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
| `friends.png` | Icon hai con ma, phía trên nút Pinball ở sân | 0.80 | So màu. Cắt dưới chấm đỏ thông báo |
| `community.png` | Nút Community ở panel hồ sơ | 0.80 | So màu. Mốc để tìm tab Add New |

## Những chỗ dễ nhận nhầm

**Visit.** Ảnh chụp tay (rộng khoảng 596px) chỉ khớp nút Visit trên emulator thật ở mức **0.65**, dưới ngưỡng. Cùng nút cắt từ `screencap` 720×1280 khớp **0.92**. Mẫu `visit.png` phải lấy từ ảnh ADB, không cắt lại từ ảnh số 4.

**Hộp quà.** Có quà: vòng tròn vàng, hộp hồng, giữa nhà, phía trên cửa. Không có quà: bong bóng trắng hình mèo. Hai cái không được dùng chung một mẫu. Mẫu hộp quà khớp ảnh có quà ở 1.00 và ảnh không quà ở khoảng 0.28.

**Hàng kết quả.** Màn Add New còn danh sách *Players you may know*, mỗi dòng cũng có nút Add. Chỉ bấm Add nằm ngay dưới chữ **Results**. Không dùng “còn thấy avatar” để kết luận ID đúng, vì ID sai thì hàng cũ không đổi.

**ID không tồn tại.** Game hiện câu tiếng Anh: *Please check the player name or player ID and try again.* Chữ trắng, viền đen, đè lên hàng thú của mình. `letter_mask` trong `vision.py` giữ điểm ảnh sáng có điểm tối bên cạnh, rồi mới so mẫu. Trên ảnh thông báo điểm khoảng **0.99**. Trên màn Add New không có câu đó, điểm khoảng **0.10 đến 0.12**.

**Đóng popup Visit.** Nút Back của Android không đóng popup hồ sơ. Bấm vùng tối bên phải, khoảng 69% chiều ngang và 70% chiều dọc. Vào nhà thì bấm Visit, không bấm vùng đó.

**Nút X.** Có ở màn tìm bạn, trong nhà, và sau khi nhận quà. Chỉ bấm X khi không còn kính lúp tìm UID, để khỏi đóng cả tab Add New.

## Đọc cấp người chơi

Sau khi thấy hàng Results, trước khi bấm avatar. Hàm `player_level` trong `gift_tool/vision.py`. Ngưỡng `MIN_LEVEL = 150` trong `gift_tool/flow.py`.

Nhãn cần đọc là viên đen **Lvl NNN** dưới tên, bên trái nút Add. Không đọc **Lvl** trên thẻ thú ở đầu màn hình (ví dụ Lvl 131 của thú mình).

Cách đọc:

1. Cắt vùng bên trái nút Add. Viên đen là mảng tối (`gray < 60`), rộng ít nhất 36px và rộng hơn 1,6 lần chiều cao.
2. Chữ trắng trên viên. Nửa trái là chữ Lvl. Chỉ giữ nét có tâm nằm sau 3,25 lần chiều cao nét. Không cắt theo phần trăm bề rộng viên: viên một hoặc hai chữ số ngắn hơn, chữ l bị tính thành một chữ số, nét đó khớp hụt và cả cấp thành rỗng.
3. So từng nét với chữ số vẽ bằng Pillow, font **Malgun Bold** (`C:\Windows\Fonts\malgunbd.ttf`). Máy không có font này thì dùng Arial Bold. Nhận một chữ khi điểm khớp từ **0.64** và cách chữ đứng thứ hai ít nhất **0.08**. Một chữ hụt thì cả cấp thành rỗng.
4. Đối chiếu độ rộng viên với số chữ đọc được (`_expected_digits` trong `vision.py`). Trên ảnh 720×1280, nút Add rộng 146px, viên một chữ số rộng 89–93px, hai chữ 103–107px, ba chữ 117–121px. Viên rộng hơn số chữ đọc được thì rớt chữ, trả rỗng. Vì sao: đọc `299` thành `29` sẽ ghi **false** oan và bỏ lỡ người chơi cấp cao. Làm tròn nghiêng về ít chữ hơn, vì chữ 1 hẹp.

Cấp rỗng thì `_read_level` trong `gift_tool/flow.py` chụp lại tối đa 4 lần. Vẫn rỗng thì lưu `logs/khong-doc-duoc-cap.png` rồi vào nhà như bảng dưới.

Quyết định:

| Đọc được | Việc làm | Cột `trang_thai` |
|---|---|---|
| Dưới 150 | Không bấm avatar, không bấm Visit | `false`, ghi chú `cấp N, dưới 150` |
| Từ 150 trở lên | Bấm avatar rồi Visit | như luồng nhận quà |
| Rỗng | Vẫn vào nhà. Log: *Không đọc được cấp, vẫn vào nhà* | như luồng nhận quà |

**Font.** Arial Bold đọc chữ **1** khoảng **0.56**, dưới ngưỡng, nên cấp có chữ 1 (131, 149, …) thành rỗng và tool vẫn Visit. Trên ảnh ADB 720×1280, chữ 9 cuối của `Lvl 299` cũng chỉ **0.637**. Malgun Bold khớp chữ trong game: chữ 1 khoảng **0.79**, chữ 9 khoảng **0.89**. Đừng đổi lại Arial, đừng cài Tesseract.

Ảnh kiểm tra: `resource/3. nhập id và tìm kiếm.png` phải đọc **299**. `py -3 -m gift_tool.self_test` dừng nếu ra số khác.

## Tự mở ô nhập UID

Hàm `_open_uid_field` trong `gift_tool/flow.py`. Chạy ở đầu lượt, và mỗi khi mất ô nhập giữa chừng. Mỗi vòng chụp một ảnh, làm **đúng một việc** theo thứ tự dưới đây, rồi chụp lại:

| Thấy gì | Việc làm |
|---|---|
| Kính lúp bên phải, không popup | Xong |
| Popup Visit, Select hoặc OK còn sót | Đóng popup |
| Nút Community (`community.png`), chưa thấy kính lúp | Panel hồ sơ đang ở tab Log hoặc Friends. Bấm tab Add New (`add_new_tab_point`) |
| Icon Bạn bè (`friends.png`) | Đang ở sân. Bấm icon để mở panel |
| Nút X điểm từ 0.80, không có gì ở trên | Đang ở Goldrush hoặc trong nhà. Bấm X, rồi **chờ X biến mất** mới làm tiếp |
| Không nhận ra | Chờ, chụp lại |

**Vì sao chờ X biến mất.** Từ Goldrush bấm X ra sân, màn cũ còn vài khung hình. Bấm X lần hai lúc đó rơi trúng nút Goldrush giữa đáy sân và vào lại Goldrush.

**Vì sao Goldrush không bị nhận là ô nhập.** Màn Goldrush có kính lúp bên **trái** (điểm 0.77, qua ngưỡng 0.72). `_uid_search` chỉ nhận kính lúp từ 55% bề ngang trở sang phải.

**Vì sao tab Add New không dùng mẫu.** Tab đang chọn sáng, tab chưa chọn tối, nên mẫu chỉ khớp một trạng thái. Vị trí tính từ Community.

Điểm khớp trên ảnh có sẵn: `friends` 1.00 ở sân, tối đa 0.64 ở màn khác. `community` tối thiểu 0.88 ở panel hồ sơ, tối đa 0.33 ở màn khác.

## Luồng một UID đang chạy

Code nằm ở `process_one` trong `gift_tool/flow.py`.

1. Phải thấy kính lúp bên phải. Không thấy thì tự mò về (xem mục *Tự mở ô nhập UID*). Mò 30 giây hoặc 8 cú bấm mà không ra thì dừng và lưu `logs/khong-nhan-ra-man.png`.
2. Bấm ô nhập, xóa chữ cũ, gõ UID, bấm kính lúp.
3. Chụp một ảnh. Thấy chữ Results và nút Add ngay bên dưới thì đọc nhãn Lvl trên hàng đó.
4. Cấp dưới 150 thì ghi **false** và sang UID sau, không bấm avatar. Cấp từ 150 trở lên, hoặc không đọc được cấp, thì bấm avatar bên trái nút Add.
5. Không thấy hàng Results thì ghi **ID sai** và sang UID sau. Không bấm dòng *Players you may know*.
6. Thấy Visit thì bấm. Ảnh sau đó vẫn còn Visit thì bấm thêm một lần.
7. Trong nhà: thấy hộp quà hoặc đã hiện Select thì nhận quà (bấm quà, Select, OK). Không thấy thì bấm X và ghi **không có quà**.
8. Sau OK, bấm X cho đến khi thấy lại kính lúp. Không thấy lại thì dừng cả lượt.

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
| `requirements.txt` | `opencv-python-headless`, `numpy`, `pillow` |

Python đang dùng là 3.13 (`py -3`). Thư viện đã cài cho bản Python đó.

## Rủi ro

Game có thể coi đây là thao tác tự động và khóa tài khoản. Chạy chậm không biến việc này thành an toàn. Lần thử nên dùng tài khoản phụ.
