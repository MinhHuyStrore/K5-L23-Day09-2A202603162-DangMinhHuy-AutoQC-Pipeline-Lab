"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.   ★

Test:  pytest tests/test_gate.py -q

Cây quyết định Day 07 (slide Day 09: "Lỗi bắt buộc chặn pipeline; lỗi cảnh báo chuyển người xem"):

  còn ≥ 1 lỗi bắt buộc (severity ERROR)                          -> "Rework"
  không còn lỗi bắt buộc, nhưng tỉ lệ ẢNH còn cảnh báo
      >= cfg["gate"]["warn_ratio_hold"]                          -> "Hold"
  còn lại                                                        -> "Release"

Tỉ lệ cảnh báo = (số ẢNH khác nhau có ≥ 1 cảnh báo) / (tổng số ảnh).  Chú ý:
- chỉ đếm issue có `image` nằm trong `image_stems` (bỏ "<dataset>", "data.yaml");
- bỏ qua ảnh nằm trong `reviewed` (người đã xem, cảnh báo của ảnh đó coi như đã xử lý) — nhưng LỖI BẮT BUỘC thì không bao giờ được bỏ qua;
- mẫu số là số ảnh, không phải số issue.

Trả về dict: decision, n_errors, n_warn_images, n_images, warn_ratio (làm tròn 4 chữ số), reasons (list[str], giải thích bằng tiếng Việt, có số liệu).
"""
from ..common import ERROR, WARN  # noqa: F401


def decide(issues, image_stems, cfg, reviewed=frozenset()):
    stems = set(image_stems)
    hold = cfg["gate"]["warn_ratio_hold"]
    # LỖI BẮT BUỘC: đếm hết, kể cả cấp dataset (data.yaml) và kể cả ảnh đã được người duyệt
    errors = [i for i in issues if i.severity == ERROR]
    # CẢNH BÁO: chỉ tính trên ẢNH còn trong dataset và CHƯA được người duyệt
    warn_images = {i.image for i in issues
                   if i.severity == WARN and i.image in stems and i.image not in reviewed}
    n_images = len(stems)
    n_warn = len(warn_images)
    warn_ratio = round(n_warn / n_images, 4) if n_images else 0.0

    if errors:
        decision = "Rework"
        by_code = {}
        for i in errors:
            by_code[i.code] = by_code.get(i.code, 0) + 1
        detail = ", ".join(f"{c}: {n}" for c, n in sorted(by_code.items()))
        reasons = [f"còn {len(errors)} lỗi bắt buộc (ERROR) chưa được sửa [{detail}]",
                   "lỗi bắt buộc chặn phát hành, kể cả trên ảnh người đã duyệt -> về bước sửa máy / người gán nhãn"]
    elif warn_ratio >= hold:
        decision = "Hold"
        pct = f"{warn_ratio:.1%}" if n_images else "0%"
        reasons = [f"0 lỗi bắt buộc; {n_warn}/{n_images} ảnh còn cảnh báo chưa người duyệt ({pct} >= ngưỡng {hold:.0%})",
                   "hàng đợi lớn hơn ngân sách duyệt nên phần dư không ai xem -> chỉ là bản nháp"]
    else:
        decision = "Release"
        pct = f"{warn_ratio:.1%}" if n_images else "0%"
        reasons = [f"0 lỗi bắt buộc; {n_warn}/{n_images} ảnh còn cảnh báo chưa người duyệt ({pct} < ngưỡng {hold:.0%})",
                   "đủ điều kiện phát hành theo cửa chặn"]
    return dict(decision=decision, n_errors=len(errors), n_warn_images=n_warn,
                n_images=n_images, warn_ratio=warn_ratio, reasons=reasons)
