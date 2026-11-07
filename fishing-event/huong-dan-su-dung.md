# Tự câu cá (Fishing Contest)

Tool điều khiển game trong **LDPlayer 9** (màn dọc 720×1280) qua ADB, giống tool nhận quà ở `checking-mvp`. Không chiếm chuột Windows. Dùng chung `adb_client.py` và hàm đọc chữ số của `checking-mvp/gift_tool`.

## Chạy

1. Mở LDPlayer, bật **Gỡ lỗi ADB** (Cài đặt, mục Khác) như tool nhận quà.
2. Mở game. Đang ở sân, màn Pinball hay màn Fishing Contest đều được. Tool tự đi từ sân: Pinball, ô Fishing Contest.
3. Mở giao diện chung (`py main.py` trong thư mục `checking-mvp`), chọn tab **Tự câu cá**. Nhập **Số lượt câu** và **Hệ số** (để trống là x1) rồi bấm **Bắt đầu**.
4. Bấm **Dừng**. Chưa vào lượt thì dừng ngay. Đang câu dở thì câu nốt lượt đó, gồm thanh trượt và đóng màn kết quả, rồi mới dừng. Không quăng lượt mới. Lúc đó nút chuyển thành **Câu nốt**, thanh tiến độ chuyển vàng, và một dải vàng hiện "Đã dừng. Đang câu nốt con cá này." Dải này giữ đến khi lượt xong, không bị dòng trạng thái phía trên ghi đè. Tiến độ (lượt, thành công, thất bại, Gold, rod còn) hiện ở dòng trạng thái, chi tiết ở khung nhật ký. Thanh trên cùng có **Tổng**, đếm thời gian của cả phiên câu. Cột **Thời gian** trong bảng kết quả đếm riêng từng con, dạng `0:12.4`, và đứng lại khi con đó xong.

Không bấm vào emulator khi tool đang chạy.

Chạy dòng lệnh (không mở cửa sổ): `py -3 tools/run_live.py <số_lượt> <hệ_số>`.

## Thông số

- **Số lượt câu**: tool quăng đủ N lần (mỗi lần quăng tính một lượt) rồi dừng. Hết rod thì dừng sớm.
- **Hệ số**: ô chọn có x1, x2, x3, x5, x10, x20, x50. Để trống là x1. Vòng trong game còn x100 rồi quay về x1. Mỗi lần bấm viên hệ số chỉ nhảy một bậc; hệ số xN tốn N rod mỗi lần quăng, thiếu rod thì tool dừng ngay khi quăng.

## Một lượt chạy thế nào

| Màn | Nhận ra bằng | Việc tool làm |
|---|---|---|
| Chờ quăng | Nút câu **xanh lá** | Kiểm hệ số, đọc số rod, bấm nút câu |
| Chờ cá cắn | Nút **xám** | Chờ |
| Reel it in | Nút tím và bảng tím "Now! Reel it in!" | Bấm nút tím một lần |
| Thanh trượt | Nút tím, thanh tối có vùng vàng và mồi đỏ | Dò tốc độ mồi, bấm khi mồi vào giữa vùng vàng. Trượt thì bấm lại. Có thể 0, 1 hoặc nhiều thanh liên tiếp |
| Time's up | Băng cam giữa màn | Ghi thất bại, chờ game tự về |
| Kết quả | Nút câu **tối** | Đọc Gold (hiện thoáng khi phá kỷ lục), ghi lượt thành công, rồi bấm bỏ qua |

Cá nhỏ chỉ cần bấm Reel it in là lên, không có thanh trượt. Cá hiếm hơn mới có một hoặc vài thanh, vùng vàng hẹp và mồi chạy nhanh hơn.

## Kết quả

