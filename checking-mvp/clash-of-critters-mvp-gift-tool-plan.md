# Plan xây dựng tool nhận quà MVP – Clash of Critters

> Plan này bám file yêu cầu `clash-of-critters-mvp-gift-tool-requirements.md`.
> Làm tuần tự từng giai đoạn. Chỉ sang giai đoạn sau khi giai đoạn trước đạt tiêu chí kiểm tra.
> Chưa code cho đến khi xong giai đoạn 0 và đã chốt các điểm còn mở ở cuối file.

---

## 1. Mục tiêu

Xây dựng tool trên Windows tự làm chuỗi thao tác lặp lại trong game mobile **Clash of Critters** (chạy trong emulator Android):

Với mỗi ID trong danh sách (khoảng 50 ID mỗi lượt):

1. Từ màn hình chính, bấm icon **Bạn bè**.
2. Nhập ID vào ô tìm kiếm.
3. Bấm avatar ở hàng kết quả.
4. Bấm **Thăm qua**.
5. Chờ game vào nhà người chơi.
6. Nếu có **hộp quà** ở giữa màn hình: bấm nhận quà, rồi bấm một trong hai nút cảm ơn.
7. Nếu không có hộp quà: bỏ qua nhận quà và cảm ơn.
8. Thoát nhà, sang ID kế tiếp.

Quy tắc thêm:

- Đếm số nhà đã nhận quà. Đủ **20** thì dừng.
- ID không tồn tại: game báo *"vui lòng kiểm tra tên người chơi hoặc id người chơi và thử lại"*, hàng kết quả giữ nguyên nội dung cũ. Tool ghi log và bỏ qua. Không được kết luận ID hợp lệ chỉ vì vẫn thấy avatar.
- Có nút Bắt đầu, Dừng, ô dán danh sách ID, nạp file `.txt`, tiến độ, vùng log.
- Điều khiển emulator qua ADB để không chiếm chuột và bàn phím thật.
- Mỗi ID một dòng log, cuối lượt có tổng kết.

---

## 2. Cách nhìn cho lập trình viên web

Tool này không có DOM và không có API game. “Phần tử” trên màn hình là một vùng ảnh. Chuỗi thao tác giống một bài test giao diện.

| Việc đã quen trên web | Việc tương ứng trong tool |
|---|---|
| `element.click()` | Lệnh ADB bảo emulator chạm một điểm |
| `waitForSelector` | Chụp màn hình, tìm ảnh mẫu đến khi thấy hoặc hết giờ |
| Wizard nhiều bước | Máy trạng thái: mỗi màn hình là một trạng thái |
| Log request | File kết quả từng ID |

ADB là kênh điều khiển của Android, giống một API gửi vào máy ảo. Chuột và bàn phím Windows vẫn dùng bình thường trong lúc tool chạy.

---

## 3. Công nghệ

### 3.1 Lựa chọn

| Hạng mục | Chọn | Lý do |
|---|---|---|
| Ngôn ngữ | Python 3 | OpenCV, gọi ADB và GUI nút bấm cài ít bước. Hợp giai đoạn đang học cách đọc màn hình. |
| Nhận diện màn hình | OpenCV, so khớp ảnh mẫu | Cắt một mảnh nút, tìm mảnh đó trong ảnh chụp. Đủ cho nút và câu báo lỗi cố định. |
| Điều khiển | ADB (`screencap`, `input tap`, `input text`) | Gửi lệnh thẳng vào emulator, không kéo chuột Windows. |
| Emulator | LDPlayer 9 | Có ADB, khóa được độ phân giải. Một cửa sổ là đủ. |
| Giao diện | Tkinter (có sẵn với Python) | Nút, ô dán, vùng log. Chưa cần framework web. |
| Log | CSV + vùng log trên GUI | Mở bằng Excel được, đồng thời nhìn trực tiếp lúc chạy. |

Java vẫn làm được về sau nếu muốn giữ một ngôn ngữ với Spring. Giai đoạn học này dùng Python để thời gian nằm ở việc hiểu tool, không nằm ở việc dựng thư viện.

