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

## Authenticated Attack Mode

Bốn scenario mới chạy **riêng** với 13 scenario cũ:

- `student-users`: STUDENT → GET `/api/users`.
- `student-students`: STUDENT → GET `/api/students`.
- `staff-users`: STAFF → GET `/api/users`.
- `idor-get`: STUDENT → GET `/api/me/{object-type}/{id}`, chỉ ID lab cung cấp trước (tối đa20). Ba loại: family-members, emergency-contacts, post-graduation-contacts.

```bash
python -m attack_simulator --target http://192.168.10.1 --scenario student-users --auth-role STUDENT --auth-confirmed --authorized --confirm-multiple
python -m attack_simulator --target http://192.168.10.1 --scenario idor-get --auth-role STUDENT --object-type family-members --object-ids 101,102 --auth-confirmed --authorized --confirm-multiple
```

CLI hỏi username và password ẩn bằng getpass; không nhận password từ CLI args/config. UI có phần Authenticated Attack riêng, không lưu credentials trong localStorage. Chọn role, bỏ chọn baseline/scenario cũ và xác nhận fixture. Không dùng ADMIN. ID phải do người vận hành chuẩn bị, không lấy dữ liệu thật hoặc dò ID.

Luồng: GET CSRF → form login204 → nhận cookie xoay vòng → GET CSRF mới → GET auth/me xác minh username, role, enabled và passwordSetupRequired → GET probe → POST logout. Một phiên riêng mỗi run, chỉ JSESSIONID đúng host/path và Secure tương thích được gửi. Không tự đăng nhập lại khi401, không theo redirect. Setup4 request + logout1 được tính vào budget; logout có chỗ dự phòng về request và thời gian. Stop dừng probe nhưng vẫn thử logout trong giới hạn. Nếu phiên hết hạn, cleanup được bỏ qua; nếu mạng/CSRF lỗi thì report ghi cleanup FAILED/SKIPPED, không hứa phiên server đã bị hủy. Cookie/token/password luôn bị xóa khỏi đối tượng quản lý khi kết thúc; Python không bảo đảm zeroize mọi bản sao immutable trong bộ nhớ.

Các GET bị403/404 vẫn là HTTP đã thực thi, không kết luận về detector. Khi login/role mismatch/session expiry, không chạy tiếp hoặc tự đổi tài khoản. Report không lưu response body/profile, username, cookie, CSRF hoặc password.

**Chưa hỗ trợ:** Unauthorized Privilege Change và authenticated CSRF. Mass Assignment/Workflow chỉ chạy theo quy trình fixture kiểm soát bên dưới. Scenario `csrf` cũ vẫn giữ nguyên cho fixture login thất bại, không phải authenticated CSRF mới.

## Mass Assignment và Business Workflow Abuse — fixture kiểm soát

Hai scenario mới (`mass-assignment`, `workflow-abuse`) bổ sung vào 17 scenario trước. Chỉ role STUDENT, không nhận payload tùy ý. Mỗi bài tối đa **1 PUT `/api/me/profile`** với JSON cố định:

- `role: "STUDENT"` là trường bị cấm (không yêu cầu nâng lên ADMIN).
- `placeOfBirth`: 151 ký tự `L` — lớp dự phòng buộc DTO không qua `@Size(max=150)` nếu protected-field check bị thiếu.

Đã đối chiếu code repository: `ProtectedFieldAdvice` từ chối role trước binding; `MyProfileController.update` dùng `@Valid`; DTO giới hạn placeOfBirth; `ActiveAccountFilter` chặn thao tác ghi khi tài khoản disabled/password-setup-required. **Không thể xác minh deployment từ HTTP response hoặc lời xác nhận một mình.** Người vận hành phải đối chiếu phiên bản/config lab trước; không xác nhận được thì bỏ chọn safety contract, simulator SKIPPED và không gửi PUT. Không chạy nếu validation đã bị bỏ qua/sửa khác repo.

Hai xác nhận riêng là `--write-confirmed` và `--safety-contract-confirmed`. Không có đủ cả hai thì scenario SKIPPED. Không lưu body/profile trong report. Simulator không tự thay đổi DB/trạng thái tài khoản, không đọc Security API và không kết luận signal/không thay đổi dữ liệu từ HTTP400/401.

### Chạy cả hai trong một đợt có kiểm soát

