---
name: thong-bao-release
description: >-
  Viết và đính kèm thông báo release mỗi khi đẩy code của clash-of-critters-tool
  lên main. Dùng khi người dùng nói push, đẩy code, đẩy lên main, release,
  phát hành, hoặc cập nhật bản mới. Nếu người dùng không đưa nội dung,
  tự viết thông báo từ diff. Người dùng cuối không biết GitHub.
---

# Thông báo release khi push

Mỗi lần người dùng yêu cầu push code, bản đẩy lên phải có thông báo release. Push xong thì đưa thông báo đó ra trong câu trả lời.

Nếu người dùng đã viết nội dung, dùng đúng ý họ. Nếu họ không đề cập gì, tự viết.

## Trước khi commit

1. Đọc diff sắp đẩy (`git diff` và `git diff --cached`, cộng commit chưa có trên `origin/main`).
2. Nếu diff đã có đúng một file `versions/<phiên bản>.md` mới ở gốc repo và `APP_VERSION` trong `checking-mvp/gift_tool/view.py` khớp tên file đó, dùng file ấy. Không tạo thêm phiên bản.
3. Nếu chưa có, tăng `APP_VERSION` một bậc vá (x.y.Z) và tạo `versions/<APP_VERSION>.md` ở gốc repo, ngoài checking-mvp. Chỉ tăng bậc giữa (x.Y.0) khi lần này thêm chức năng người dùng bấm được.
4. Gộp file phiên bản và `APP_VERSION` vào cùng commit sẽ push. Không push khi thiếu thông báo.

## Cách viết

Người đọc là người bấm **Cập nhật** trong tool. Viết tiếng Việt, một ý một gạch đầu dòng, nói việc họ thấy trên màn hình.

Không viết GitHub, git, commit, hash, nhánh, remote, terminal, tên file mã nguồn.

Hộp thoại chỉ hiện mục **Thêm**, **Sửa**, **Bỏ**. Dòng `- Không có.` bị bỏ qua. Mục Kiểm tra không hiện cho người dùng.

```markdown
# Phiên bản X.Y.Z

Ngày: YYYY-MM-DD

## Thêm
- Việc mới người dùng làm được.

## Sửa
- Việc cũ hết lỗi, nói triệu chứng đã hết.

## Bỏ
- Không có.

## Kiểm tra
- Một bước bấm thử trên tool.
```

Ngày lấy theo ngày làm việc. Để `- Không có.` ở mục trống. Kiểm tra chỉ ghi bước tự kiểm trên máy.

## Sau khi push thành công

Đưa thông báo ra trong câu trả lời, đúng phần người dùng sẽ thấy. Bỏ mục trống và bỏ Kiểm tra.

```text
Đã đẩy lên main.

Có gì mới
Phiên bản X.Y.Z
Sửa
• ...
```

Nếu push thất bại, không đưa thông báo như thể đã phát hành. Nói lỗi push trước.
