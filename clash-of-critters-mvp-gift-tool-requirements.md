# Yêu cầu tool tự động nhận quà MVP – Clash of Critters

> File này mô tả nhu cầu của người dùng để AI khác lập kế hoạch (plan) xây dựng tool.
> Phần **"Thông tin người dùng đã xác nhận"** là dữ kiện chắc chắn. Phần **"Gợi ý kỹ thuật sơ bộ"** chỉ là gợi ý tham khảo, AI lập plan có thể đề xuất hướng khác. Phần **"Thông tin còn thiếu"** cần hỏi lại người dùng trước khi code.

---

## 1. Mục tiêu

Xây dựng tool tự động hóa một chuỗi thao tác lặp đi lặp lại trong game mobile **Clash of Critters**: ghé nhà từng người chơi trong danh sách ID, nhận quà MVP nếu có, gửi lời cảm ơn rồi thoát ra, lặp lại cho ID kế tiếp.

## 2. Về người dùng

- Tên: Trường. Giao tiếp bằng tiếng Việt, văn phong thân mật.
- Là lập trình viên, quen **Java (Spring Boot), phát triển web (Next.js/React), Oracle Database, Kubernetes, Jenkins**.
- **Chưa từng làm tool tự động hóa game** (đọc màn hình, giả lập thao tác bấm), chưa từng cài emulator.
- Sẵn sàng dùng ngôn ngữ khác Java nếu phù hợp hơn cho việc viết tool.
- Cách học ưa thích: giải thích thực tế, từng bước, có ví dụ/so sánh; không thích nhận quá nhiều thông tin một lúc. Plan nên chia thành các bước nhỏ, kiểm chứng được từng bước.

## 3. Thông tin người dùng đã xác nhận

### 3.1 Môi trường

| Hạng mục | Chi tiết |
|---|---|
| Game | Clash of Critters (mobile) |
| Nền tảng chạy game | Emulator Android trên PC |
| Hệ điều hành PC | Windows |
| RAM | 32 GB |
| Emulator | Chưa cài. Chấp nhận loại nào miễn **hiệu quả** (AI lập plan đề xuất) |
| Độ phân giải emulator | Chưa biết (có thể cấu hình theo yêu cầu của tool) |
| Ngôn ngữ giao diện game | Tiếng Việt (các thông báo trong game bằng tiếng Việt) |

### 3.2 Luồng thao tác cần tự động hóa (cho MỖI ID)

1. Từ màn hình chính, bấm **icon Bạn bè**.
2. **Nhập ID người chơi** vào ô tìm kiếm.
3. Bấm vào **avatar** ở hàng kết quả.
4. Bấm nút **Thăm qua**.
5. **Chờ game điều hướng** vào nhà người chơi (load).
6. Nếu thấy **biểu tượng hộp quà** (nằm **chính giữa màn hình** khi có quà):
   - Bấm vào để **nhận quà**.
   - Xuất hiện **2 nút cảm ơn**, chỉ cần bấm **một nút bất kỳ** trong hai.
7. **Thoát khỏi nhà** người chơi này.
8. Quay lại bước 1–2 với ID kế tiếp.

Nếu **không có hộp quà**: thoát ra luôn (bỏ qua bước nhận quà và cảm ơn).

### 3.3 Quy tắc nghiệp vụ

- **Giới hạn nhận quà: tối đa 20 hộp quà.** Tool phải có **bộ đếm số nhà có quà (đã nhận)**; khi đạt 20 thì dừng.
- Không có popup nào chen ngang trong quá trình chạy (theo người dùng).
- Thời gian load vào nhà **khá ổn định, thường không quá 10 giây**; tuy nhiên đôi khi vẫn có thể lag.

### 3.4 Xử lý ID sai

- Khi nhập ID không tồn tại, game hiện thông báo: **"vui lòng kiểm tra tên người chơi hoặc id người chơi và thử lại"**.
- Lúc này **hàng kết quả (tên người chơi, cấp độ, avatar) không thay đổi** so với trước đó.
- Yêu cầu: **bỏ qua ID sai**, ghi log rồi chuyển sang ID tiếp theo.
- Lưu ý cho plan: vì hàng kết quả giữ nguyên nội dung cũ, **không được dựa vào việc "có avatar" để kết luận ID hợp lệ**. Cần nhận diện thông báo lỗi hoặc so sánh hàng kết quả trước/sau khi nhập.

### 3.5 Đầu vào

- Danh sách ID người chơi, khoảng **50 ID mỗi lần chạy**.
- Chạy **theo nhu cầu**, khi người dùng đưa danh sách ID mới (không có lịch cố định).
- Nguồn danh sách: người dùng tự cung cấp mỗi lần.

### 3.6 Đầu ra

- **File/bảng log kết quả** cho từng ID, tối thiểu gồm: ID, trạng thái (đã nhận quà / không có quà / ID sai / lỗi-timeout), thời gian xử lý.
- Tổng kết cuối lượt chạy: số quà đã nhận, số ID không có quà, số ID sai, số ID lỗi.

