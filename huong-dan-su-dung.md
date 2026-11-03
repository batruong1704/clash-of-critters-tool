# Hướng dẫn dùng tool nhận quà MVP

Tool tự vào nhà từng UID trong Clash of Critters, nhận hộp quà MVP nếu có, rồi sang UID tiếp theo. Game chạy trong LDPlayer. Chuột máy tính vẫn dùng được trong lúc tool chạy.

## Trước khi mở tool

1. Mở LDPlayer, vào Clash of Critters, để màn hình **dọc**.
2. Mở tab **Add New**, thấy ô nhập UID và kính lúp bên phải.
3. Lần đầu nên dùng **tài khoản phụ** và chỉ dán **1–2 UID**. Game có thể khóa tài khoản nếu phát hiện thao tác tự động.

ADB trong LDPlayer phải bật: Cài đặt giả lập → mục Khác → **Gỡ lỗi ADB**. Nếu quên, bấm **Chụp thử** trong tool. Tool có thể tắt rồi mở lại giả lập một lần. Sau đó vào lại game và mở lại tab Add New.

## Mở tool

Double-click `run.bat` trong thư mục này.

Hoặc mở terminal tại thư mục tool và chạy:

```bat
py -3 main.py
```

Lần đầu trên máy mới, cài thư viện:

```bat
py -3 -m pip install -r requirements.txt
```

## Các nút

| Nút | Việc |
|---|---|
| Chụp thử | Kiểm tra đã nối được emulator. Ảnh lưu ở `logs/chup-thu.png` |
| Kiểm tra nút | Khoanh các nút tool đang thấy, mở ảnh `logs/kiem-tra.png` |
| Nạp file txt | Đọc UID từ file, mỗi dòng một UID |
| Dừng sau số quà | Trần số quà của lượt này, tối đa 20 |
| Bắt đầu | Chạy danh sách |
| Dừng | Dừng sau bước đang làm |

Dòng `search: thấy` trong Kiểm tra nút nghĩa là tool đang nhìn đúng ô tìm UID. Chưa thấy thì đừng bấm Bắt đầu.

## Danh sách UID

Mỗi dòng một UID, chỉ gồm chữ số, dài từ 4 đến 15 số. Có thể dán nhiều dòng, hoặc cách nhau bởi dấu phẩy. Dòng không phải số sẽ bị bỏ qua và hiện trong log.

Ví dụ:

```text
42276157
231886640
```

## Tool làm gì với mỗi UID

1. Gõ UID vào ô tìm và bấm kính lúp.
2. Có hàng **Results** thì bấm avatar, rồi bấm **Visit**.
3. Trong nhà có hộp quà vàng ở giữa thì bấm nhận, chọn một nút **Select**, rồi **OK**.
4. Không có hộp quà thì bấm **X** để ra.
5. Không thấy người chơi thì bỏ qua UID đó.
6. Đủ số quà đã đặt, hoặc hết danh sách, thì dừng.

## Đọc kết quả

Log hiện ngay trên cửa sổ. Cùng nội dung được ghi vào `logs/ket-qua-ngày-giờ.csv`. Mở bằng Excel được.

| Trạng thái | Nghĩa |
|---|---|
| đã nhận quà | Đã bấm Select và OK |
| không có quà | Vào nhà nhưng không thấy hộp quà |
| ID sai | Không thấy người chơi với UID đó |
| lỗi / timeout | Kẹt một bước, ví dụ không thấy Visit hoặc không thấy lại ô tìm |

Cuối lượt, log có dòng tổng bốn trạng thái trên.

Nếu tool báo không thấy lại ô nhập UID, nó dừng để khỏi bấm nhầm. Mở lại tab Add New, rồi chạy tiếp những UID chưa xử lý.

## Khi sửa xong code hoặc ảnh mẫu

Tắt hẳn cửa sổ tool rồi mở lại `run.bat`. Cửa sổ đang mở vẫn giữ ảnh mẫu cũ trong bộ nhớ.
