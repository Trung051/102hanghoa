# Hướng Dẫn Cài Đặt Google Sheets Integration

## Yêu Cầu

1. File `service_account.json` đã được cấu hình đúng
2. Google Sheet đã được chia sẻ với service account email
3. Đã cài đặt các thư viện cần thiết

## Cài Đặt Thư Viện

```bash
python -m pip install gspread google-auth
```

## Cấu Hình Google Sheets

### Bước 1: Lấy Service Account Email

Mở file `service_account.json` và tìm trường `client_email`. Ví dụ:
```json
"client_email": "trungwwww@pure-genius-457509-n6.iam.gserviceaccount.com"
```

### Bước 2: Chia Sẻ Google Sheet

1. Mở Google Sheet: https://docs.google.com/spreadsheets/d/1ROAsNg_7UsoW3qTr4_4mC0BRGmospktYidJM0ZNJAOo
2. Click nút **"Chia sẻ"** (Share) ở góc trên bên phải
3. Nhập email service account (từ bước 1)
4. Chọn quyền **"Editor"** hoặc **"Viewer"** (tùy nhu cầu)
5. Click **"Gửi"**

### Bước 3: Kiểm Tra Kết Nối

1. Mở ứng dụng Streamlit
2. Đăng nhập với tài khoản admin
3. Vào tab **"⚙️ Cài Đặt"** → **"☁️ Google Sheets"**
4. Click nút **"🔍 Kiểm tra kết nối"**
5. Nếu thành công, bạn sẽ thấy thông báo "Kết nối thành công!"

## Sử Dụng

### Push Dữ Liệu Từ Dashboard

1. Vào tab **"📊 Dashboard"**
2. Lọc dữ liệu nếu cần (theo trạng thái, NCC, thời gian)
3. Click nút **"☁️ Push lên Google Sheets"**
4. Dữ liệu sẽ được thêm vào Google Sheet (tránh trùng lặp)

### Push Dữ Liệu Từ Quản Lý Phiếu

1. Vào tab **"📋 Quản Lý Phiếu"**
2. Lọc dữ liệu nếu cần
3. Click nút **"☁️ Push lên Google Sheets"**
4. Dữ liệu sẽ được thêm vào Google Sheet

### Push Tất Cả Dữ Liệu (Admin Only)

1. Vào tab **"⚙️ Cài Đặt"** → **"☁️ Google Sheets"**
2. Chọn chế độ:
   - **Thêm mới (Append)**: Thêm dữ liệu mới, bỏ qua dữ liệu đã tồn tại
   - **Thay thế toàn bộ (Replace)**: Xóa tất cả dữ liệu cũ và thay thế bằng dữ liệu mới
3. Click nút **"📤 Push tất cả dữ liệu lên Google Sheets"**

## Cấu Trúc Dữ Liệu Trong Google Sheets

Các cột trong Google Sheet:
- **ID**: ID phiếu trong database
- **Mã QR Code**: Mã QR code của phiếu
- **IMEI**: IMEI thiết bị
- **Tên Thiết Bị**: Tên thiết bị
- **Dung Lượng**: Dung lượng thiết bị
- **Nhà Cung Cấp**: Tên nhà cung cấp
- **Trạng Thái**: Trạng thái phiếu (Đang gửi, Đã nhận, Hư hỏng, Mất)
- **Thời Gian Gửi**: Thời gian gửi hàng
- **Thời Gian Nhận**: Thời gian nhận hàng (nếu có)
- **Người Tạo**: Người tạo phiếu
- **Người Cập Nhật**: Người cập nhật phiếu (nếu có)
- **Ghi Chú**: Ghi chú (nếu có)
- **Thời Gian Đồng Bộ**: Thời gian push dữ liệu lên Google Sheets

## Lưu Ý

- Dữ liệu được push sẽ tự động tránh trùng lặp dựa trên ID
- Chế độ "Thêm mới" sẽ chỉ thêm các phiếu chưa có trong Google Sheet
- Chế độ "Thay thế" sẽ xóa tất cả dữ liệu cũ (trừ header) và thay thế bằng dữ liệu mới
- Service account cần có quyền Editor để có thể ghi dữ liệu vào Google Sheet

