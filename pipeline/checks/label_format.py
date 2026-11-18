"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401


def run(ds, cfg):
    c = cfg["label_format"]                       # ngưỡng luôn lấy từ config, không viết cứng
    tol, min_px = c["overflow_tol"], c["min_box_px"]
    max_frac, dup_iou = c["max_box_frac"], c["dup_box_iou"]
    n_cls = len(ds.classes)
    issues = []
    for p in ds.label_files():
        stem = p.stem
        size = ds.image_size(stem)                # (W, H) px; None nếu ảnh mở không được
        good = []                                 # các dòng "hình học hợp lệ": (line, cls, cx, cy, w, h)
        for ln, text in ds.read_label_lines(stem) or []:   # số dòng GỐC (đã bỏ dòng trống)
            try:
                cls, x, y, w, h = parse_yolo_line(text)
            except ValueError as e:
                issues.append(Issue("label_format", ERROR, "BAD_FORMAT", stem, f"dòng không hợp lệ: {e}", ln))
                continue
            if not 0 <= cls < n_cls:
                issues.append(Issue("label_format", ERROR, "BAD_CLASS_ID", stem,
                                    f"id lớp {cls} ngoài 0..{n_cls - 1}", ln, {"id": cls}))
                continue
            if w <= 0 or h <= 0:
                issues.append(Issue("label_format", ERROR, "BOX_ZERO", stem, f"rộng={w} cao={h}", ln))
                continue
            # dòng hỏng cú pháp rồi thì không kiểm tiếp hình học của nó
            overflow = max(-x + w / 2, x + w / 2 - 1.0, -y + h / 2, y + h / 2 - 1.0)
            if overflow > tol:
                issues.append(Issue("label_format", ERROR, "BOX_OUT_OF_IMAGE", stem,
                                    f"box tràn ra ngoài ảnh: {overflow:.4f}", ln,
                                    {"overflow": round(overflow, 6)}))
                continue
            dup = next((g for g in good if g[1] == cls and iou_xywh((x, y, w, h), g[2:]) > dup_iou), None)
            if dup:
                issues.append(Issue("label_format", ERROR, "DUP_BOX", stem,
                                    f"trùng box dòng {dup[0]} (IoU > {dup_iou})", ln,
                                    {"of_line": dup[0]}))
                continue
            good.append((ln, cls, x, y, w, h))
            if size:                              # chỉ cảnh báo hình học khi đo được bằng px
                W, H = size
                short_px = min(w * W, h * H)
                if short_px < min_px:
                    issues.append(Issue("label_format", WARN, "BOX_TINY", stem,
                                        f"cạnh ngắn box {short_px:.1f}px < {min_px}px", ln,
                                        {"short_px": round(short_px, 1)}))
                if w * h > max_frac:
                    issues.append(Issue("label_format", WARN, "BOX_HUGE", stem,
                                        f"box phủ {w * h:.2f} > {max_frac} diện tích ảnh", ln,
                                        {"area_frac": round(w * h, 3)}))
    return issues
