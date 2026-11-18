# Judge audit

Chạy:
- `python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 5`
- `python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Ma trận nhầm lẫn (`FAIL`=POS) | Fail rate (obs → RG) | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|---|---|
| `tone_ok` | 100 | 0.757 | 0.857 | 0.800 | `tp=24, fp=4, fn=6, tn=66` | `0.28 → 0.30` | Có (cả 3 đều vượt sàn) | **dùng** (chỉ cho giọng điệu, bổ sung sửa rubric) |
| `helpful` | 100 | 0.375 | 1.000 | 0.300 | `tp=9, fp=0, fn=21, tn=70` | `0.09 → 0.30` | Không (`κ=0.375 < 0.6`, `R=0.3 < 0.7`) | **loại** (cấm dùng làm gate) |

## ≥5 case audit thủ công (8 case tiêu biểu)
| # | Case | Judge nói | Người nói | Ai đúng? | Phân tích & hành động sửa rubric / nhãn |
|---|---|---|---|---|---|
| 1 | `H-008` (`tone_ok`): *"Em đã hoàn tiền cho anh rồi nha, anh check giúp em."* | PASS | FAIL | Người đúng (FN) | Xưng `"em"` + `"nha"` quá suồng sã so với chuẩn CSKH LogiX; judge nhầm sang "thân thiện". **Hành động:** Bổ sung quy tắc rõ trong rubric: bắt buộc xưng `"LogiX"` và gọi khách `"anh/chị"`, cấm `"nha/nhé/bạn ơi"`. |
| 2 | `H-029` (`tone_ok`): *"Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm."* | PASS | FAIL | Người đúng (FN) | Cụm `"không cần nhắn thêm"` mang giọng ra lệnh, xua đuổi khách; judge bị đánh lừa bởi từ mở đầu `"Dạ, vui lòng"`. **Hành động:** Thêm ví dụ âm (negative example) trong rubric: không chấm PASS chỉ dựa trên từ khóa lịch sự đầu câu nếu vế sau có ý đuổi/ra lệnh khách. |
| 3 | `H-042` (`tone_ok`): *"Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ."* | FAIL | PASS | Người đúng (FP) | Câu ngắn gọn, lịch sự (`Dạ` / `ạ`), đủ thông tin hoàn tiền; judge phạt oan vì đòi phải có câu xin lỗi. **Hành động:** Ghi rõ trong rubric: phản hồi xác nhận hoàn tiền thành công **không bắt buộc** phải có câu xin lỗi dài dòng. |
| 4 | `H-051` (`tone_ok`): *"Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ."* | FAIL | PASS | Người đúng (FP) | Chính sách CSKH LogiX cho phép dùng từ `"refund"`; judge tự phạt vì trộn tiếng Anh. **Hành động:** Nêu rõ danh sách thuật ngữ tiếng Anh được phép (whitelist: `refund`, `claim`, `order`) trong rubric. |
| 5 | `H-063` (`tone_ok`): *"Dạ, LogiX đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ."* | PASS | FAIL | Người đúng (FN) | Tự ý hứa `"sẽ hoàn thêm"` ngoài kết quả hệ thống; giọng nghe lịch sự nên judge bỏ lọt. **Hành động:** Thêm tiêu chí cấm cam kết/hứa hẹn ngoài quyết định hệ thống (và tách kiểm tra số tiền sang code grader FM-08). |
| 6 | `H-081` (`tone_ok`): *"Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ."* | FAIL | PASS | **Judge đúng** (nhãn người sai) | Người chấm đọc nhầm ticket nên gán nhầm nhãn PASS trong tập audit. **Hành động:** **Sửa lại nhãn người (re-label)** trong bộ benchmark và áp dụng 2 người chấm độc lập (double annotation) cho các ca biên. |
| 7 | `HL-016` (`helpful`): *"Dạ, LogiX thành thật xin lỗi... LogiX đã hoàn 55.000đ cho đơn O-404..."* (ledger ghi `35.000đ`) | PASS | FAIL | Người đúng (FN) | Reply nói sai số tiền (`55.000đ` vs ledger `35.000đ`) nhưng mở đầu/kết thúc xin lỗi rất dài dòng khiến judge chấm PASS (verbosity/politeness bias + không đọc được ledger). **Hành động:** **Không dùng LLM judge** để chấm đúng/sai tiền — tách phần khớp tiền sang **code grader** (FM-08). |
| 8 | `HL-047` (`helpful`): *"Ok bạn, đơn O-515 xử lý rồi nhé."* | PASS | FAIL | Người đúng (FN) | Trả lời suồng sã (`Ok bạn`, `nhé`) và không nêu rõ kết quả/số tiền hoàn, nhưng judge vẫn bỏ lọt. **Hành động:** Dùng judge `tone_ok` đã qua hiệu chuẩn cho giọng điệu thay vì gộp chung vào tiêu chí mơ hồ `helpful`. |

## Kết luận
- **Tiêu chí bị loại:** `helpful` **FAIL** nặng chuẩn FLOORS (`κ = 0.375 < 0.6`, `Recall = 0.300 < 0.7`), do ma trận nhầm lẫn có **`fn = 21`** trên tổng số 30 lỗi thật (`tp = 9, fp = 0, fn = 21, tn = 70`). Judge bỏ lọt tới **70% số lỗi thật** (phần lớn là các ca nói sai số tiền so với ledger nhưng viết lời xin lỗi dài dòng) khiến tỉ lệ lỗi quan sát bị đánh giá thấp ảo (`0.09`), trong khi hiệu chỉnh Rogan-Gladen chỉ ra tỉ lệ lỗi thật là **`0.30`**. Vì vậy **tuyệt đối không được dùng `helpful` làm CI gate**; các tiêu chí liên quan tới tiền và phê duyệt phải chấm bằng **code grader** (M3).
- **Tiêu chí giữ lại:** `tone_ok` **PASS** cả 3 ngưỡng (`κ = 0.757`, `P = 0.857`, `R = 0.800`; `tp = 24, fp = 4, fn = 6, tn = 66`; Rogan-Gladen `0.28 → 0.30`), đủ điều kiện dùng để theo dõi chất lượng giọng điệu sau khi cập nhật rubric theo các ca audit trên.
- **Rủi ro còn lại:** Judge chỉ được kiểm định trên tập dữ liệu replay đã công khai (`n = 100`); cần thu thập tập **held-out** mới do người chấm độc lập (sau khi sửa rubric) để xác nhận không bị overfit vào các mẫu audit hiện tại.
