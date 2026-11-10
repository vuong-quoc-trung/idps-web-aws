# WebSentinel Attack Simulator — Attacker only

Python ≥3.10. Công cụ chỉ gửi HTTP request tới target lab và quan sát HTTP response. Defender tự phát hiện và hiển thị kết quả trên WebSentinel; simulator không kết nối Dashboard, không đọc dữ liệu phát hiện và không đánh giá hiệu quả phòng thủ.

## Cài đặt

Ubuntu / Kali, từ root repository:

```bash
cd attack-simulator
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[web]'
python -m attack_simulator --web
```

Windows PowerShell:

```powershell
cd attack-simulator
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[web]"
.\.venv\Scripts\python.exe -m attack_simulator --web
```

Mở **http://127.0.0.1:8765**. UI chỉ bind localhost, mỗi laptop chạy UI riêng. Chọn target, scenario, giới hạn và xác nhận quyền kiểm thử. Không cần mở Dashboard để gửi request. Stop/Ctrl+C dừng sau request hiện tại, tối đa timeout cấu hình.

CLI dùng standard library, chạy ngay trong `attack-simulator/`, không cần Flask:

```bash
python3 -m attack_simulator --list
python3 -m attack_simulator --target http://192.168.10.1 --scenario baseline --authorized --report reports/baseline.json
python3 -m attack_simulator --target http://192.168.10.1 --scenario sqli --scenario xss --authorized --confirm-multiple --report reports/signatures.csv
```

## Hai laptop đổi vai

Sửa target trong `configs/laptop-a-attacks-b.json` / `laptop-b-attacks-a.json` thành URL reverse proxy của Defender. IP trong file chỉ là ví dụ. Không hardcode IP nguồn; hệ điều hành chọn đường mạng.

```bash
python -m attack_simulator --config configs/laptop-a-attacks-b.json --authorized --confirm-multiple
python -m attack_simulator --config configs/laptop-b-attacks-a.json --web
```

UI lấy target và allowlist từ file; kiểm tra/chọn lại profile, giới hạn, scenario trên UI. Xác nhận quyền và nhiều request phải chọn lại mỗi run. Config không hỗ trợ các trường kết nối Dashboard cũ: hãy xóa chúng trước khi dùng.

## 13 kịch bản (giữ nguyên payload và số request)

| Scenario | Probe | Request |
|---|---:|---|
| baseline | 1 | GET `/api/auth/me` |
| sqli | 1 | SQLi marker trong query của auth/me |
| xss | 1 | XSS marker trong query của auth/me |
| traversal | 1 | `../../pbl4-nonexistent` trong query; không tải file thật |
| command | 1 | `;whoami` trong query bỏ qua của auth/me; không endpoint thực thi |
| scanner | 1 | User-Agent lab có marker nikto |
| method | 1 | PROPFIND `/api/auth/me` |
| auth-get | 10 | GET auth không có phiên |
| login-failure | 10 + 1 setup | Username lab, password sai ngẫu nhiên; lấy session/CSRF trước |
| csrf | 5 + 1 setup | Session fixture, cố ý không gửi CSRF token |
| enumeration | 20 | Các path lab không tồn tại, duy nhất |
| burst | 120 | GET có giới hạn, profile behavior |
| ai-shadow | 1 | GET `/api/auth/me`; chỉ quan sát HTTP, không lấy kết quả AI |

Fixture login/CSRF cần tài khoản lab riêng và xác nhận. Không dùng tài khoản thật. Nếu login bất ngờ thành công, dừng vì fixture không an toàn. Không upload, raw packet, thực thi mã, SQL delay hoặc thay đổi dữ liệu.

```bash
python -m attack_simulator --target http://192.168.10.1 --scenario login-failure --lab-username simulator-lab-only --fixture-confirmed --authorized --confirm-multiple
python -m attack_simulator --target http://192.168.10.1 --scenario burst --profile behavior --max-requests 180 --rate 5 --authorized --confirm-multiple
```

## Trạng thái thực thi và báo cáo

- **COMPLETED:** đã hoàn tất các request và nhận HTTP response. HTTP 3xx/4xx/5xx cũng là response; redirect không được theo.
- **FAILED:** lỗi truyền tải/kết nối hoặc fixture login được chấp nhận ngoài dự kiến. Không đánh giá khả năng phát hiện.
- **CANCELLED:** người dùng dừng hoặc run chạm giới hạn thời gian/request trước khi hoàn tất.
- **SKIPPED:** thiếu fixture phù hợp hoặc scenario chưa được bắt đầu khi run dừng.

Trong lúc chạy, kết quả chưa có giá trị cuối và UI ghi “Đang thực thi”. Report JSON/CSV ghi target, tên scenario, số request, HTTP status, độ trễ, request ID từ response, timestamp và lỗi truyền tải đã lọc. Request ID thiếu/không đúng dạng 32 hex để trống. Không ghi body, query, password, cookie hay CSRF token. UI giữ run mới nhất, export thủ công. CLI trả exit code 1 nếu FAILED, 130 nếu CANCELLED, 0 nếu COMPLETED/SKIPPED.

## Giới hạn an toàn

Target chỉ nhận HTTP(S) origin, không credentials/path/query. Mặc định chỉ private/loopback. `allowlist` cấu hình các origin lab được phép ngoài private range; không sửa allowlist qua UI. Kiểm tra toàn bộ địa chỉ DNS rồi pin IP cho run; giữ Host và TLS SNI. Không theo redirect kể cả cùng origin; xác minh TLS, không dùng proxy môi trường hoặc giả IP nguồn.

Giới hạn cứng: 200 request/run (gồm setup), 5 request/s, timeout10s, run300s; response tối đa256KiB; một job UI; JSON input16KiB. Mọi request chạy tuần tự. Không tự bật/tắt enforcement hay sửa dịch vụ: Defender vẫn có thể chặn IP theo chính sách đang có.

UI giữ bảo vệ CSRF riêng cho thao tác Run/Stop, kiểm tra Host/Origin, CSP và không CORS. CSRF này chỉ bảo vệ UI simulator, không phải credential của hệ thống phòng thủ.

## Cấu trúc và tests

```
attack_simulator/
  http_client.py   # target, DNS pinning, HTTP có giới hạn
  config.py        # xác nhận quyền, profile, budget
  scenarios.py     # catalog + request specification
  runner.py        # runner chung, fixture, Stop
  reports.py       # JSON/CSV chỉ thông tin thực thi HTTP
  cli.py / web.py  # entrypoints
  templates/ static/
configs/           # hai laptop đổi vai
tests/             # HTTP mocks và Flask test client
```

```bash
python -m unittest discover -s tests -v
python -m attack_simulator --help
```

Tests không phụ thuộc Defender đang chạy và không gửi probe vào hệ thống thật. Flask cần được cài để chạy đủ UI tests. Tính portable dựa trên Python stdlib/Flask; cần nghiệm thu thêm trên Windows/Kali và đường mạng hai laptop thật. Công cụ không suy luận từ HTTP status rằng tấn công đã thành công hay Defender đã phát hiện.
