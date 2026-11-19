# Báo cáo Day 09 — Đặng Minh Huy, 2A202603162

## 1. Kết luận trước

**HOLD** (mã thoát 10) — bản xuất `submission/export/clean_v1/` là **bản NHÁP**, không được phát hành.

- **224 ảnh vào** → cửa vào loại **21** (CORRUPT 2, BAD_SIZE 3, DUP_EXACT 8, DUP_NEAR 3, LEAK_TEST 5) → **203 ảnh vào dataset**.
- Máy sửa được **toàn bộ lỗi bắt buộc**: 35 thay đổi vòng 1 + 1 vòng sau duyệt; sau 80 ảnh người duyệt, `07_error_list_v3` còn **0 lỗi ERROR**.
- Lý do Hold: **38/203 ảnh (18,7%) còn cảnh báo chưa người duyệt ≥ ngưỡng 10%** — hàng đợi 125 ảnh vượt ngân sách 80, phần dư không ai xem. Số liệu: `08_summary.json`.

## 2. Lỗi và phân việc

Từ `02_error_list_v1` (210 dòng, trên 203 ảnh; mẫu số ghi kèm):

| Mã lỗi | Số ảnh/dòng | Ai sửa | Vì sao |
|---|---:|---|---|
| CORRUPT_IMAGE | 2 ảnh | máy (loại) | không mở được, không cứu được |
| BAD_SIZE | 3 ảnh | máy (loại) | cạnh ngắn < 250px |
| DUP_IMAGE_EXACT | 8 ảnh | máy (loại) | trùng byte, giữ ảnh đầu |
| DUP_IMAGE_NEAR | 3 ảnh | máy (loại) | phash ≤ 8; đã mở xem từng cặp (§3) |
| LEAK_TEST | 5 ảnh | máy (loại) | trùng kho test/gold_val — metric đẹp giả |
| BAD_FORMAT | 3 dòng | máy (drop_line) | thiếu cột / không phải số |
| BAD_CLASS_ID | 6 dòng | máy (drop_line) | id ngoài 0..3 |
| BOX_ZERO | 4 dòng | máy (drop_line) | rộng/cao ≤ 0 |
| BOX_OUT_OF_IMAGE | 8 dòng | máy (clip_box) | cắt về [0,1], mất diện tích thì xoá |
| DUP_BOX | 7 dòng | máy (drop_line) | cùng lớp, IoU > 0.9 |
| BAD_CLASS_NAME | 2 dòng (data.yaml) | máy (rename) | `Person`/`Bus` sai chỗ |
| MISSING_LABEL_FILE | 6 ảnh | **người** (needs_label) | máy không bịa nhãn |
| EMPTY_LABEL | 12 ảnh | người | ảnh nền hay quên gán? máy không phân biệt |
| BOX_TINY / BOX_HUGE | 6 / 3 dòng | người | ngưỡng 12px/0.95 là quy án, không có đáp án để calibrate |
| CLASS_RARE | 4 | người | thống kê, không kết luận lỗi |
| POSSIBLE_MISSING | 53 dòng | người | model lớn thấy vật, nhãn không có box |
| POSSIBLE_WRONG_CLASS | 18 dòng | người | cùng vị trí khác lớp (car/truck/bus) |
| POSSIBLE_LOOSE_BOX | 28 dòng | người | đúng vật, IoU thấp |
| POSSIBLE_FALSE_POS | 29 dòng | người | box nhãn không khớp dự đoán nào |

**Hàng đợi** (`05_review_queue.csv`, 125 ảnh): điểm = Σ trọng số cảnh báo × (1+conf) + điểm FIXED_*/NEEDS_LABEL. Đầu hàng đợi là các ảnh `NEEDS_LABEL` (weight 10 — chỉ người gán được) và `img_0020` (11,52: vừa bị xoá dòng vừa dính MISSING + WRONG_CLASS — nhiều lỗi ngữ nghĩa nhất). Với ngân sách 80 ảnh, người giải quyết được **66/123 dòng cảnh báo ngữ nghĩa (54%)**: MISSING 53→13, WRONG_CLASS 18→3, LOOSE 28→20, FALSE_POS 24→21 (v2 → v3).

## 3. Calibration (2 ngưỡng)

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **8** | NEAR 1.00/0.50 → 1.00/0.67 (EXACT giữ 1.00/1.00) | Lỗi E → máy **tự loại ảnh** nên phải giữ precision = 1.00; 8 là đầu plateau 4–14, đổi 2 FN lấy +0,17 recall, không đổi FP |
| `second_opinion.conf` | 0.25 | **0.6** | MISSING 0.50/1.00 → 0.57/1.00; WRONG_CLASS 0.56/0.83 → 0.62/0.83; LOOSE 0.29/0.40 → 0.20/0.20; FALSE_POS 0.31/1.00 (không đổi — dùng `fp_conf`) | Cảnh báo chuyển người → giữ recall tối đa; 0.6 là "knee" (bỏ dự đoán nhiễu mà không mất lỗi chèn nào); 0.7–0.8 chỉ tăng precision bằng cách **làm checker mù** (mất recall MISSING/LOOSE) → hàng đợi nhỏ giả tạo = Release giả |

