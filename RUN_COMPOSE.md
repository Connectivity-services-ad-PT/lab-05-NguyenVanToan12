# RUN_COMPOSE.md – Hướng dẫn chạy Lab 05 (Team Analytics)

Tài liệu này hướng dẫn cách chạy và kiểm thử toàn bộ stack Docker Compose của dịch vụ **Analytics & Alert** (Team Analytics) tích hợp cùng cơ sở dữ liệu **TimescaleDB** và **AI service** (mock).

---

## 1. Chuẩn bị tài nguyên
Sao chép tệp cấu hình `.env.example` thành `.env` tại thư mục gốc của repo:
```bash
cp .env.example .env
```
Bạn có thể mở tệp `.env` lên để cấu hình lại các thông số nếu cần (ví dụ: `APP_PORT`, `AUTH_TOKEN`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`).

---

## 2. Khởi chạy Docker Compose Stack
Sử dụng Makefile hoặc lệnh trực tiếp Docker Compose để build và chạy toàn bộ các service dưới nền:
```bash
# Sử dụng Makefile
make compose-up

# Hoặc dùng lệnh trực tiếp
docker compose up -d --build
```

Lệnh trên sẽ khởi chạy 3 container:
- `fit4110-db-lab05` (TimescaleDB chạy ở cổng 5432)
- `fit4110-ai-lab05` (Mock AI service chạy ở cổng 9000)
- `fit4110-api-lab05` (FastAPI Analytics & Alert API chạy ở cổng 8000)

Theo dõi logs của toàn bộ stack hoặc riêng API để kiểm tra xem quá trình kết nối DB và khởi tạo bảng có thành công không:
```bash
make logs
# Hoặc
docker logs -f fit4110-api-lab05
```

---

## 3. Kiểm chứng trạng thái hoạt động (Readiness & Health)

### A. Kiểm tra API Health
FastAPI Analytics service sẽ tự động kiểm tra kết nối tới TimescaleDB và gọi thử AI mock service khi bạn truy cập `/health`. Nếu cả hai service liên quan hoạt động tốt, endpoint sẽ trả về trạng thái `UP` với code 200:
```bash
curl http://localhost:8000/health
# Phản hồi: {"status":"UP"}
```

### B. Kiểm tra database TimescaleDB
Kiểm tra xem database Postgres/TimescaleDB đã sẵn sàng chấp nhận các kết nối chưa:
```bash
docker exec -it fit4110-db-lab05 pg_isready -U lab05 -d iotdb
```

### C. Kiểm tra AI Service
Kiểm tra health và kết quả dự đoán của mô hình AI mock:
```bash
# Healthcheck
curl http://localhost:9000/health

# Dự đoán thử
curl -X POST http://localhost:9000/predict
```

---

## 4. Chạy bộ kiểm thử tự động Newman

Bộ kiểm thử Newman sẽ chạy các bài kiểm tra API (functional, auth, negative, boundary, polymorphism, consumer smoke).

Để chạy tests:
1. Cài đặt các thư viện Node.js:
   ```bash
   npm install
   ```
2. Chạy mock server cho IoT Ingestion phục vụ cho bài test consumer smoke (bởi vì kiểm thử tích hợp yêu cầu gọi sang cổng telemetry):
   ```bash
   # Chạy Prism mock ở cổng 4011 dưới nền
   npm run mock:iot
   ```
3. Khởi chạy Newman:
   ```bash
   npm run test:compose
   ```

Báo cáo kiểm thử (Newman Reports) sẽ được xuất ra dưới định dạng HTML và JUnit XML tại thư mục:
- `reports/newman-lab05-compose.html`
- `reports/newman-lab05-compose.xml`

---

## 5. Dừng hệ thống
Để tắt toàn bộ container:
```bash
make compose-down
```
Nếu muốn xoá sạch các volume dữ liệu được lưu trữ trong TimescaleDB:
```bash
docker compose down -v
```