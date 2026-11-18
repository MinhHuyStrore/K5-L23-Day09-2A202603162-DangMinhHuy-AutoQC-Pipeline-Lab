"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401
from ..model_cache import get_preds  # noqa: F401


def _pred_rows(rows):
    """[(cls, conf, cx, cy, w, h)] từ dự đoán thô, bỏ dòng dị dạng (model/cache có thể thiếu cột)."""
    out = []
    for r in rows or []:
        try:
            cls = int(r[0])
            conf = float(r[1])
            box = (float(r[2]), float(r[3]), float(r[4]), float(r[5]))
        except (IndexError, TypeError, ValueError):
            continue
        out.append((cls, conf, box))
    return out


def run(ds, cfg, preds=None):
    c = cfg["second_opinion"]
    if preds is None:                       # không có sẵn -> lấy ý kiến model lớn hơn (cache, không cần GPU)
        preds = get_preds(ds, cfg, "checker")
    issues = []
    for p in ds.image_files():              # thứ tự theo tên file = thứ tự báo cáo ổn định
        stem = p.stem
        if stem not in preds:
            continue
        label_lines = ds.read_label_lines(stem)
        if label_lines is None:             # không có file nhãn: phần việc của missing_labels/needs_label
            continue
        size = ds.image_size(stem)
        if not size:
            continue
        W, H = size
        all_rows = _pred_rows(preds[stem])
        # P: dự đoán đủ tin cậy và đủ lớn (lọc conf + diện tích px) cho chiều "model thấy vật"
        P = [(cls, conf, box) for cls, conf, box in all_rows
             if conf >= c["conf"] and box[2] * W * box[3] * H >= c["min_area_px"]]
        # FP: mọi dự đoán conf >= fp_conf (không lọc diện tích) cho chiều nhãn-thừa
        FP = [box for _cls, conf, box in all_rows if conf >= c["fp_conf"]]

        # Nhãn hợp lệ kèm số dòng gốc (để FALSE_POS báo đúng dòng)
        labels = []                          # [(line, cls, (cx, cy, w, h))]
        for ln, text in label_lines:
            try:
                b = parse_yolo_line(text)
            except ValueError:               # dòng hỏng: không được làm script chết
                continue
            if 0 <= b[0] < len(ds.classes):
                labels.append((ln, b[0], (b[1], b[2], b[3], b[4])))

        # (a) chiều dự đoán -> nhãn: mỗi dự đoán tối đa 1 issue
        for cls, conf, box in P:
            cands = [(lcls, iou_xywh(box, lbox)) for _ln, lcls, lbox in labels
                     if iou_xywh(box, lbox) >= c["iou_missing"]]
            if not cands:                                        # không có nhãn nào đủ gần
                code, msg = "POSSIBLE_MISSING", "model thấy vật, nhãn không có box phù hợp"
            else:
                same = [iou for lcls, iou in cands if lcls == cls]
                if same:                                         # cùng lớp: chỉ cờ box lỏng nếu IoU < iou_loose
                    if max(same) < c["iou_loose"]:
                        code, msg = "POSSIBLE_LOOSE_BOX", "đúng vật, cùng lớp nhưng IoU với box nhãn thấp"
                    else:
                        continue                                 # nhãn đã phủ vật này -> im lặng
                else:
                    best_other = max(iou for _lcls, iou in cands)
                    if best_other >= c["iou_match"]:
                        code, msg = "POSSIBLE_WRONG_CLASS", "cùng vị trí nhưng nhãn gắn lớp khác"
                    else:
                        continue                                 # IoU trong [missing, match): mờ hồ -> không cờ
            issues.append(Issue("second_opinion", WARN, code, stem, f"{msg} (conf {conf:.2f})",
                                extra={"conf": round(conf, 3)}))

        # (b) chiều nhãn -> dự đoán: box nhãn không khớp vật nào model thấy = có thể thừa
        for ln, _cls, lbox in labels:
            best = max((iou_xywh(lbox, pbox) for pbox in FP), default=0.0)
            if best < c["iou_missing"]:
                issues.append(Issue("second_opinion", WARN, "POSSIBLE_FALSE_POS", stem,
                                    "box nhãn không khớp dự đoán nào của model", ln,
                                    {"iou": round(best, 3)}))
    return issues
