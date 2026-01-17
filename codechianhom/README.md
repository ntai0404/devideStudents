# Student Group Division Tool (Công cụ chia nhóm sinh viên)

Ứng dụng web dựa trên Flask giúp tự động lấy thông tin sinh viên từ hệ thống đăng ký tín chỉ và hỗ trợ chia nhóm dựa trên GPA, điểm môn học và kỹ năng.

## Tính năng chính
- Đăng nhập bằng tài khoản sinh viên TLU.
- Tự động lấy danh sách ca thực hành của môn học mục tiêu.
- Đăng ký vào các lớp nhóm (65HTTT, 65CNTTT).
- Ghi nhận yêu cầu về mục tiêu (A, B, C, D) và điểm mạnh (Lập trình, Thiết kế, Thuyết trình...).
- Trang Admin: Quản lý danh sách, xuất file CSV và tự động chia nhóm.

## Cài đặt và Khởi chạy

### 1. Cài đặt thư viện
Yêu cầu Python 3.x. Cài đặt các thư viện cần thiết:
```bash
pip install flask requests urllib3 pandas waitress
```

### 2. Khởi chạy ứng dụng
Di chuyển vào thư mục `codechianhom` và chạy:
```bash
python app.py
```
Ứng dụng sẽ chạy tại địa chỉ: `http://localhost:5000`

## Cấu hình (Dành cho Giảng viên/Trợ giảng)

Để thay đổi môn học cần theo dõi ca thực hành, bạn mở file `app.py` và chỉnh sửa 2 dòng cấu hình ở đầu file:

```python
# app.py
TARGET_SUBJECT_CODE = "CSE441"
TARGET_SUBJECT_NAME = "Phát triển ứng dụng di động"
```

Ứng dụng sẽ tự động cập nhật tên môn học và mã môn học trên toàn bộ giao diện và logic lọc dữ liệu.

## Cấu trúc thư mục
- `app.py`: Code xử lý chính của server.
- `chia_nhom.py`: Thuật toán tự động chia nhóm.
- `templates/`: Chứa các tệp giao diện HTML.
- `static/`: Chứa các tệp CSS và tài nguyên tĩnh.
- `log.txt`: Dữ liệu mẫu (sử dụng khi cần kiểm tra).