- Cửa sổ có số lượt, số cá thành công, số lần thất bại, tổng Gold và rod còn lại. Thanh trên cùng hiện thời gian tổng của phiên. Bảng kết quả có cột Lượt (chữ đen khi giao diện sáng, chữ trắng khi giao diện tối), Kết quả (xanh lá khi thành công, đỏ khi thất bại), Thời gian (đồng hồ của từng con, cùng số với cột `giay` trong file csv), Phân loại (màu phẩm giữ nguyên: đỏ, xanh, tím, cam, trắng) và Gold (vàng). Kẹo, pinball và túi mồi nằm ở cột Phân loại, kèm số lượng, chữ trắng. Một lượt có cả hai thì ghi chung, ví dụ `x3 pinball, x1 túi mồi`; nếu kèm cá thì chữ lấy màu của cá.
- `logs/cau-ca-<giờ>.csv`: mỗi lượt một dòng (`luot`, `ket_qua`, `vang`, `loai`, `pham`, `so_lan_bam`, `giay`). `ket_qua` là `thanh_cong`, `that_bai` hoặc `khong_ro`. `loai` là tên cá, `x3 pinball`, `x3,125 kẹo`, `x1 túi mồi`, hoặc ghép chung như `x3 pinball, x1 túi mồi`. `pham` là `do`, `xanh`, `tim`, `vang` với cá, và `trang` với kẹo, pinball, túi mồi. Có cả cá lẫn vật phẩm thì `pham` theo cá.
- `logs/cau-ca-<giờ>-vet.txt`: vết thời gian từng mẫu mồi và từng cú bấm. Dùng khi cần chỉnh lại độ trễ. Cuối mỗi lượt có dòng `lượt N: K lần bấm thanh trượt` và một dòng thông số cho từng lần.
- `logs/cau-ca-<giờ>-bam.csv`: cùng nội dung, mỗi cú bấm một dòng để tính độ trễ. Lượt không có thanh trượt vẫn có một dòng `lan=0`. Cột giờ là `t_lenh` (lúc phát lệnh), `tu_quang` (kể từ lúc quăng), `tre` (độ trễ đang giả định), `cho` (lệnh cách ảnh cuối bao lâu), `chup_dau`/`chup_cuoi` (cửa sổ chụp ảnh cuối), `mau_sau_*` (mồi ở ảnh ngay sau lệnh). `thanh` là thanh thứ mấy trong lượt, `lan_tren_thanh` là lần bấm thứ mấy trên thanh đó. `ket_qua_bam` là `trung` hoặc `truot`. `err_px` là mồi lúc game nhận trừ tâm vùng đang nhắm (dương là lệch sang phải). Chưa có mẫu quanh lúc đó thì để trống.
- Ảnh `logs/cau-ca-ketqua-N.png` (12 ảnh đầu mỗi lần chạy) để đối chiếu khi số Gold đọc sai.

## Ghi chú kỹ thuật

Sửa code trên máy xong phải **đóng giao diện rồi mở lại**. Tiến trình đang chạy vẫn giữ bản đã nạp lúc mở. Nút **Cập nhật** trong Cài đặt thì tự mở lại sau khi kéo bản mới.

Không bấm vào emulator khi tool đang chạy. Một cú bấm thừa vào viên hệ số hoặc nút câu làm lệch cả lượt.

### Hệ số

- Tool đọc **chữ số trắng** trên viên hệ số, không so cả hình tròn vàng. Hình tròn của x1 và x50 gần giống nhau, so cả viên sẽ nhận nhầm rồi bấm đổi.
- Đã thấy đúng hệ số một lần trong phiên thì không bấm viên đó nữa. Một lần đọc nhầm cũng đủ đẩy hệ số đi.
- Bấm một lần khi đang x20 thì game sang **x50**. Muốn về x1 phải đi tiếp x100 rồi mới về x1.
- Không đọc được viên hệ số thì tool chụp lại vài lần, không bấm đại.

### Thanh trượt