### 3.7 Giao diện

- Người dùng muốn **giao diện có nút bấm** (GUI), trong đó có thể **nhập/dán danh sách ID** (và nên hỗ trợ nạp từ file txt nếu tiện).
- Nên có: nút Bắt đầu, nút Dừng, hiển thị tiến độ (đang xử lý ID nào, đã nhận bao nhiêu/20), vùng hiển thị log.

### 3.7b Vừa chạy vừa dùng máy

- Người dùng thường **không dùng máy** lúc tool chạy, nhưng **muốn có khả năng vẫn dùng máy bình thường** nếu cần.
- Ưu tiên hướng điều khiển emulator **không chiếm chuột/bàn phím thật** (ví dụ qua ADB), để không bị gián đoạn.

## 4. Rủi ro đã trao đổi

- Game có thể **cấm hoặc phát hiện hành vi tự động hóa** và khóa tài khoản. Người dùng **chưa cân nhắc rủi ro này** từ trước và cho rằng "thao tác chậm một chút thì không sao". Điều này **chưa được đảm bảo**: chạy chậm và thêm độ trễ ngẫu nhiên chỉ giúp giảm rủi ro, không loại bỏ.
- Chưa biết acc game quan trọng đến mức nào (nên hỏi lại).
- Kiến nghị cho plan: có chế độ **chạy thử với ít ID**, độ trễ ngẫu nhiên giữa các thao tác, giới hạn tốc độ, và nhắc người dùng cân nhắc dùng acc phụ để thử.

## 5. Gợi ý kỹ thuật sơ bộ (không bắt buộc)

- **Emulator** hỗ trợ ADB và cho đặt độ phân giải cố định (ví dụ LDPlayer, BlueStacks, MuMu). Cố định độ phân giải/DPI để toạ độ và ảnh mẫu ổn định.
- **Điều khiển** bằng **ADB** (lệnh tap, chụp màn hình) để vừa ổn định vừa không chiếm chuột.
- **Nhận diện màn hình**: so khớp ảnh mẫu (template matching, ví dụ OpenCV) cho hộp quà, nút Thăm qua, thông báo lỗi ID; hoặc OCR tiếng Việt cho thông báo lỗi.
- **Ngôn ngữ**: Python là lựa chọn phổ biến cho loại tool này (hệ sinh thái ADB/OpenCV phong phú, GUI đơn giản với Tkinter/PySide). Người dùng quen Java nên có thể cân nhắc Java nếu muốn, nhưng cần so sánh độ thuận tiện. Do người dùng chưa có kinh nghiệm, plan nên ưu tiên **công cụ dễ học, ít cài đặt**.
- Nên thiết kế theo từng giai đoạn nhỏ: (1) cài emulator + kết nối ADB, (2) chụp màn hình + bấm thử, (3) tự động hóa 1 ID, (4) vòng lặp nhiều ID + log, (5) GUI.

## 6. Thông tin còn thiếu (cần hỏi người dùng khi lập plan)

1. **Ảnh chụp màn hình** từng bước: icon Bạn bè, ô nhập ID, hàng kết quả, nút Thăm qua, hộp quà, 2 nút cảm ơn, nút thoát nhà, thông báo ID sai. (Người dùng chưa cung cấp.)
2. **Giới hạn 20 quà**: reset theo ngày hay theo chu kỳ nào? Khi chạm giới hạn game báo gì? Giới hạn tính theo tài khoản hay theo lượt chạy?
3. **Timeout khi lag**: người dùng nói thường không quá 10 giây nhưng chưa chốt ngưỡng chờ tối đa. Gợi ý ban đầu: chờ tới khoảng 15 giây rồi bỏ qua/thoát (chưa được người dùng xác nhận).
4. **Cách thoát nhà**: nút nào, vị trí nào, hay dùng nút Back của Android?
5. **Xử lý khi thất bại giữa chừng**: nếu một bước không tìm thấy nút mong đợi (ngoài trường hợp ID sai và lag), tool nên thử lại, bỏ qua ID, hay dừng hẳn?
6. **Emulator và độ phân giải**: chưa chọn; người dùng cần hướng dẫn cài đặt từng bước.
7. **Mức quan trọng của tài khoản game** và mức chấp nhận rủi ro bị phát hiện.
8. **Định dạng log mong muốn** (txt, CSV hay hiển thị trong GUI) và nơi lưu.

## 7. Yêu cầu đối với kế hoạch (plan) mong muốn

- Chia theo giai đoạn nhỏ, mỗi giai đoạn có tiêu chí kiểm tra rõ ràng.
- Có hướng dẫn **cài đặt môi trường từ đầu** (emulator, ADB, ngôn ngữ/thư viện), vì người dùng chưa có kinh nghiệm.
- Giải thích lý do chọn công nghệ bằng ngôn ngữ dễ hiểu, ưu tiên cách làm thực tế, kiểm chứng bằng kết quả chạy thật.
- Nêu rõ rủi ro và cách giảm thiểu (xem mục 4).