OCR (đọc chữ trên ảnh) để dành cho lúc ảnh mẫu của thông báo lỗi không còn khớp. Bản đầu không dùng OCR.

### 3.2 Cấu hình emulator khóa cứng

Mọi ảnh mẫu gắn với cấu hình này. Đổi độ phân giải là phải cắt lại ảnh mẫu.

| Mục | Giá trị |
|---|---|
| Số giả lập | 1 |
| Độ phân giải | 720×1280, kiểu phone, màn dọc |
| DPI | Cố định, không để tự đổi theo cửa sổ |
| CPU / RAM giả lập | 4 nhân, 4 GB (máy thật 32 GB) |
| Ngôn ngữ game | Tiếng Anh trên các ảnh đã gửi (Mall, Friends, Enter a player UID). Câu báo lỗi sẽ chụp theo đúng chữ game hiện ra, không dùng câu tiếng Việt trong file yêu cầu. |

### 3.3 Khung chương trình

Giữ nguyên từ giai đoạn 3 đến giai đoạn 5. Giao diện chỉ gọi vòng lặp.

```
GUI (dán ID, nạp txt, Bắt đầu, Dừng, tiến độ, log)
  -> Runner (vòng lặp ID, bộ đếm quà, độ trễ, dừng)
       -> Flow (máy trạng thái của một ID)
            -> Vision (tìm ảnh mẫu trên ảnh chụp)
            -> GameClient (ADB: chụp màn hình, tap, nhập chữ)
       -> Logger (một dòng CSV mỗi ID, tổng kết cuối lượt)
```

---

## 4. Luồng một ID

Đã đối chiếu với ảnh trong thư mục project. Tab **Friends** không dùng. Ô tìm người chơi nằm ở tab **Add New**.

```
Màn chính (tab pinball)
  -> Icon Bạn bè (phía trên nút Camp, cách thêm một icon)
  -> Ô "Enter a player UID."
  -> Nhập ID, bấm nút kính lúp
  -> Kiểm tra kết quả
       -> ID sai: ghi log, sang ID sau
       -> ID hợp lệ: bấm avatar của người đó
            -> Thẻ profile hiện ra (có nút Add, Invite, Visit)
            -> Chỉ bấm nút Visit màu xanh lá. Không bấm Add hay Invite.
            -> Chờ vào nhà (tối đa 15 giây)
                 -> Hết giờ: ghi lỗi-timeout, thoát, sang ID sau
                 -> Vào được nhà:
                      -> Có hộp quà: nhận quà, bấm một nút cảm ơn, cộng bộ đếm
                      -> Không có hộp quà: ghi không có quà
                 -> Thoát nhà
                 -> Về trạng thái sẵn sàng cho ID tiếp theo
```

Đủ 20 quà thì dừng cả lượt, kể cả còn ID trong danh sách.

### 4.1 Nhận ra ID sai

Làm cả hai việc, vì hàng kết quả không đổi khi ID sai:

1. Tìm ảnh mẫu của thông báo *"vui lòng kiểm tra tên người chơi hoặc id người chơi và thử lại"*.
2. So ảnh hàng kết quả trước và sau khi nhập. Nội dung không đổi cộng với có thông báo thì kết luận ID sai.

Không dùng “còn thấy avatar” làm dấu hiệu ID đúng.

### 4.2 Mặc định khi chưa có thêm thông tin

Các mặc định này đang dùng để thiết kế. Nếu câu trả lời ở mục 7 khác, sửa lại trước khi code giai đoạn 3.

| Tình huống | Cách xử lý |
|---|---|
| Chờ vào nhà quá 15 giây | Ghi `lỗi-timeout`, thoát, sang ID sau |
| Không thấy nút mong đợi | Thử lại một lần. Vẫn thất bại thì ghi `lỗi-timeout` hoặc lỗi bước đó, bỏ qua ID, không dừng cả lượt |
| Thoát nhà | Xác minh ở giai đoạn 1. Ưu tiên nút thoát trong game nếu có vị trí ổn định |
| Log | Hiện trên giao diện và ghi file CSV |
| Bộ đếm 20 | Tính trong một lượt chạy |
| ID nhập vào | Giả định là chuỗi số. `adb shell input text` nhập số ổn định. Ký tự đặc biệt xử lý sau nếu ID thực tế có |

