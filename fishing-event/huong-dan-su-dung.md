# Tự câu cá (Fishing Contest)

Tool điều khiển game trong **LDPlayer 9** (màn dọc 720×1280) qua ADB, giống tool nhận quà ở `checking-mvp`. Không chiếm chuột Windows. Dùng chung `adb_client.py` và hàm đọc chữ số của `checking-mvp/gift_tool`.

## Chạy

1. Mở LDPlayer, bật **Gỡ lỗi ADB** (Cài đặt, mục Khác) như tool nhận quà.
2. Mở game. Đang ở sân, màn Pinball hay màn Fishing Contest đều được. Tool tự đi từ sân: Pinball, ô Fishing Contest.
3. Mở giao diện chung (`py main.py` trong thư mục `checking-mvp`), chọn tab **Tự câu cá**. Nhập **Số lượt câu** và **Hệ số** (để trống là x1) rồi bấm **Bắt đầu**.
4. Bấm **Dừng** để dừng ngay. Tiến độ (lượt, thành công, hết giờ, Gold, rod còn) hiện ở dòng trạng thái, chi tiết ở khung nhật ký.

Không bấm vào emulator khi tool đang chạy.

Chạy dòng lệnh (không mở cửa sổ): `py -3 tools/run_live.py <số_lượt> <hệ_số>`.

## Thông số

- **Số lượt câu**: tool quăng đủ N lần (mỗi lần quăng tính một lượt) rồi dừng. Hết rod thì dừng sớm.
- **Hệ số**: x1, x2, x3, x5, x10, x20, x50, x100 (đúng vòng đổi hệ số của tài khoản này, bấm viên hệ số là sang số kế, sau x100 về x1). Để trống là x1. Tool tự bấm viên hệ số cho tới khi đúng số đã nhập. x200 có trong danh sách nhưng chưa thấy trong vòng đổi của game, và chưa có ảnh mẫu `templates/mult_200.png` nên tool từ chối chạy với x200 (không đoán mò).

## Một lượt chạy thế nào

| Màn | Nhận ra bằng | Việc tool làm |
|---|---|---|
| Chờ quăng | Nút câu **xanh lá** | Kiểm hệ số, đọc số rod, bấm nút câu |
| Chờ cá cắn | Nút **xám** | Chờ |
| Reel it in | Nút tím và bảng tím "Now! Reel it in!" | Bấm nút tím một lần |
| Thanh trượt | Nút tím, thanh tối có vùng vàng và mồi đỏ | Dò tốc độ mồi, bấm khi mồi vào giữa vùng vàng. Trượt thì bấm lại. Có thể 0, 1 hoặc nhiều thanh liên tiếp |
| Time's up | Băng cam giữa màn | Ghi hết giờ, chờ game tự về |
| Kết quả | Nút câu **tối** | Đọc Gold (hiện thoáng khi phá kỷ lục), ghi lượt thành công, rồi bấm bỏ qua |

Cá nhỏ chỉ cần bấm Reel it in là lên, không có thanh trượt. Cá hiếm hơn mới có một hoặc vài thanh, vùng vàng hẹp và mồi chạy nhanh hơn.

## Kết quả

- Cửa sổ có số lượt, số cá thành công, số lần hết giờ, số lần bấm thanh trượt, tổng Gold, rod còn lại.
- `logs/cau-ca-<giờ>.csv`: mỗi lượt một dòng (`luot`, `ket_qua`, `bac`, `vang`, `so_lan_bam`, `giay`). `ket_qua` là `thanh_cong`, `het_gio` hoặc `khong_ro`.
- `logs/cau-ca-<giờ>-vet.txt`: vết thời gian từng mẫu mồi và từng cú bấm. Dùng khi cần chỉnh lại độ trễ.
- Ảnh `logs/cau-ca-ketqua-N.png` (12 ảnh đầu mỗi lần chạy) để đối chiếu khi số Gold đọc sai.

## Điểm cần biết

