# 📦 Ứng Dụng Quản Lý Giao Nhận

Ứng dụng web quản lý giao nhận hàng hóa sử dụng Streamlit, với tính năng quét QR code từ camera, lưu trữ SQLite và dashboard thống kê.

## ✨ Tính Năng

- 🔍 **Quét QR Code**: Sử dụng camera để quét và decode QR code tự động
- 📤 **Gửi Hàng**: Tạo phiếu gửi hàng mới từ QR code
- 📥 **Tiếp Nhận**: Cập nhật trạng thái phiếu khi nhận hàng
- 📊 **Dashboard**: Thống kê và xem danh sách phiếu với bộ lọc
- 📋 **Lịch Sử**: Xem audit log tất cả thay đổi
- 🔐 **Xác Thực**: Hệ thống đăng nhập đơn giản
- 💾 **SQLite Database**: Lưu trữ dữ liệu local

## 🚀 Cài Đặt

### Yêu Cầu

- Python 3.8+
- pip

### Các Bước

1. **Clone hoặc tải project**

2. **Cài đặt dependencies:**
```bash
pip install -r requirements.txt
```

3. **Chạy ứng dụng:**
```bash
streamlit run app.py
```

4. **Truy cập ứng dụng:**
   - Mở trình duyệt tại: `http://localhost:8501`

## 🔑 Đăng Nhập

Tài khoản mặc định:
- Username: `admin` / Password: `admin123`
- Username: `user` / Password: `user123`
- Username: `staff` / Password: `staff123`

Có thể thay đổi trong file `config.py`

## 📱 Sử Dụng

### Gửi Hàng

1. Chọn tab **"📤 Gửi Hàng"**
2. Cho phép truy cập camera khi được yêu cầu
3. Quét QR code (định dạng: `qr_code,imei,device_name,capacity`)
4. Chọn nhà cung cấp
5. Nhập ghi chú (tùy chọn)
6. Click **"💾 Lưu Phiếu"**

### Tiếp Nhận Hàng

1. Chọn tab **"📥 Tiếp Nhận"**
2. Quét QR code của phiếu cần cập nhật
3. Chọn trạng thái mới (Đã nhận/Hư hỏng/Mất)
4. Nhập ghi chú (tùy chọn)
5. Click **"🔄 Cập Nhật"**

### Dashboard

- Xem thống kê tổng quan
- Lọc theo trạng thái, nhà cung cấp, thời gian
- Xuất dữ liệu ra CSV

### Lịch Sử

- Xem tất cả thay đổi trong hệ thống
- Audit log ghi lại mọi hành động

## 📊 Định Dạng QR Code

QR code phải có định dạng:
```
qr_code,imei,device_name,capacity
```

Ví dụ:
```
YCSC001234,124109200901,iPhone 15 Pro Max,128
```

## 🗄️ Database

Database SQLite tự động được tạo tại `shipments.db` với 3 bảng:

- **ShipmentDetails**: Thông tin phiếu gửi hàng
- **Suppliers**: Danh sách nhà cung cấp
- **AuditLog**: Lịch sử thay đổi

## 📁 Cấu Trúc Project

```
WEB/
├── app.py                 # File chính Streamlit app
├── database.py            # Database operations (CRUD)
├── qr_scanner.py          # QR code scanning & parsing
├── auth.py                # Authentication logic
├── config.py              # Configuration (users, settings)
├── requirements.txt       # Python dependencies
├── README.md              # Hướng dẫn sử dụng
└── shipments.db           # SQLite database (tạo tự động)
```

## 🛠️ Cấu Hình

Có thể tùy chỉnh trong `config.py`:
- Thông tin đăng nhập
- Trạng thái phiếu
- Nhà cung cấp mặc định

## 📝 Lưu Ý

- Camera chỉ hoạt động trên trình duyệt hỗ trợ WebRTC (Chrome, Edge, Safari)
- QR code phải rõ ràng và đủ ánh sáng để quét thành công
- Database SQLite lưu local, cần backup định kỳ

## 🚀 Deploy

Để deploy lên Hugging Face Spaces:

1. Tạo repository trên GitHub
2. Push code lên GitHub
3. Tạo Space mới trên Hugging Face
4. Kết nối với GitHub repository
5. Chọn template Streamlit

## 📄 License

MIT License

