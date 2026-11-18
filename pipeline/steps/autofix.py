"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


# Mã lỗi -> cách sửa (khớp bảng trong docstring)
DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}          # xoá dòng
CLIP_CODES = {"BOX_OUT_OF_IMAGE"}                                           # cắt box về [0,1]
REMOVE_CODES = {"DUP_IMAGE_EXACT", "DUP_IMAGE_NEAR", "LEAK_TEST",
                "CORRUPT_IMAGE", "BAD_SIZE"}                                 # loại cả ảnh + nhãn


def _fmt(cls, x, y, w, h):
    """Dòng YOLO chuẩn sau khi cắt; 6 số thập phân làm round-trip an toàn cho box <= 1."""
    return f"{cls} {x:.6f} {y:.6f} {w:.6f} {h:.6f}"


def _fix_label_file(ds, stem, file_issues):
    """Gom mọi sửa theo dòng của MỘT file rồi ghi lại MỘT lần, dùng số dòng GỐC."""
    by_line = defaultdict(set)
    for i in file_issues:
        by_line[i.line].add(i.code)
    path = ds.label_path(stem)
    raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
    out, fixes, touched = [], [], False
    for n, text in enumerate(raw, 1):                   # số dòng GỐC, dòng trống vẫn đếm
        codes = by_line.get(n, set())
        if codes & DROP_CODES:                          # xoá dòng thắng, không ghi thêm clip_box
            touched = True
            fixes.append(dict(image=stem, line=n, action="drop_line", before=text.strip(), after=""))
            continue
        if codes & CLIP_CODES:
            touched = True
            try:
                cls, x, y, w, h = parse_yolo_line(text)
            except ValueError:                          # dòng không parse được: coi như xoá
                fixes.append(dict(image=stem, line=n, action="drop_line", before=text.strip(), after=""))
                continue
            l, t = max(0.0, x - w / 2), max(0.0, y - h / 2)
            r, b = min(1.0, x + w / 2), min(1.0, y + h / 2)
            nw, nh = r - l, b - t
            if nw <= 0 or nh <= 0:                      # cắt xong hết diện tích -> xoá, không ghi box rỗng
                fixes.append(dict(image=stem, line=n, action="drop_line", before=text.strip(),
                                  after="(box nằm hẳn ngoài ảnh sau khi cắt)"))
                continue
            new = _fmt(cls, (l + r) / 2, (t + b) / 2, nw, nh)
            fixes.append(dict(image=stem, line=n, action="clip_box", before=text.strip(), after=new))
            out.append(new)
            continue
        out.append(text)                                # giữ nguyên dòng liên quan (kể cả nội dung gốc)
    if touched:
        path.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
    return fixes


def _rename_classes(ds, cfg):
    """Ghi lại `names` trong data.yaml đúng thứ tự cfg["classes"]; giữ các khoá khác."""
    data = {}
    if ds.yaml_path.exists():
        data = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
    before = ", ".join(f"{i}={ds.yaml_names().get(i)!r}" for i in sorted(ds.yaml_names()))
    data["names"] = {i: n for i, n in enumerate(cfg["classes"])}
    ds.yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    after = ", ".join(f"{i}={n!r}" for i, n in enumerate(cfg["classes"]))
    return dict(image="data.yaml", line="", action="rename_classes", before=before, after=after)


def fix(ds, issues, cfg):
    fixes, removed = [], set()
    errors = sorted((i for i in issues if i.severity == ERROR), key=lambda i: (i.image, i.line or 0))

    # 1) Loại cả ảnh: ảnh + nhãn biến mất khỏi ds (data/raw không bao giờ bị đụng tới)
    for i in errors:
        if i.code in REMOVE_CODES and i.image not in removed:
            removed.add(i.image)
            img = ds.image_path(i.image)
            if img:
                img.unlink(missing_ok=True)
            ds.label_path(i.image).unlink(missing_ok=True)
            fixes.append(dict(image=i.image, line="", action="remove_image",
                              before=img.name if img else "(không có file ảnh)", after=""))

    # 2) data.yaml: tên lớp sai -> viết lại đúng danh sách dự án (idempotent vì chỉ sửa khi còn issue)
    if any(i.code == "BAD_CLASS_NAME" for i in errors):
        fixes.append(_rename_classes(ds, cfg))

    # 3) Nhãn: missing file -> needs_label (không bịa nhãn, không tạo file rỗng);
    #    các issue dòng còn lại gom theo file (bỏ qua êm ảnh đã bị loại ở bước 1)
    by_file = defaultdict(list)
    for i in errors:
        if i.image in removed:
            continue
        if i.code == "MISSING_LABEL_FILE":
            fixes.append(dict(image=i.image, line="", action="needs_label",
                              before="(không có file)", after="chuyển người gán"))
            continue
        if i.line and (i.code in DROP_CODES or i.code in CLIP_CODES):
            by_file[i.image].append(i)
    for stem in sorted(by_file):
        if ds.label_path(stem).exists():
            fixes.extend(_fix_label_file(ds, stem, by_file[stem]))
    return fixes