- **Rod.** Hệ số xN tốn N rod mỗi lần quăng (đo: x2 từ 81 xuống 79). Còn ít hơn N rod thì tool dừng.
- **Bấm bỏ qua màn kết quả.** Bấm giữa màn hay chỗ `(360, 900)` không đóng được màn "New Team Record". Bấm `(130, 1100)` (bên trái nút câu đang tối) thì đóng, và không rơi vào nút câu. Bấm `(360, 1100)` cũng đóng nhưng nếu màn đã đóng sẵn thì cú bấm đó quăng thêm một lần, nên chỉ là phương án cuối.
- **Màn "Rewards!"** cũng là màn kết quả của cá thường (cá không cần trượt). Tool tính một lượt thành công khi thấy màn tối sau khi cần đã được quăng. Popup khác chen vào lúc cần chưa quăng thì không tính lượt.
- **Cần quăng ngoài tool.** Nếu tool thấy cần đã quăng mà nó không bấm (bắt đầu giữa chừng), nó tính thêm một lượt và câu tiếp bình thường.
- **Độ chính xác đã đo trên máy thật** (3 lần chạy, hơn 20 cú bấm thanh trượt): khoảng 65% trúng ngay lần đầu, phần còn lại trúng sau 1–2 lần bấm lại. Cá có 4–5 thanh liên tiếp đôi khi hết 30 giây.
- **Gold.** Gold hiện chưa tới một giây khi phá kỷ lục, nên tool chụp thêm vài ảnh trước khi bấm bỏ qua. Số Gold từ 10 trở lên được nhận ngay cả khi chỉ kịp đọc trên một ảnh. Tool chỉ đọc chữ vàng +Gold, không lấy số trắng cạnh đồng xu bạc. Một chữ số lẻ chỉ nhận khi thấy ở hai ảnh, để bỏ tia sáng đọc nhầm. Tool không còn đọc Silver.
- **Độ trễ khi bấm thanh trượt.** Mỗi lần chụp mất khoảng 0.45 giây, bấm qua ADB mất thêm vài phần mười giây. Tool ghi vài mẫu vị trí mồi, tính tốc độ (sóng tam giác nảy ở hai đầu thanh) rồi bấm trước một nhịp. Đo trên máy thật cần bấm muộn hơn tính toán khoảng 0.25 giây (`BASE_BIAS` trong `fishing_tool/flow.py`). Trượt thì tool thử lệch ±0.05 giây và nhớ độ lệch vừa trúng.
- **Phẩm chất cao.** Mồi chạy nhanh và vùng vàng hẹp thì tỉ lệ trúng giảm. Trượt chỉ trừ thời gian, hết 30 giây là mất cá.
- Tool dừng và báo lý do khi: không nhận ra màn hình quá lâu (thường là popup), bấm quăng ba lần mà không phản hồi, không đổi được hệ số, hết rod.

Rủi ro: game có thể coi đây là thao tác tự động và khóa tài khoản. Nên thử trên tài khoản phụ.

## Kiểm tra sau khi sửa

1. `py -3 -m fishing_tool.self_test` chạy trên ảnh và video có sẵn, không cần emulator. Phải ra `XONG`.
2. `py -3 tools/check_predictor.py` kiểm bộ đoán vị trí mồi trên video.
3. `py -3 tools/sim_flow.py 400 3` chạy vòng câu trên game giả (ảnh thật của video, mồi vẽ lại). Không đụng game.
4. Cuối cùng thử trên emulator thật, vài lượt, xem `logs/*-vet.txt`.

## Tool nhớ và học qua các phiên

Cú bấm đi từ lệnh ADB tới game mất khoảng 0.35 giây (đo trên 52 cú bấm thật). Sau mỗi cú bấm, tool biết kết quả (trúng nếu sang thanh mới hoặc hiện màn kết quả, trượt nếu vẫn thanh cũ) và biết đường đi của mồi nhờ các mẫu của thanh đó. Tool thử từng độ trễ L và hỏi "nếu cú bấm tới game sau L giây thì mồi có trong vùng vàng không", rồi giữ các L khớp với kết quả thật. Độ trễ dùng cho lần sau là L khớp với nhiều cú bấm nhất.

Dữ liệu nằm ở `data/hoc.json` (400 cú bấm gần nhất), nên càng dùng càng chuẩn và phiên sau không học lại từ đầu. Dòng đầu nhật ký cho biết độ trễ đang dùng. Xóa `data/hoc.json` để học lại.

Phân tích thủ công: `py -3 tools/phan_tich.py` tính lại tỉ lệ trúng từ các file vết, in bảng độ trễ L và độ chính xác của từng L. Thêm `--nhap` để dựng lại `data/hoc.json` từ các file vết. Chế độ mô phỏng (`tools/sim_flow.py`) không ghi vào file này.

## Thư mục

| Đường dẫn | Việc |
|---|---|
| `checking-mvp/gift_tool/gui.py` | Giao diện chung, tab **Tự câu cá** gọi `fishing_tool.flow.Runner` |
| `fishing_tool/flow.py` | Vòng câu, đọc kết quả, dò độ lệch giờ bấm |
| `fishing_tool/memory.py` | Bộ nhớ học giữa các phiên (`data/hoc.json`) |
| `fishing_tool/predictor.py` | Đoán vị trí mồi, chọn giờ bấm |
| `fishing_tool/vision.py` | Nhận màn hình, đọc thanh trượt, đọc Gold, rod, hệ số |
| `fishing_tool/device.py` | ADB: đo giờ chụp, bấm qua shell mở sẵn |
| `fishing_tool/self_test.py` | Kiểm tra nhận màn trên ảnh có sẵn |
| `templates/` | Ảnh mẫu: nút Pinball, nút Camp, ô Fishing Contest, viên hệ số |
| `tools/` | `sim_flow.py`, `check_predictor.py`, `run_live.py` |
| `resource/` | Ảnh và video mô tả game |