- Trong một lượt, thanh sau hẹp hơn thanh trước. Thanh đầu thường khoảng 146px. Thanh sau còn khoảng 110px, rồi khoảng 70px. Trượt không làm vùng nhỏ lại. Vùng nhỏ lại sau mỗi lần **trúng**, khi sang thanh kế.
- Không lấy một độ lệch trung bình rồi cộng vào mọi vùng. Vùng hẹp mà cộng độ lệch của vùng rộng sẽ bấm sát mép và trượt.
- Điểm nhắm là **giữa vùng đang thấy** (3 lần đọc gần nhất). Mồi che một mép làm vùng vừa đọc hẹp hơn rõ so với bản rộng nhất của cùng thanh thì nhắm theo bản rộng nhất.
- Chỉ bấm khi mồi được dự đoán nằm trong **40% giữa** vùng đó. Ngoài khoảng này thì chờ mẫu mới, không bấm mép. Đủ 20 cú có `err_px` thì bán kính này thu lại theo các cú trúng (không rộng hơn 40% nhìn thấy).
- Mồi đỏ đã chạy trước khi vùng vàng hiện (lúc Reel hoặc cảnh chuyển) thì được ghi lại. Vàng hiện lên là bấm theo quỹ đạo đó, không đo lại từ đầu.
- Ba ảnh liên tiếp cùng một chiều là đủ vận tốc và pha. Vùng rộng còn bấm từ ảnh thứ 3 khi đường khớp lệch không quá 8px, kể cả khi ba ảnh chưa đi một chiều vì cú nảy nằm trong đó. Chờ thêm sẽ lỡ lượt mồi đang đi ngang. Vùng rộng cũng bấm từ ảnh thứ 4 nếu đường khớp. Không đợi đủ 5 ảnh. Vùng hẹp hơn 120px không dùng lối tắt này.
- Vùng từ 120px trở lên: lệnh tính với độ trễ 0,24 giây. Vùng hẹp hơn: độ trễ đang học cộng 0,12 giây.
- Cửa sổ vào vùng còn xa hơn 0,70 giây thì chụp tiếp, chỉnh pha trên đoạn mồi đang chạy, rồi mới bấm. Trượt thì không xóa quỹ đạo: lần mồi quay lại được đặt lịch từ mô hình đang có. Độ trễ chỉ xê khi mồi còn trong vùng (lệch không quá nửa bề rộng); lệch lớn hơn thế là sai pha, giữ nguyên độ trễ. Mức xê không quá 0,08 giây và không quá khoảng 35% nửa vùng.
- Vùng dưới 120px mà chưa có đoạn thẳng sạch: lần bấm đầu vẫn chờ ít nhất 6 mẫu và sai số ≤ 18px. Trượt thì tính lại từ ảnh mới, không xê ±0,03 giây.
- Mồi chạy kiểu sóng tam giác, nảy ở khoảng x=206 và x=536 trên ảnh 720px (tâm mồi đo trên video tỉ lệ trượt; mốc cũ 199 và 532 làm cú bấm sau cú nảy tới muộn khoảng 20px), tốc độ thường 210–250 px/s. Mỗi ảnh chụp mất khoảng 0,45 giây nên không bấm theo ảnh vừa thấy. Bấm đi qua một shell ADB mở sẵn.
- Trượt không mất rod, chỉ mất thời gian. Hết khoảng 30 giây thì cá thoát, ghi `that_bai`.

### Độ trễ cú bấm

- Độ trễ là khoảng từ lúc phát lệnh bấm tới lúc game nhận. Mặc định **0,15 giây** (`BASE_LATENCY`). Tool chỉ học từ cú **trúng**: lấy lúc mồi đi ngang giữa vùng, rồi lấy trung vị 40 cú trúng gần nhất. Kết quả bị chặn trong **0,10–0,18 giây**. Vùng rộng không dùng số này để phát lệnh: video 17:29 cho thấy số học được (0,10 giây) tới muộn, nên lệnh của vùng rộng tính với **0,24 giây**. Sau một cú trượt mà mồi vẫn nằm trong vùng, độ trễ của lần bấm kế trên cùng thanh được xê theo `err_px`, tối đa 0,08 giây và không quá khoảng 35% nửa vùng. Mồi đã ra khỏi vùng thì không xê: đó là sai pha, không phải độ trễ.
- Cú trượt không đưa vào tính độ trễ. Lúc trượt gần như mọi độ trễ đều "khớp", trung vị bị kéo về 0 và cú bấm tới sau khi mồi đã ra khỏi vùng.
- Số đang dùng hiện ở dòng đầu nhật ký. Dữ liệu ở `data/hoc.json` (tối đa 400 cú). Xóa file đó để học lại. `tools/sim_flow.py` không ghi file này.
- `py -3 tools/phan_tich.py` chấm lại từng cú từ `logs/*-vet.txt`. Không tin dòng TRÚNG/TRƯỢT cũ trong file vết: bản trước có lúc báo trúng khi mồi chỉ che bớt vùng vàng. Thêm `--nhap` để dựng lại `data/hoc.json` từ các file vết.

### Gold

