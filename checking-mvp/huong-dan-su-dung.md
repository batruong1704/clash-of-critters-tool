# Hướng dẫn dùng tool nhận quà MVP

Tool tự vào nhà từng UID trong Clash of Critters, nhận hộp quà MVP nếu có, rồi sang UID tiếp theo. Game chạy trong LDPlayer. Chuột máy tính vẫn dùng được trong lúc tool chạy.

## Trước khi mở tool

1. Mở LDPlayer, vào Clash of Critters, để màn hình **dọc**.
2. Không cần mở tab **Add New** trước. Đang ở sân chính, chế độ Goldrush, hoặc panel hồ sơ sai tab thì tool tự bấm về ô nhập UID. Màn lạ thì tool dừng và lưu ảnh ở `logs/khong-nhan-ra-man.png`.
3. Lần đầu nên dùng **tài khoản phụ** và chỉ dán **1–2 UID**. Game có thể khóa tài khoản nếu phát hiện thao tác tự động.

ADB trong LDPlayer phải bật: Cài đặt giả lập → mục Khác → **Gỡ lỗi ADB**. Nếu quên, bấm **Chụp thử** trong tool. Tool có thể tắt rồi mở lại giả lập một lần. Sau đó vào lại game và mở lại tab Add New.

## Mở tool

Double-click `run.bat` ở thư mục gốc của project (cùng cấp với thư mục này). File đó mở cửa sổ chung cho mọi chức năng. Lần đầu trên máy mới, nếu chưa có Python 3.11 trở lên thì file này tự cài Python 3.13 cho tài khoản đang đăng nhập, rồi tạo một `.venv` ở thư mục gốc và cài thư viện trong `requirements.txt`. Câu cá và rally dùng chung môi trường đó. Cần có mạng. Copy sang máy khác thì mở lại `run.bat`, không cần đường dẫn của máy cũ.

Muốn chạy tay trong terminal tại thư mục tool:

```bat
..\.venv\Scripts\python.exe main.py
```

## Các nút

| Nút | Việc |
|---|---|
| Chụp thử | Kiểm tra đã nối được emulator. Ảnh lưu ở `logs/chup-thu.png` |
| Kiểm tra nút | Khoanh các nút tool đang thấy, mở ảnh `logs/kiem-tra.png` |
| Bắt đầu / Quét | Nút xanh dưới tab. Đổi theo tab đang mở |
| Nhập danh sách | Dán hoặc nạp file UID |
| Quét ID | Nhập ID đầu và số lần. Mỗi lần sau cộng thêm 1 |
| Dừng | Dừng sau bước đang làm |
| Xem chi tiết log | Mở ô log từng bước. Bấm lần nữa để ẩn |

Dòng `search: thấy` trong Kiểm tra nút nghĩa là tool đang nhìn đúng ô tìm UID. Chưa thấy thì đừng bấm Bắt đầu.

## Danh sách UID

Ở tab **Nhập danh sách**. Mỗi dòng một UID, chỉ gồm chữ số, dài từ 4 đến 15 số. Có thể dán nhiều dòng, hoặc cách nhau bởi dấu phẩy. Dòng không phải số sẽ bị bỏ qua và hiện trong log.

Ví dụ:

```text
42276157
231886640
```

## Tool làm gì với mỗi UID

1. Gõ UID vào ô tìm và bấm kính lúp.
2. Có hàng **Results** thì bấm avatar, rồi bấm **Visit**.
3. Trong nhà có hộp quà vàng ở giữa thì bấm nhận, chọn một nút **Select**, rồi **OK**.
4. Không có hộp quà thì bấm **X** một lần để ra. Không bấm X lần nữa, vì cú thứ hai đóng tab tìm kiếm và có thể đụng nút **Goldrush** ở sân.
5. Không thấy người chơi thì bỏ qua UID đó.
6. Cấp dưới 150 thì ghi **false** và không vào nhà.
7. Đủ 20 quà, hết danh sách, hoặc hết số lần quét nối tiếp, thì dừng.

## Quét ID

Mở tab **Quét ID**, điền **ID đầu** và **Số lần**, rồi bấm nút **Quét** ở thanh bên dưới. Tool không đọc ô danh sách ở tab kia. ID đầu là lượt 1, lượt sau là ID đó cộng 1. Số lần 100 nghĩa là quét 100 ID rồi dừng, kể cả ID sai và nhà không có quà. Đủ 20 quà thì dừng sớm hơn.

## Đọc kết quả

**Log tổng quan** luôn hiện bên trái, khung thấp, ghi từng UID và kết quả. **Log chi tiết** chỉ hiện khi bấm **Xem chi tiết log**, nằm bên phải và cao hơn, ghi từng bước đang làm, ví dụ gõ UID, bấm Visit, bấm hộp quà. Kết quả từng UID còn được ghi vào `logs/ket-qua-ngày-giờ.csv`. Mở bằng Excel được.

| Trạng thái | Nghĩa |
|---|---|
| đã nhận quà | Đã bấm Select và OK |
| không có quà | Vào nhà nhưng không thấy hộp quà |
| ID sai | Không thấy người chơi với UID đó |
| false | Có người chơi nhưng cấp dưới 150, không vào nhà |
| lỗi / timeout | Kẹt một bước, ví dụ không thấy Visit hoặc không thấy lại ô tìm |

Cuối lượt, log có dòng tổng bốn trạng thái trên.

Nếu tool báo không thấy lại ô nhập UID, nó dừng để khỏi bấm nhầm. Mở lại tab Add New, rồi chạy tiếp những UID chưa xử lý.

## Khi sửa xong code hoặc ảnh mẫu

Sửa code trên máy thì tắt cửa sổ rồi mở lại `run.bat`. Cửa sổ đang mở vẫn giữ ảnh mẫu cũ trong bộ nhớ.

Nút **Cập nhật** trong Cài đặt kéo bản trên GitHub về rồi tự mở lại cửa sổ, nên không cần tắt tay sau khi bấm nút đó.
