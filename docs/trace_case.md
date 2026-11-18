# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case phân tích: `seeded_regression C-002@11`

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, report `src/reports/eval_seeded_regression.json`, `run_id`: `E-seeded_regression-20261118-051d` |
| Triệu chứng | `lab8 grader` FAIL (`status resolved != denied`). Đọc ledger trước reply: ledger ghi `refund_vnd=20000`, `refund_count=1`, `status=resolved` trong khi nhãn đúng là `refund_vnd=0`, `refund_count=0`, `status=denied`; reply ở step 6 nói `"Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."` |
| Bước sai đầu tiên | Event **3** (`model_override`): `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Event **1** (`handoff`) giao đúng phạm vi `owner_order_only` và 3 tool read-only; Event **2** (`investigator`) tra DB chính xác `order_id="O-202"`, `status="delivered"`, `delay_days=2` (< 3 ngày nên không đủ điều kiện). Từ Event **3**, agent lấy `5 ngày` trong ticket ghi đè `delay_days=2` của DB, kéo theo Event **4** (`quote`) tính sai thành `20000` và gọi `issue_refund` ghi nhầm vào ledger. |
| Failure mode | `FM-03` (`ticket_trust`) trong `docs/failure_taxonomy.md` |
| Đối chứng | Cùng `C-002@11` trên shape `fixed`: không có event `model_override`. Ngay sau Event **2** (`investigator`, `delay_days=2`), Event **3** (`quote`) trả `{"amount_vnd": 0, "reason": "no_entitlement", "clause_ids": [], "parts": {}}`, ledger giữ `refund_vnd=0`, `refund_count=0`, `status=denied`. |
| Regression test | `src/tests/test_lab9_trace_case.py::test_trace_case_c002_fm03_caught_on_regression_and_passes_on_fixed` (dùng `DbFactKept` + kiểm tra ledger `refund_vnd == 0` và `status == "denied"`): đã kiểm chứng FAIL trên `seeded_regression` và PASS trên `fixed`. |
| Chưa chắc chắn | Trace chỉ chứng minh agent tin ticket khi nó tự log event `model_override`. Nếu một biến thể lỗi ghi đè ngầm không phát event (như `quiet_override`), chỉ kiểm tra `DbFactKept` sẽ không đủ mà phải kết hợp grader kiểm tra ledger (`RefundAmountCorrect` / `TrialPass`). |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
