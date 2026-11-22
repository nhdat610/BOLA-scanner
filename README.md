# BOLA-scanner

**BOLA-scanner** là công cụ dòng lệnh (CLI) được xây dựng bằng Python nhằm tự động hóa một phần quy trình kiểm thử phát hiện dấu hiệu **Broken Object Level Authorization (BOLA/IDOR)** trong ứng dụng Web/API.

Công cụ hướng đến việc thu thập HTTP traffic từ các phiên làm việc với nhiều tài khoản thử nghiệm, phân tích các vị trí có khả năng chứa object identifier và sinh test case kiểm thử quyền truy cập đối tượng.

> **Project status:** Đang phát triển. Các chức năng thu thập traffic, phân tích identifier và sinh test case đã được triển khai ở mức cơ bản. Chức năng thực thi test case và phân tích kết quả BOLA đang được phát triển.

## 1. Chức năng chính

### Đã triển khai

- **Scoped Crawling:** Truy cập website và khám phá các liên kết trong phạm vi được cấu hình, có giới hạn số trang và độ sâu crawl.
- **HTTP Traffic Collection:** Sử dụng Playwright để thu thập HTTP request và response phát sinh trong quá trình duyệt web.
- **Request Normalization:** Chuẩn hóa URL bằng cách loại bỏ fragment và loại bỏ request trùng lặp dựa trên HTTP method, URL và request body.
- **OpenAPI/Swagger Parser:** Đọc đặc tả OpenAPI/Swagger từ file hoặc URL được cấu hình để trích xuất thông tin endpoint, method, parameter, request body và response.
- **Authentication Context:** Tạo các browser context riêng biệt cho từng tài khoản thử nghiệm và hỗ trợ thao tác đăng nhập thủ công.
- **Sensitive Data Redaction:** Che giấu các thông tin nhạy cảm như token, cookie, password và authorization trong dữ liệu được lưu.
- **Identifier Analysis:** Phân tích request để nhận diện các vị trí có khả năng chứa object identifier.
- **Test Case Generation:** Sinh test case kiểm thử chéo bằng identifier thu thập từ các tài khoản thử nghiệm khác nhau.

### Đang phát triển

- Kiểm tra an toàn trước khi gửi request.
- Tự động thực thi test case bằng HTTPX, duy trì đúng ngữ cảnh tài khoản.
- Thu thập và so sánh response giữa các tài khoản.
- Phân tích dấu hiệu BOLA dựa trên status code, nội dung, cấu trúc và thông tin object.
- Hoàn thiện báo cáo kết quả trên CLI và JSON.

## 2. Công nghệ sử dụng

| Công nghệ | Mục đích |
|---|---|
| Python | Ngôn ngữ phát triển chính |
| Playwright | Tự động hóa trình duyệt và thu thập HTTP traffic |
| HTTPX | Gửi HTTP request phục vụ kiểm thử API |
| PyYAML | Đọc đặc tả OpenAPI/Swagger |
| pytest | Kiểm thử các thành phần của chương trình |
| Docker | Triển khai môi trường kiểm thử |

## 3. Quy trình hoạt động

Quy trình tổng thể dự kiến của BOLA-scanner:

1. **API Discovery:** Nhận URL mục tiêu, cấu hình phạm vi và thu thập request/response trong quá trình duyệt web.
2. **Request Normalization:** Chuẩn hóa dữ liệu và loại bỏ request trùng lặp.
3. **Identifier Analysis:** Phân tích request để tìm các vị trí có khả năng chứa object identifier.
4. **Test Case Generation:** Sử dụng identifier của các tài khoản khác nhau để sinh test case kiểm thử chéo.
5. **Safety Check:** Kiểm tra phạm vi và mức độ an toàn của request trước khi thực thi.
6. **Test Execution:** Gửi các request kiểm thử trong ngữ cảnh tài khoản tương ứng.
7. **Response Analysis:** So sánh response để tìm dấu hiệu truy cập đối tượng trái phép.
8. **Reporting:** Tổng hợp kết quả và bằng chứng trên CLI và JSON.

## 4. Cấu trúc dự án