---

## 5. Các giai đoạn

### Giai đoạn 0 — Game chạy ổn định trong emulator

Ước lượng: khoảng nửa buổi.

Việc làm:

1. Cài LDPlayer 9.
2. Tạo một giả lập, đặt 720×1280 (phone, màn dọc), DPI cố định, 4 nhân, 4 GB RAM.
3. Cài Clash of Critters.
4. Đăng nhập bằng **tài khoản phụ**.
5. Vào được màn hình chính.
6. Tắt rồi mở lại emulator, kiểm tra độ phân giải không bị đổi.

Đạt khi: game vào được nhà của mình, độ phân giải vẫn 720×1280 sau khi tắt mở.

Chưa cần Python, chưa cần ADB.

### Giai đoạn 1 — Bấm và chụp bằng ADB

Ước lượng: một buổi.

Việc làm:

1. Cài Android Platform-Tools, thêm `adb` vào PATH.
2. Bật gỡ lỗi ADB trong LDPlayer, chạy `adb devices` và thấy emulator.
3. Chụp màn hình ra một file PNG.
4. Chạm thử icon Bạn bè bằng `adb shell input tap`.
5. Ghi lại tọa độ vài nút chính để đối chiếu sau này, dù bản chính sẽ bấm theo ảnh mẫu.
6. Quan sát cách thoát khỏi nhà người chơi: nút trong game hay nút Back của Android.

Đạt khi:

- File PNG đúng màn hình game.
- Cú chạm trúng icon Bạn bè.
- Con trỏ chuột Windows không bị kéo.

Lệnh sẽ dùng lúc làm việc cùng nhau, chưa ghi cứng tọa độ vào plan vì chưa có ảnh màn hình.

### Giai đoạn 2 — Python tìm một nút trên ảnh

Ước lượng: một đến hai buổi.

Việc làm:

1. Cài Python 3, tạo virtualenv trong project.
2. Cài OpenCV.
3. Viết một script: chụp màn hình, tìm ảnh mẫu icon Bạn bè, gửi tap vào tâm vùng tìm được.
4. Cắt ảnh mẫu các màn chính và để trong thư mục riêng, đặt tên rõ:
   - icon Bạn bè
   - ô tìm kiếm
   - hàng kết quả (để so trước / sau)
   - avatar trong hàng kết quả
   - nút Thăm qua
   - hộp quà ở giữa màn hình
   - một nút cảm ơn
   - nút thoát nhà
   - thông báo ID sai
5. Chọn ngưỡng khớp ảnh (thường bắt đầu quanh 0.8) và ghi lại ngưỡng nào ổn với từng mẫu.

Đạt khi: script tự tìm và bấm icon Bạn bè dù icon lệch nhẹ so với lần cắt mẫu. Chuột Windows vẫn không bị chiếm.

Đây là lúc cần ảnh chụp từng bước. Chưa có ảnh thì dừng ở việc cài Python và script chụp màn hình.

### Giai đoạn 3 — Xử lý trọn một ID

Ước lượng: vài buổi. Đây là phần khó nhất.

Việc làm:

1. Dựng máy trạng thái theo mục 4.
2. Nhập ID qua ADB.
3. Phân biệt ID sai bằng thông báo và bằng ảnh hàng kết quả trước / sau.
4. Chờ vào nhà, timeout 15 giây.
5. Nhánh có quà và nhánh không có quà.
6. Thoát nhà và xác nhận đã về màn hình sẵn sàng cho ID sau.
7. Ghi một dòng log tạm cho ID vừa chạy.

Đạt khi, trên tài khoản phụ, cả ba ca đều đúng:

- Một ID có quà: nhận quà, bấm được một nút cảm ơn, thoát nhà.
- Một ID không có quà: không bấm nhận quà, thoát nhà.
- Một ID sai: không bấm vào hàng kết quả cũ, log ghi ID sai.

### Giai đoạn 4 — Danh sách, giới hạn 20, file log

Việc làm:

1. Đọc danh sách ID từ ô văn bản hoặc file `.txt` (một ID một dòng).
2. Lặp từng ID, gọi flow giai đoạn 3.
3. Bộ đếm nhà đã nhận quà. Đủ 20 thì dừng.
4. Độ trễ ngẫu nhiên ngắn giữa các cú chạm, và một khoảng nghỉ ngắn giữa hai ID.
5. Nút dừng được kiểm tra giữa các ID (và giữa các bước dài như chờ load).
6. CSV gồm các cột: `id`, `trang_thai`, `thoi_gian_xu_ly`.
7. `trang_thai` chỉ dùng bốn giá trị: `da_nhan_qua`, `khong_co_qua`, `id_sai`, `loi_timeout`.
8. Cuối lượt in tổng: số quà đã nhận, số ID không có quà, số ID sai, số ID lỗi.

Đạt khi:

- Chạy thử 5 ID, file CSV khớp những gì nhìn thấy trên game.
- Bộ đếm dừng đúng ở mốc 20 khi đã nhận đủ (có thể thử bằng danh sách toàn ID đang có quà, hoặc tạm hạ mốc xuống 2 để kiểm tra logic dừng).
- Bấm dừng thì không sang ID mới.

### Giai đoạn 5 — Giao diện nút bấm

Việc làm:

1. Cửa sổ Tkinter: ô dán danh sách, nút nạp `.txt`, Bắt đầu, Dừng.
2. Dòng tiến độ: đang xử lý ID nào, đã nhận bao nhiêu trên 20.
3. Vùng log cuộn được, cùng nội dung với file CSV.
4. Bắt đầu thì khóa nút Bắt đầu, bật nút Dừng. Hết lượt hoặc bấm Dừng thì ngược lại.
5. Chạy vòng lặp ở luồng nền để cửa sổ không bị đơ.

Đạt khi: bấm Dừng thì lượt chạy kết thúc ở ID kế tiếp, không cần tắt cửa sổ dòng lệnh. Dán ID hoặc nạp file đều chạy được cùng một flow.

---

## 6. Rủi ro tài khoản

Game có thể coi chuỗi thao tác tự động là vi phạm và khóa tài khoản. Chạy chậm và thêm độ trễ ngẫu nhiên chỉ làm nhịp bấm bớt đều. Điều đó không biến tool thành thứ an toàn với tài khoản.

Cách giảm thiệt hại khi đang học:

- Mọi thử nghiệm giai đoạn 0 đến 3 dùng tài khoản phụ.
- Có chế độ chạy thử ít ID trước khi đưa cả danh sách 50.
- Giới hạn tốc độ, có khoảng nghỉ giữa các thao tác.
- Chỉ chạy tài khoản chính sau khi tự chấp nhận rủi ro khóa acc.

Plan này không gồm cách né hệ thống phát hiện của game.

---

## 7. Điểm cần chốt trước khi code giai đoạn 3

Bốn điểm dưới đây đổi thiết kế nếu khác các mặc định ở mục 4.2.

1. Tài khoản định chạy hằng ngày là acc phụ hay acc chính?
2. Giới hạn 20 quà của game reset theo ngày, hay chỉ là trần muốn đặt cho mỗi lượt chạy? Khi game chạm trần, màn hình báo gì?
3. Thoát nhà bằng nút nào trong game, hay bằng nút Back của Android?
4. Ảnh từng màn: Bạn bè, ô nhập ID, hàng kết quả, Thăm qua, hộp quà, hai nút cảm ơn, nút thoát, thông báo ID sai. Cần lúc vào giai đoạn 2.

Timeout 15 giây, log CSV và cách bỏ qua ID khi lỗi một bước đang giữ làm mặc định.

---

## 8. Việc làm tiếp theo

Game đã vào được màn chính trên LDPlayer. Ảnh đã có: màn pinball, màn nhập UID, thẻ profile với nút Visit. Tab Friends bỏ qua.

Việc còn lại trước giai đoạn 1: khóa 720×1280 rồi tắt mở lại emulator. Bấm Visit một lần, chụp màn nhà người chơi, cả lúc có hộp quà và lúc không có nếu làm được. Xong thì sang giai đoạn 1 (ADB chụp màn hình và tap thử).