1. **Defender chuẩn bị trước:** tài khoản STUDENT lab riêng đã active, hồ sơ lab riêng; chụp/ghi đối chiếu trường hồ sơ, role và trạng thái ban đầu bằng công cụ phía Defender. Không dùng dữ liệu thật. Đối chiếu code đang deploy có đủ hai lớp validation kể trên. Đảm bảo audit pipeline hoạt động riêng ở Defender.
2. **Simulator:** chọn Mass Assignment trước, Workflow cuối; bỏ chọn baseline. Chọn STUDENT, nhập username/password lab, xác nhận tài khoản, nhiều request, quyền test và hai xác nhận PUT/contract. Đặt duration300s, fixture wait120s nếu cần thao tác thủ công.
3. Login/CSRF/role được xác minh. Mass Assignment gửi1 PUT, **dự kiến HTTP400**. Nếu nhận2xx simulator FAILED và dừng, không retry hoặc rollback. Kiểm tra ngay dữ liệu lab ở Defender. 400 không tự chứng minh nguyên nhân từ chối.
4. Simulator dừng ở **“Đang chờ fixture”** sau login, chưa gửi PUT workflow. Người vận hành trên Defender kiểm tra dữ liệu sau bài đầu rồi **vô hiệu hóa đúng tài khoản lab** bằng công cụ quản trị đã được phép. Việc thay đổi enabled là fixture chủ động, không phải tác dụng của simulator. Không dùng phiên đang thử để GET kiểm tra trạng thái: request đó có thể thu hồi phiên trước bài PUT.
5. Bấm **“Đã chuẩn bị đúng fixture · Tiếp tục”** hoặc **“Bỏ qua workflow”**. Xác nhận gắn run ID hiện tại, chỉ dùng một lần và chỉ có hiệu lực trong lúc chờ. Không có xác nhận/timeout → SKIPPED; Stop → CANCELLED. Không tự lấy việc hết thời gian làm đồng ý.
6. Workflow gửi1 PUT với session/CSRF đã có, **dự kiến HTTP401** do account filter. Không gửi GET/relogin trung gian. Nếu fixture chưa disabled, payload vẫn phải bị hai lớp validation từ chối; HTTP400 được ghi là không đúng kỳ vọng workflow, không coi là chứng minh thao tác nghiệp vụ bị chặn đúng cơ chế.
7. **Defender đối chiếu riêng:** kiểm tra hồ sơ và role không đổi; chỉ enabled thay đổi như fixture chủ động. Tìm bằng request ID/thời gian trong WebSentinel, kiểm tra `MASS_ASSIGNMENT` và `WORKFLOW_DENIED` ở phía Defender. Lưu bằng chứng tại Defender; không chuyển cookie/token hoặc nội dung hồ sơ vào report simulator. Nếu chỉ đổi credential version/role mà không disabled/password-setup-required, không được coi là fixture workflow tương đương.
8. Người vận hành khôi phục fixture lab phía Defender theo quy trình riêng. Simulator chỉ logout khi còn phiên và xóa dữ liệu quản lý phiên; không tự phục hồi tài khoản.

CLI (password nhập ẩn; sau login sẽ hỏi xác nhận fixture):

```bash
python -m attack_simulator --target http://IP-DEFENDER \
  --scenario mass-assignment --scenario workflow-abuse \
  --auth-role STUDENT --auth-confirmed --authorized --confirm-multiple \
  --write-confirmed --safety-contract-confirmed \
  --duration 300 --fixture-wait 120 --report reports/controlled-fixtures.json
```

Khi CLI hỏi, chỉ gõ `DISABLED` sau khi đã chuẩn bị đúng trạng thái trên Defender. Enter/EOF hoặc hết thời gian sẽ bỏ qua. Xác nhận trước login trong config không thể thay thế bước này.

`COMPLETED` chỉ nói request đã thực thi; `expected_http_status`/`http_expectation_met` là đối chiếu HTTP, không phải detector verdict. Response2xx ngoài dự kiến phải dừng và kiểm tra dữ liệu. HTTP401 cũng có thể do session hết hạn, nên không tự khẳng định workflow signal. Tổng budget gồm setup4, hai PUT, logout tối đa1; chờ fixture nằm trong duration và dành thời gian cleanup. Không có polling tới Student hoặc Defender khi chờ.

### Trạng thái nghiệm thu

Unit/integration tests dùng HTTP mock kiểm tra payload, CSRF/cookie, hai lớp xác nhận, workflow gate/run ID, timeout/Stop, status ngoài dự kiến và không rò secret. **Chưa chạy end-to-end Student Web thật:** còn cần tài khoản/fixture do người vận hành chuẩn bị, xác nhận contract đang deploy và đối chiếu dữ liệu trước/sau. Mock thành công không phải bằng chứng dữ liệu lab thật không đổi hoặc Defender đã tạo signal.

## Repeat GET vượt quyền sau đăng nhập

`--repeat 1..8` (mặc định1) chỉ nhân số GET của `student-users`, `student-students`, `staff-users`. UI có ô **Repeat GET vượt quyền**. Đăng nhập đúng một lần/run, giữ cookie hiện tại, gửi tuần tự rồi logout. IDOR, PUT fixture và 13 scenario ban đầu không bị nhân số request. Run có các GET này giới hạn rate hiệu lực tối đa2/s (nhập cao hơn được giới hạn về2); Repeat>1 cần rate≥0.2/s. Các run khác giữ giới hạn rate hiện có.

Demo STUDENT lab:

```bash
python -m attack_simulator --target http://IP-DEFENDER \
  --scenario student-users --auth-role STUDENT --auth-confirmed \
  --repeat 8 --rate 2 --max-requests 13 --duration 120 \
  --authorized --confirm-multiple --report reports/repeated-users.json
```

Tổng13 request: setup4 + probe8 + logout1. Nhiều scenario được chọn thì mỗi scenario GET vượt quyền dùng Repeat riêng, cộng chung budget. CLI/UI từ chối budget quá nhỏ. Request thực thi vẫn chịu duration/timeout/Stop và phần thời gian dự phòng logout. HTTP401 dừng ngay, không tự login lại; role mismatch không gửi probe. HTTP403/200 vẫn được ghi riêng từng lượt, không kết luận detector.

Ở rate2/s, 8 probe cần khoảng3.5 giây cộng độ trễ response cuối nếu mỗi response nhanh hơn0.5s; với mạng lab bình thường nằm trong60s. Không bảo đảm60s khi mạng/upstream chậm hoặc session hết hạn; không tăng tốc hoặc vượt timeout để ép đạt. Dùng cấu hình demo trên để tránh duration quá ngắn. Bảng UI có cột lượt/bước và từng HTTP status, request ID, độ trễ, trạng thái. Người vận hành đối chiếu kết quả riêng tại Dashboard Defender; simulator không gọi Security API.
