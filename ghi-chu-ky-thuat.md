# Ghi chú kỹ thuật — tool nhận quà MVP

Những điều đã chốt khi dựng tool. Đọc file này trước khi sửa ảnh mẫu hoặc luồng bấm.

## Cách tool điều khiển game

Game chạy trong **LDPlayer 9**, màn hình **dọc 720×1280**. Tool không chiếm chuột Windows. Mọi cú bấm và lần chụp đi qua **ADB**:

- `adb` của LDPlayer: `D:\LDPlayer\LDPlayer9\adb.exe`
- Điều khiển giả lập: `D:\LDPlayer\LDPlayer9\ldconsole.exe`
- Máy thường hiện là `emulator-5554`. Nếu chưa thấy, tool thử `ldconsole adb` rồi `adb connect 127.0.0.1:<cổng>`.
- Chụp màn hình: `adb exec-out screencap -p`. Trên Windows phải đổi `\r\n` thành `\n` trước khi đọc PNG. Nếu lệnh đó hỏng, tool chụp ra `/sdcard/coc_gift_cap.png` rồi kéo về `logs/cap.png`.
- Bấm: `adb shell input tap x y`. Gõ UID: `adb shell input text` (chỉ chữ số). Xóa ô cũ: phím `123` (về cuối dòng) rồi nhiều lần `67` (xóa).

ADB phải bật trong LDPlayer (Cài đặt → Khác → Gỡ lỗi ADB). Trong file `vms/config/leidian0.config` khóa đó là `basicSettings.adbDebug`. Nếu đang tắt, nút **Chụp thử** có thể tắt giả lập, ghi `1` vào khóa này, rồi mở lại. Lúc đó phải vào lại game.

## Nhận nút trên ảnh

Không có DOM. Mỗi nút là một file PNG trong `templates/`. OpenCV so mẫu (`TM_CCOEFF_NORMED`), điểm từ 0 đến 1. Ảnh chụp được thu về bề rộng tối đa 640px rồi mới so, tọa độ bấm được nhân lại ra ảnh gốc.

`screen_w` trong `gift_tool/vision.py` là bề rộng ảnh lúc cắt mẫu. Đổi độ phân giải emulator là phải cắt lại mẫu.

| Mẫu | Cắt từ đâu | Ngưỡng | Ghi chú |
|---|---|---|---|
| `search.png` | Kính lúp bên phải ô UID | 0.72 | Dấu hiệu đang ở tab Add New |
| `results.png` | Chữ Results | 0.80 | Chỉ hàng kết quả tìm kiếm |
| `add.png` | Nút Add xanh | 0.78 | Phải nằm dưới chữ Results |
| `visit.png` | Nút Visit trên ảnh ADB 720×1280 | 0.80 | So màu. Không dùng ảnh cửa sổ đã bị co |
| `gift.png` | Vòng tròn vàng, hộp hồng, giữa nhà | 0.78 | So màu |
| `select.png` | Một nút Select | 0.75 | Bấm nút nào cũng được |
| `ok.png` | Nút OK sau Select | 0.75 | |
| `close.png` | Nút X đáy màn hình | 0.93 | Ngưỡng cao để khỏi bấm nhầm |
| `missing_id.png` | Câu báo không thấy ID | 0.70 | So mặt nạ chữ trắng viền đen |

## Những chỗ dễ nhận nhầm

**Visit.** Ảnh chụp tay (rộng khoảng 596px) chỉ khớp nút Visit trên emulator thật ở mức **0.65**, dưới ngưỡng. Cùng nút cắt từ `screencap` 720×1280 khớp **0.92**. Mẫu `visit.png` phải lấy từ ảnh ADB, không cắt lại từ ảnh số 4.

**Hộp quà.** Có quà: vòng tròn vàng, hộp hồng, giữa nhà, phía trên cửa. Không có quà: bong bóng trắng hình mèo. Hai cái không được dùng chung một mẫu. Mẫu hộp quà khớp ảnh có quà ở 1.00 và ảnh không quà ở khoảng 0.28.

**Hàng kết quả.** Màn Add New còn danh sách *Players you may know*, mỗi dòng cũng có nút Add. Chỉ bấm Add nằm ngay dưới chữ **Results**. Không dùng “còn thấy avatar” để kết luận ID đúng, vì ID sai thì hàng cũ không đổi.

**ID không tồn tại.** Game hiện câu tiếng Anh: *Please check the player name or player ID and try again.* Chữ trắng, viền đen, đè lên hàng thú của mình. `letter_mask` trong `vision.py` giữ điểm ảnh sáng có điểm tối bên cạnh, rồi mới so mẫu. Trên ảnh thông báo điểm khoảng **0.99**. Trên màn Add New không có câu đó, điểm khoảng **0.10 đến 0.12**.

**Đóng popup Visit.** Nút Back của Android không đóng popup hồ sơ. Bấm vùng tối bên phải, khoảng 69% chiều ngang và 70% chiều dọc. Vào nhà thì bấm Visit, không bấm vùng đó.

**Nút X.** Có ở màn tìm bạn, trong nhà, và sau khi nhận quà. Chỉ bấm X khi không còn kính lúp tìm UID, để khỏi đóng cả tab Add New.

## Luồng một UID đang chạy

Code nằm ở `process_one` trong `gift_tool/flow.py`.

1. Phải thấy kính lúp. Không thấy thì dừng, không bấm linh tinh.
2. Bấm ô nhập, xóa chữ cũ, gõ UID, bấm kính lúp.
3. Chụp một ảnh. Thấy chữ Results và nút Add ngay bên dưới thì bấm avatar bên trái nút Add.
4. Không thấy hàng Results thì ghi **ID sai** và sang UID sau. Không bấm dòng *Players you may know*.
5. Thấy Visit thì bấm. Ảnh sau đó vẫn còn Visit thì bấm thêm một lần.
6. Trong nhà: thấy hộp quà hoặc đã hiện Select thì nhận quà (bấm quà, Select, OK). Không thấy thì bấm X và ghi **không có quà**.
7. Sau OK, bấm X cho đến khi thấy lại kính lúp. Không thấy lại thì dừng cả lượt.

Giới hạn **20** quà một lượt. Mỗi UID một dòng CSV trong `logs/ket-qua-*.csv`, cột `id`, `trang_thai`, `giay`, `ghi_chu`.

## Thư mục

| Đường dẫn | Việc |
|---|---|
| `main.py`, `run.bat` | Mở cửa sổ tool |
| `gift_tool/gui.py` | Nút, ô dán UID, log |
| `gift_tool/flow.py` | Luồng một UID |
| `gift_tool/vision.py` | So ảnh mẫu |
| `gift_tool/adb_client.py` | Chụp và bấm |
| `templates/` | Ảnh mẫu nút |
| `logs/` | CSV và ảnh chụp thử |
| `requirements.txt` | `opencv-python-headless`, `numpy` |

Python đang dùng là 3.13 (`py -3`). Thư viện đã cài cho bản Python đó.

## Rủi ro

Game có thể coi đây là thao tác tự động và khóa tài khoản. Chạy chậm không biến việc này thành an toàn. Lần thử nên dùng tài khoản phụ.