**Một chỗ calibration có thể đánh lừa:** `phash_dist=16` có F1 DUP_NEAR **0.91 > 0,80** — nhìn bảng thì "tốt hơn 8". Nhưng mức tăng đến đúng 1 cặp biến đổi mạnh đã chèn trong calib (ô 6 lỗi, nhảy từng bước 17%), và ở 20 thì EXACT tụt recall 0.33 (ảnh chỉ nhận một mã: NEAR nuốt EXACT). Bằng chứng từ dữ liệu của tôi: mở xem cả 3 cặp NEAR bị loại trên raw — `img_0042↔img_0076` là **cùng một cảnh xe buýt 103 ROJA** (đã xác nhận bằng mắt), 0037↔0143 và 0077↔0223 tương tự; 21 ảnh loại ở intake là hợp lý. Với 16, mọi FP sẽ **xoá âm thầm ảnh tốt** trên raw — nơi không còn đáp án nào để kiểm. Calib chỉ 39 ảnh, lại dựng từ nhãn người (WRONG_CLASS chủ yếu person→car), còn raw nghiêng car/truck/bus và có LEAK_TEST mà calib không có → recall trên calib không phải recall trên raw.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được

**(a) Gate chặn thật:** chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb` (không người duyệt) → kết luận **REWORK, mã thoát 20**, còn 6 lỗi `MISSING_LABEL_FILE`, và **`work/exp_nb/clean_v1` không tồn tại** — cửa chặn không cho xuất dataset khi còn lỗi bắt buộc. Ngược lại, Hold thì vẫn xuất nhưng manifest ghi `decision: Hold` (bản nháp) — đúng hợp đồng mã thoát 0/10/20 cho CI.

**(b) Điểm mù có bằng chứng (≥2):**
1. **Nhầm lớp mà model lớn cũng nhầm**: `img_0030` (sân cầu lông) — hàng "person" thực chất là **ảnh phản chiếu trong gương**; cả yolo26l lẫn nhãn máy cùng sai → second_opinion im lặng. Máy-vs-máy không bắt được lỗi hệ thống chung.
2. **Ảnh trùng biến đổi mạnh lọt lưới**: ở dist 8, calib vẫn bỏ 2/6 cặp chèn (recall 0.67) — bản thu/cắt cực đoan vào thẳng dataset, không ai cờ.
3. **LOOSE_BOX precision 0.20**: ảnh sạch cũng bị cờ vì model và người khoanh tự nhiên lệch nhau — người mở 5 cờ chỉ ~1 cờ thật, mệt và dễ bỏ qua cờ đúng.
4. **EMPTY_LABEL (còn 4 ở v3)**: máy không phân biệt "ảnh nền hợp lệ" với "quên gán nhãn" — chỉ người biết.
5. **BOX_TINY không có đáp án để calibrate**: 7 ảnh biên 8,9–11,4px quanh ngưỡng 12px là phán quyết của quy án, không phải của dữ liệu.

## 5. Train: raw vs clean

_(Đang chạy — xem mục dưới; nếu bảng trống nghĩa là chưa xong)_

## 6. Quyết định và ghi chú AI

**(a) Quyết định cuối: HOLD** — khớp số liệu (`07_error_list_v3`: 0 ERROR; `08_summary`: 18,7% ≥ 10%). Để thành **Release**: duyệt nốt ~45 ảnh còn lại của hàng đợi (CVAT/label studio) rồi chạy lại — nếu người xác nhận/sửa, tỉ lệ ảnh còn cảnh báo chưa duyệt giảm xuống dưới 10%; hoặc tăng `review.budget_images` (quy án dự án, không tự đổi trong lab). Điều kiện đổi sang **Rework**: bất kỳ ảnh nào người duyệt để lại lỗi cú pháp mà máy không sửa được (VD xoá nhầm thành file nhãn hỏng).

**(b) Ghi chú AI (3 dòng):**
1. *Prompt chính*: dán docstring-từng-module (định dạng vào, bảng quy tắc mã lỗi, kiểu in ra, giới hạn "không sửa data/raw") + file test tương ứng vào AI, theo 4 ý của docs/PROMPTING.md — không mô tả lại bằng lời.
2. *Cách kiểm*: 79 unit test xanh; tự viết 5 ca ngoài test (1 dòng dính 2 lỗi → chỉ 1 `drop_line`; dòng trống giữa file giữ số dòng gốc; 1 ảnh nhiều dự đoán đúng thứ tự; clip→drop khi box ra hẳn ngoài; gate đếm theo ảnh, ERROR không bị "che" bởi ảnh đã duyệt); mở xem 3 cặp DUP_NEAR bằng mắt; chạy `pipeline.run` trên raw và thí nghiệm `--budget 0`.
3. *Một lần AI sai*: script kiểm bổ sung ban đầu mong đợi autofix **xoá** dòng tràn ảnh — thực tế nó **clip** `0.95→0.925` (đúng docstring); lỗi ở kỳ vọng của code kiểm, không ở module, sửa kỳ vọng và chạy lại. Ngoài ra ghi chú trung thực: `scripts/check_submission.py` trên **Windows** báo nhầm `pipeline/calibrate.py` "nhắc tới MANIFEST" vì so đường dẫn `\` với khoá `/` trong `_protected.json` (file đã ghim sha1 — không sửa; trên máy Linux của giảng viên lỗi này không xảy ra; các mục LỖI khác đều đã sạch).