Cấu trúc thư mục dự kiến theo các thành phần hiện tại:

```text
BOLA-scanner/
├── auth/
│   └── session.py
├── crawler/
│   ├── crawler.py
│   └── network_connector.py
├── tests/
├── data/
│   ├── network_traffic.json
│   └── identifiers_and_test_cases.json
├── config.json
├── main.py
├── openapi_parser.py
├── requirements.txt
└── README.md
```

Thư mục `data/` chứa dữ liệu traffic đã thu thập và kết quả phân tích, sinh test case. Các file JSON này được tạo trong quá trình chạy chương trình.

## 5. Cài đặt

Yêu cầu:
- Python 3.10 trở lên.
- Trình duyệt Chromium được Playwright hỗ trợ.
- Các thư viện được khai báo trong `requirements.txt`.

Clone repository:

```bash
git clone <repository-url>
cd BOLA-scanner
```

Tạo và kích hoạt môi trường ảo:

```bash
python -m venv .venv
```

Trên Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Cài đặt thư viện:

```bash
pip install -r requirements.txt
```

Cài đặt Chromium cho Playwright:

```bash
python -m playwright install chromium
```

## 6. Cấu hình và sử dụng

Cấu hình thông tin mục tiêu, phạm vi crawl và các tài khoản thử nghiệm trong `config.json` theo cấu trúc mà chương trình hỗ trợ.

Khởi chạy:

```bash
python main.py
```

Trong quá trình chạy, chương trình sẽ:
- Khởi tạo trình duyệt và xử lý từng tài khoản thử nghiệm.
- Chờ người dùng đăng nhập và thao tác trên website.
- Tự động ghi nhận HTTP traffic phát sinh trong phiên làm việc.
- Thực hiện crawl các URL được phát hiện trong phạm vi cấu hình.
- Phân tích identifier và sinh test case.
- Lưu dữ liệu thu thập và kết quả phân tích vào thư mục `data/`.

**Lưu ý:** Ở phiên bản hiện tại, người dùng cần đăng nhập và thao tác thủ công trên trình duyệt để tạo traffic. Chương trình chưa tự động thực thi các test case đã sinh.

## 7. Kết quả đầu ra

Một số file JSON được tạo trong quá trình chạy:

| File | Nội dung |
|---|---|
| `data/network_traffic.json` | HTTP request/response đã thu thập và xử lý |
| `data/identifiers_and_test_cases.json` | Identifier được nhận diện và các test case được sinh |

Ví dụ, với hai tài khoản thử nghiệm A và B, chương trình có thể sinh các test case:
- Sử dụng identifier của tài khoản B trong request của tài khoản A.
- Sử dụng identifier của tài khoản A trong request của tài khoản B.

Các test case này hiện được sinh ra để phục vụ bước kiểm thử tiếp theo; chưa thể kết luận có hay không có lỗi BOLA khi chưa thực thi và phân tích response.

## 8. Kiểm thử

Chạy bộ kiểm thử bằng pytest:

```bash
python -m pytest -q
```

## 9. An toàn khi sử dụng

- Chỉ kiểm thử các hệ thống mà bạn được phép sử dụng.
- Giới hạn hoạt động trong phạm vi domain/host đã cấu hình.
- Sử dụng tài khoản thử nghiệm, không sử dụng tài khoản hoặc dữ liệu của người khác khi chưa được cho phép.
- Không đưa token, cookie, password hoặc thông tin xác thực vào repository.
- Kiểm tra kỹ các request có khả năng làm thay đổi dữ liệu trước khi thực thi.

## 10. Hướng phát triển

- Hoàn thiện cơ chế kiểm tra an toàn và giới hạn request.
- Tự động thực thi test case bằng HTTPX.
- Hoàn thiện cơ chế so sánh response và nhận diện dấu hiệu BOLA.
- Xây dựng báo cáo kết quả chi tiết trên CLI và JSON.
- Đánh giá công cụ trên các môi trường Web/API thử nghiệm có và không có BOLA.
- Hoàn thiện tài liệu hướng dẫn và kiểm thử hồi quy.

---

**BOLA-scanner** — Python-based tool for automated BOLA/IDOR testing.