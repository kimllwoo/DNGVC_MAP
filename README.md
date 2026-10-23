# VTP Fleet Tracking — Hệ Thống Giám Sát Đội Xe Đà Nẵng

Hệ thống dashboard tập trung giám sát và quản lý phương tiện vận tải (36+ xe tải) phục vụ Trung tâm Vận hành / Bưu chính Viettel Post Đà Nẵng và các tuyến kết nối Quảng Nam. Hệ thống hợp nhất dữ liệu từ nhiều nguồn GPS (Viettel VTracking, Adsun) và các bảng tính Excel nghiệp vụ nội bộ (`Danh sách xe`, `Tồn đội vận chuyển`).

---

## 1. Kiến Trúc & Cấu Trúc Module

```
vtp_fleet_tracking/
├── .env.example             # Template cấu hình biến môi trường và tài khoản GPS
├── .gitignore               # Chặn commit thông tin nhạy cảm (.env, *.log, token)
├── run_dashboard.sh         # Script khởi chạy dịch vụ (Bảo mật: bind 127.0.0.1)
├── app/
│   ├── main.py              # FastAPI application & lifecycle management
│   ├── api/
│   │   └── routes.py        # REST API endpoints (/api/fleet/...)
│   ├── core/
│   │   ├── config.py        # Quản lý cấu hình & làm sạch dữ liệu nhạy cảm
│   │   └── logger.py        # Logging an toàn (tự động mask password/token)
│   ├── models/
│   │   ├── vehicle.py       # Mô hình xe hợp nhất (VehicleUnified) & Plate Normalizer
│   │   └── provider.py      # Mô hình trạng thái Provider & FleetSummary
│   ├── providers/
│   │   ├── base.py          # Abstract Base Provider
│   │   ├── vtracking.py     # Viettel VTracking Provider (Cloudrity WAF handling)
│   │   └── adsun.py         # Adsun Provider (LoginV4 & API tracking)
│   ├── services/
│   │   ├── excel_loader.py  # Đọc & tối ưu bộ nhớ từ các file Excel nghiệp vụ
│   │   └── fleet_service.py # Bộ tổng hợp trạng thái, hợp nhất & fallback demo
│   └── templates/
│       └── index.html       # Single-Page Dashboard (Stitch design + Leaflet OSM)
└── tests/
    ├── test_models.py       # Kiểm thử chuẩn hóa biển số & lọc tọa độ (0,0)
    ├── test_vtracking.py    # Kiểm thử xác thực, WAF 403, HTTP 200 false, bounded retry
    ├── test_adsun.py        # Kiểm thử Adsun LoginV4, token & parse payload
    ├── test_fleet_service.py# Kiểm thử hợp nhất Excel + GPS & demo fallback
    ├── test_api.py          # Kiểm thử tích hợp toàn bộ REST endpoints
    └── test_security.py     # Kiểm thử kiểm duyệt log và không rò rỉ bí mật
```

---

## 2. Bảng Kiểm Kê API & Mức Độ Xác Minh (Giai đoạn 1)

| Nhà cung cấp | Endpoint & Method | Cách xác thực | Dữ liệu trả về | Mức độ xác minh | Ghi chú & Phần còn thiếu |
|---|---|---|---|---|---|
| **Viettel VTracking** | `POST https://vtracking2.viettel.vn/login1` | JSON body `{username, password}` | `{"success": bool, "content": {"token", "refresh_token", "org_id", "project_id"}}` | **Đã xác minh (Live Probe)** | Trả HTTP 200 cả khi thất bại (`status: 2003, success: false`). Yêu cầu browser User-Agent để vượt Cloudrity WAF. |
| **Viettel VTracking Gateway** | `POST https://vtracking2.viettel.vn/portDataWithParam` | Cookie `presence=JWT` / Bearer token | `{"content": {"list": [...]}}` | **Quan sát thực tế** | Gateway proxy gọi microservices `/api/devices/vtracking/vehicle/filter/v2`. |
| **Adsun GPS Auth** | `POST https://auth.adsun.vn/Auth/LoginV4` | JSON body `{username, pwd}` | `{"Token": str/null, "Status": int}` | **Đã xác minh (Live Probe)** | Trả HTTP 200 với `Token: null` và `Status: 0` khi thông tin sai. |
| **Adsun Telemetry** | `GET https://dinhvi.adsun.vn/api/CarTracking/GetListCarRealtime` | Header `token`, `x-access-token` | `{"Data": [danh sách tọa độ xe]}` | **Quan sát lưu trữ** | WebApp lưu phiên và cấu hình qua Redux Persist. |
| **Excel Danh Sách Xe** | `Danh_sach_xe_10-10-2026.xlsx` | Đọc trực tiếp | 34 phương tiện cốt lõi (BKS, tải trọng, garage, bảo dưỡng, KĐ) | **100% Xác minh** | Cung cấp danh mục phương tiện chuẩn và thời hạn bảo dưỡng. |
| **Excel Tồn Vận Chuyển** | `Tồn đội vận chuyển DNG.xlsx` | Đọc trực tiếp | Số kiện tồn theo xe, tài xế vận hành, thời gian quét | **100% Xác minh** | Làm giàu 20 xe vận chuyển thực tế với dữ liệu hàng tồn. |

---

## 3. Quy Tắc An Toàn Mạng LAN & Bảo Mật

1. **Tuân thủ chính sách mạng LAN Doanh nghiệp**:
   - Dịch vụ backend **CHỈ BIND VÀO `127.0.0.1` (localhost)** hoặc chỉ định Wi-Fi.
   - Tuyệt đối không mở port hay lắng nghe trên giao diện LAN nội bộ `enp2s0` (`10.*.*.*`).
   - Không quét mạng, không probe port nội bộ.
2. **Bảo vệ thông tin xác thực**:
   - Không commit mật khẩu, token, cookie vào Git repository.
   - File `.env` nằm trong `.gitignore`.
   - Logging filter tự động làm sạch (mask) toàn bộ mật khẩu, chuỗi token JWT, và Authorization Bearer headers.
   - Không đưa thông tin đăng nhập GPS xuống giao diện người dùng.

---

## 4. Hướng Dẫn Vận Hành

### Bước 1: Thiết lập cấu hình tài khoản thực tế (Khi có thông tin)
Copy file `.env.example` thành `.env` và nhập tài khoản:
```bash
cp .env.example .env
nano .env
```
Cấu hình các dòng:
```env
VTRACKING_ENABLED=true
VTRACKING_USERNAME=tai_khoan_viettelpost
VTRACKING_PASSWORD=mat_khau_viettelpost

ADSUN_ENABLED=true
ADSUN_USERNAME=tai_khoan_adsun
ADSUN_PASSWORD=mat_khau_adsun
```
*Lưu ý: Nếu chưa cấu hình tài khoản thực tế, hệ thống tự động bật chế độ `DEMO MODE` với tuyến đường thực tế quanh Đà Nẵng để kiểm tra giao diện và hiển thị rõ huy hiệu cảnh báo `[DEMO MODE]`.*

### Bước 2: Chạy kiểm thử
```bash
python3 -m pytest -v tests/
```

### Bước 3: Khởi chạy Dashboard
```bash
./run_dashboard.sh
```
Mở trình duyệt truy cập: **`http://127.0.0.1:8000`**