- Chữ vàng `+N` nằm bên phải đầu cá, **phía trên** số trắng cạnh đồng xu bạc. Trên video demo, chữ vàng hiện khoảng giây 23,6 đến 24,2 rồi mất trước giây 24,4. Chưa tới một giây.
- Không lấy số trắng đó, không lấy dòng cân nặng, không lấy dòng Beat …%. Dòng "New Team Record" không có nghĩa số trắng là Gold.
- Số từ 10 trở lên nhận ngay khi đọc được một lần. Một chữ số lẻ (tia sáng, hoặc mảnh đồng xu trong mưa xu đọc thành 2) chỉ nhận khi lặp ở hai ảnh, và không được chọn nếu cùng lượt đã đọc được số từ 10 trở lên. Mưa đồng xu sau chữ +Gold không đọc.
- Tool chụp thêm vài ảnh lúc chuyển cảnh Cool! sang màn kết quả, trước khi bấm bỏ qua. Ngủ 0,8 giây ở cảnh đó sẽ bỏ lỡ chữ vàng.

### Màn kết quả và rod

- Hệ số xN tốn N rod mỗi lần quăng. Còn ít hơn N rod thì dừng.
- Bấm `(130, 1100)` để đóng màn kết quả, kể cả "New Team Record". Bấm giữa màn hoặc `(360, 900)` không đóng được. `(360, 1100)` chỉ là phương án cuối: màn đã đóng sẵn thì cú đó quăng thêm một lần.
- Màn "Rewards!" là kết quả của cá thường, không có thanh trượt. Thấy nút câu tối sau khi cần đã quăng thì tính một lượt thành công. Popup lúc cần chưa quăng không tính lượt.
- Bấm Dừng lúc chưa quăng thì dừng ngay. Đang câu thì câu nốt lượt đó rồi dừng, không quăng thêm. Màn kết quả hoặc Time's up còn mở thì đóng nốt. Màn đó không đổi sau 12 giây thì dừng dù chưa về màn chờ quăng.
- Tool cũng dừng khi: không nhận ra màn hình quá lâu, bấm quăng ba lần không phản hồi, không đổi được hệ số, hết rod.

Rủi ro: game có thể coi đây là thao tác tự động và khóa tài khoản. Nên thử trên tài khoản phụ.

Rủi ro: game có thể coi đây là thao tác tự động và khóa tài khoản. Nên thử trên tài khoản phụ.

## Kiểm tra sau khi sửa

1. `py -3 -m fishing_tool.self_test` chạy trên ảnh và video có sẵn, không cần emulator. Phải ra `XONG`.
2. `py -3 tools/check_predictor.py` kiểm bộ đoán vị trí mồi trên video.
3. `py -3 tools/sim_flow.py 400 3` chạy vòng câu trên game giả (ảnh thật của video, mồi vẽ lại). Không đụng game.
4. Cuối cùng thử trên emulator thật, vài lượt, xem `logs/*-vet.txt`.

## Thư mục

| Đường dẫn | Việc |
|---|---|
| `checking-mvp/gift_tool/gui.py` | Cửa sổ chung. Tab **Tự câu cá** nằm ở `presenter.py` và `view.py`, gọi `fishing_tool.flow.Runner` |
| `fishing_tool/flow.py` | Vòng câu, đọc kết quả, dò độ lệch giờ bấm |
| `fishing_tool/memory.py` | Bộ nhớ học giữa các phiên (`data/hoc.json`) |
| `fishing_tool/predictor.py` | Đoán vị trí mồi, chọn giờ bấm |
| `fishing_tool/vision.py` | Nhận màn hình, đọc thanh trượt, đọc Gold, rod, hệ số |
| `fishing_tool/device.py` | ADB: đo giờ chụp, bấm qua shell mở sẵn |
| `fishing_tool/self_test.py` | Kiểm tra nhận màn trên ảnh có sẵn |
| `templates/` ở thư mục gốc repo | Ảnh mẫu dùng chung: nút Pinball, nút Camp, ô Fishing Contest, viên hệ số |
| `data/loai-ca/` | Ảnh từng loài, chia thư mục `do`, `vang`, `tim`, `xanh`. Kẹo, pinball và túi mồi để ngay trong thư mục này |
| `tools/` | `sim_flow.py`, `check_predictor.py`, `run_live.py` |
| `resource/` | Ảnh và video mô tả game |
