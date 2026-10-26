# 07 — Cấu hình khi nâng bản Student Web trên VM, Security chạy riêng

**Ngày:** 26/10/2026. **Phạm vi:** hướng dẫn chuyển từ code trước Shared Foundation sang code mới, giữ mô hình Student Web trên Web VM và Security trên một máy khác. Không áp cấu hình, sửa `.env` cá nhân, đổi mạng hay restart dịch vụ trong lần viết hướng dẫn này. Cấu hình đang chạy trên máy bạn của người dùng chưa được cung cấp; IP dưới đây là ví dụ topology có trong repo, phải thay nếu lab thực tế khác.

Code foundation ở nhánh `codex/foundation-audit-and-schema`. Tại thời điểm viết guide, code chưa commit; hiện đã được chia commit theo phần (ledger06 mục15), vẫn chưa push trong phiên này. Máy khác chỉ pull được sau khi tác giả push nhánh. Nhận đầy đủ migrations/contracts trước khi làm theo; không chép riêng entity mới mà bỏ migration, hoặc chép riêng parser mà bỏ contract.

## 1. Mô hình cần giữ

```text
Kali / trình duyệt
        |
        v
Máy Security (host hoặc VM, chạy security-web/Suricata/Nginx/nftables)
  phía client: 192.168.10.1
  phía Web VM: 192.168.20.1
        |
        | HTTP tới 192.168.20.10:80
        v
Web VM 192.168.20.10
  Nginx của Web VM → /api/ → Student backend 127.0.0.1:8080
                  → /     → Student frontend 127.0.0.1:5173
                             hoặc frontend dist đã build
  PostgreSQL Student riêng trong VM
  Student JSONL → file trong VM → transport riêng → collector trên máy Security
```

`127.0.0.1` trên máy Security và `127.0.0.1` trong Web VM là **hai máy khác nhau**. Web VM có Nginx nội bộ để phục vụ Student không có nghĩa chạy thêm `security-web` trong Web VM.

| Thành phần | Web VM của bạn cùng làm | Máy Security |
|---|---|---|
| Student backend/frontend/Student DB | Có, như mô hình cũ | Không cần chạy |
| Nginx | Web-facing proxy/static server tại VM | Edge proxy/structured access log |
| security-web/Security DB/Suricata/nft helper | Không cần cài theo guide này | Chạy riêng như lab hiện có |
| `scripts/dev-up-and-verify.sh` | Không dùng để triển khai mô hình tách máy | Script này dựng demo gộp một máy, không phải launcher VM-only |

## 2. Bảng cấu hình bắt buộc và phần có thể giữ nguyên

| Hạng mục | Điều cần làm khi nhận code mới | Ai làm |
|---|---|---|
| `.env` cũ, database và volume | Giữ giá trị thực; bổ sung biến mới, không thay cả file bằng `.env.example`, không reset DB | Người giữ Web VM |
| Audit JSONL/HMAC | Thêm path ghi được và key tối thiểu 32 byte; exporter bật mặc định nên thiếu key sẽ lỗi khởi động | Người giữ Web VM |
| App bind | Giữ loopback nếu Nginx ngay trong VM nhận request; cấu hình lại nếu trước đây Security truy cập trực tiếp VM:8080/5173 | Người giữ Web VM |
| Trusted proxy | Khai báo đúng peer/chuỗi proxy, giữ request ID từ Security edge tới app | Cả hai phía |
| DB port | Student vẫn mặc định5433. Hai DB khác máy có thể cùng5433; Security Compose mới mặc định5434 và DATABASE_URL phải khớp | Mỗi bên quản DB của mình |
| Flyway | V2 thêm request_id cho Student; Security có SQLx0003/0004. Kiểm history/checksum và sao lưu trước nâng | Mỗi bên quản service của mình |
| Upstream Security Nginx | Với VM-only, trỏ thẳng WebVM:80 thay cho ưu tiên Student loopback trên máy Security | Người giữ máy Security |
| Shipping audit | Phải cung cấp bản sao/mount/stream file từ Web VM về máy Security; chỉ đặt cùng tên path ở hai máy không nối được log | Cả hai phía |
| Collector/dataset | Đặt path đích đọc được; bật COLLECT_ALL_EVENTS nếu cần lưu observations cho dataset | Người giữ máy Security |
| Firewall/Suricata | Chỉ cần nâng nếu phía Security cũng nhận code foundation; cài đồng bộ helper/policy/rules và đối chiếu NIC thực | Người giữ máy Security |

Nếu **chỉ nâng Student** thì website/audit có thể chạy sau cấu hình phía Web VM; Security bản cũ sẽ chưa đọc nguồn Student JSONL hoặc normalized_events. Muốn có luồng mới đầy đủ phải nâng cả phía Security. Các trường bổ sung trong DTO audit không thay thế việc nâng parser/schema ở máy Security.

## 3. Những biến cần thêm vào Student backend `.env`

Ví dụ này dành cho **Nginx nằm trong Web VM**, Spring và Vite ở loopback. Nginx Security có IP kết nối sang VM là192.168.20.1:

```dotenv
# GIỮ DB_URL, DB_USERNAME, DB_PASSWORD và các biến SMTP/account hiện có.
# Nếu DB Docker trên VM map5433 thì DB_URL dạng:
# jdbc:postgresql://127.0.0.1:5433/student_db

STUDENT_BIND_ADDRESS=127.0.0.1
TRUSTED_PROXIES=127.0.0.1/32,::1/128,192.168.20.1/32

AUDIT_INCLUDE_SUCCESSFUL_READS=true
STUDENT_AUDIT_LOG_ENABLED=true
STUDENT_AUDIT_LOG_PATH=./logs/student-audit.log
STUDENT_SOURCE_INSTANCE=student-web-vm
STUDENT_AUDIT_MAX_BYTES=67108864

# Chỉ dùng false cho lab HTTP. Nếu edge dùng HTTPS thì dùng true.
SESSION_COOKIE_SECURE=false
# Địa chỉ người dùng mở trên trình duyệt, không phải localhost bên trong VM.
PUBLIC_APP_URL=http://192.168.10.1
```

Thêm `STUDENT_AUDIT_HMAC_KEY=<key thật do nhóm tạo riêng>`; sinh key bằng `openssl rand -hex 32` rồi đặt giá trị vào `.env`, không commit key. Giữ key ổn định qua các lần restart để pseudonym user/session có thể đối chiếu; không gửi key sang Security chỉ để parse JSONL vì collector không cần giải HMAC.

`run.sh` có nạp `.env`; chạy JAR/systemd trực tiếp thì phải nạp các biến bằng cơ chế tương ứng, Spring không tự đọc file `.env` như một file properties. Đường dẫn `./logs/...` tính theo working directory của process; `run.sh` chuyển vào thư mục backend. Với systemd, đặt WorkingDirectory đúng hoặc dùng đường dẫn tuyệt đối.

File được tạo0600, thư mục mới0700; parent phải thuộc user chạy app, không group/world writable và target không là symlink. Không dùng chmod777 để chữa lỗi export. Mặc định file tối đa64MiB; cần rotation rename/create và giữ file cũ chưa nén đến khi collector đọc hết. Lỗi ghi được báo trong server log nhưng không tự dừng nghiệp vụ.

Để tạm chạy website trước khi cấu hình xong audit, có thể đặt `STUDENT_AUDIT_LOG_ENABLED=false`; DB audit vẫn có. Đây là chế độ **chưa thu JSONL**, không đánh dấu audit integration hoàn thành.

Không đổi `server.forward-headers-strategy` sang native/framework: code mới chủ động dùng Boot strategyNONE **cùng ForwardedHeaderFilter tùy biến kiểm trust trước khi rewrite**. `RequestAttribution` sẽ từ chối cấu hình auto strategy khácNONE. Chỉ khai báo proxy thực, không tin toàn bộ mạng client. Cách tách ranh giới header dựa trên [hướng dẫn Spring về forwarded headers](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html).

## 4. Nginx trong Web VM: giữ IP và request ID qua hai proxy

Nếu VM đã có reverse proxy cổng80, chỉnh site đang có; không tạo site thứ hai tranh cùng listen/server_name. Nếu VM đang serve frontend `dist`, giữ cấu hình static/SPA fallback hiện tại, chỉ cập nhật `/api/` và các header liên quan. Nếu đang dùng Vite, có thể tham khảo mẫu sau.

**Mẫu HTTP/Vite để đối chiếu, chưa áp trên VM:**

```nginx
server {
    listen 192.168.20.10:80;
    server_name _;

    # IP nguồn THỰC của máy Security khi kết nối đến VM.
    allow 192.168.20.1;
    deny all;

    # Edge Security đã ghi structured log; tránh log phụ chứa raw token/query.
    access_log off;
    error_log /dev/null crit;

    proxy_http_version 1.1;
    proxy_set_header Host $http_host;
    proxy_set_header X-Request-Id $http_x_request_id;
    proxy_set_header X-Real-IP $http_x_real_ip;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
    proxy_set_header Forwarded "";

    location /api/ {
        proxy_pass http://127.0.0.1:8080;
    }
    location / {
        proxy_pass http://127.0.0.1:5173;
    }
}
```

Mẫu này giả định WebVM Nginx chưa bật `real_ip` rewrite ở cấp khác: allow/deny phải kiểm peer Security thật. Nếu đã có real_ip module/config riêng, cần đối chiếu lại boundary trước dùng mẫu. Restriction nguồn cần được áp cả ở mạng/host phù hợp, không mở trực tiếp app/DB ra mạng client.

Chuỗi mong đợi: edge nhận clientIP, **overwrite** XFF thành clientIP và sinh requestID mới; NginxVM **giữ** requestID và append peerSecurity vào XFF; Spring peer=loopback, đi ngược chuỗi qua các hop trusted rồi dừng tại client. Không overwrite XFF thành192.168.20.1 hoặc sinh requestID thứ hai ở Web VM, vì sẽ mất attribution/correlation.

Header đặt ở server được các location kế thừa nếu location không khai báo proxy_set_header riêng; khi sửa site có sẵn phải kiểm cả inheritance. Tham chiếu [Nginx proxy headers](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_set_header) và [allow/deny](https://nginx.org/en/docs/http/ngx_http_access_module.html).

Frontend mới mặc định127.0.0.1:5173, strictPort=true. Khi có Nginx trong VM thì giữ được bind này; frontend dev proxy `/api` vẫn trỏ backend8080 trong cùng VM. Nếu trước đây truy cập trực tiếp VM:5173, phải chuyển sang Nginx hoặc chủ động bind IP VM qua `bash run.sh --host <WEB_VM_IP> --port 5173`, đồng thời giới hạn người được truy cập. Backend direct-IP là phương án khác, cần `STUDENT_BIND_ADDRESS=<WEB_VM_IP>` và đổi upstream Security sang8080; **không trộn phương án direct-IP với mẫu WebVM:80 ở trên**.

Mẫu trên là HTTP lab. Nếu profileprod của Spring đang bật TLS trực tiếp, upstream `http://127.0.0.1:8080` không còn đúng: giữ hợp đồng TLS hiện tại và cấu hình HTTPS upstream/certificate trust tương ứng, hoặc chốt TLS tại edge và dùng profile HTTP phía app. Không tắt verify chứng thư để làm cấu hình chạy tạm.

## 5. Database Student: không cần tạo lại

- Java25 và Node phù hợp Vite8 vẫn là stack đã có trước foundation; không cần đổi ngôn ngữ/chuyển DB sang máy Security.
- Nếu `.env` cũ đã có DB_URL đúng5432 hoặc5433 thì giữ nguyên; default mới5433 chỉ tác động khi không có override. Compose Student vẫn mặc định5433.
- `STUDENT_DB_PORT` là biến môi trường cho Docker Compose, không tự được đọc từ `student-web/backend/.env` khi gọi Compose từ gốc. Có thể truyền như `STUDENT_DB_PORT=5433 docker compose -f docker/docker-compose.yml up -d postgres`.
- DB đã có FlywayV1: V2 mới thêm `request_id` và index, giữ dữ liệu cũ. Không sửa checksum/V1 và không dùng Hibernate create/update để né migration.
- DB cũ chưa có Flyway history: theo [DATABASE_MIGRATIONS.md](../student-web/backend/docs/DATABASE_MIGRATIONS.md), kiểm schema và chỉ baseline sau khi đã sẵn sàng. Không bật baseline tự động cho mọi DB và không chạy lại toàn bộ seed.
- Sao lưu trước nâng version. Không dùng `docker compose down -v`, không xóa database/volume để “chạy code mới”.

## 6. Máy Security: trỏ trực tiếp Web VM thay vì local-first

Trong bản site mới đang cài trên máy Security, giữ `map`, `log_format idps_json`, các location và header của foundation. **Chỉ thay hai upstream** thành:

```nginx
upstream student_api {
    server 192.168.20.10:80;
}
upstream student_frontend {
    server 192.168.20.10:80;
}
```

Với VM-only, WebVM là upstream chính, không mang cờbackup và không thử localhost8080/5173 của máy Security. `backup` có nghĩa chỉ dùng khi primary không khả dụng theo [Nginx upstream](https://nginx.org/en/docs/http/ngx_http_upstream_module.html); không cần cơ chế đó khi nhóm chủ động chỉ dùng một WebVM.

Có thể giữ `listen 192.168.10.1:80` của lab cũ để chỉ phục vụ interface lab; không bắt buộc mở0.0.0.0 nếu không dùng LAN. Giữ edge overwrite XFF, X-Real-IP và sinh X-Request-Id như template mới. Nếu chép nguyên site cũ combined thì trang web có thể vẫn chạy, nhưng log thiếu requestID và các flag redacted mới; không đạt cùng contract correlation/privacy của foundation.

Security `.env` cần đối chiếu:

```dotenv
WEB_SERVER_IP=192.168.20.10
PROTECTED_GATEWAY_IP=192.168.20.1
ENFORCEMENT_MODE=OFF
AUTO_BLOCK=false

# Path BÊN MÁY SECURITY, sau khi đã có cơ chế nhận log từ Web VM.
STUDENT_AUDIT_LOG_PATH=/var/spool/idps/student-vm/student-audit.log
SECURITY_SENSOR_ID=security-lab
COLLECT_ALL_EVENTS=true

SURICATA_EVE_PATH=/var/log/suricata/eve.json
NGINX_ACCESS_PATH=/var/log/nginx/access.log
```

Giữ DATABASE_URL/auth hashes hiện có. Nếu giữ Security DB5433 trên máy riêng, đặt `SECURITY_DB_PORT=5433` trong Compose env và DATABASE_URL5433; nếu nhận default mới5434 thì đổi cả hai sang5434. Hai DB ở hai máy hoàn toàn có thể cùng5433. Không có yêu cầu đổi Student DB chỉ vì máy Security đổi port.

Nếu chưa có bản log ở đích, để `STUDENT_AUDIT_LOG_PATH=` rỗng tạm thời để không bật watcher thiếu nguồn; khi đó **chưa ingest Student audit**. Khi muốn lưu observations phục vụ dataset phải bật COLLECT_ALL_EVENTS; false vẫn phát hiện cảnh báo nhưng không giữ mọi traffic bình thường.

## 7. Audit JSONL giữa hai máy: phần cần nối thêm

Code hiện có writer file ở Student và reader file cục bộ ở Security; **chưa có shipper xuyên máy tích hợp**. Đặt cùng biến path ở hai máy, đặt địa chỉ `user@vm:/...` hoặc URLSSH vào biến này không tạo được kết nối mạng.

Chọn secure collector/transport hoặc mount theo quy trình của nhóm. Nó cần đáp ứng:

1. Có quyền đọc file0600 của app và tạo bản đích cho user chạy security-web đọc; không nới file thành777 hoặc public share.
2. Giữ từng dòng JSONL và `event_id/source_instance` nguyên vẹn; không cắt dòng đang ghi, không truncate/ghi đè tùy tiện file đích đã được collector ACK.
3. Theo dõi rotation rename/create; giữ rotated files chưa nén đến khi đọc xong. Collector hiện không đọc.gz.
4. Có retry/checkpoint và giám sát độ trễ/dung lượng. Chuyển log chậm vẫn hữu ích cho dataset, nhưng phản ứng auto có freshness gate mặc định60s và không nên áp hồi tố.
5. Giữ origin instance ổn định và khác nhau cho từng app producer; không tạo eventID mới khi retransmit.

Vì vậy có hai mốc độc lập: **Student mới chạy trên VM** hoàn thành khi app/DB/exporter hoạt động; **IDPS đọc được auditVM** chỉ hoàn thành khi transport và collector đã nối được. Không hứa chỉ sửa.env là tự đạt mốc thứ hai.

## 8. Suricata và firewall nếu nâng cả phía Security

- Giữ NIC/IP lab thực tế. Nếu Security chạy VM, NIC có thể tênenp*/ens*, không phảivmnet2/vmnet3 của host VMware. Đối chiếu `ATTACKER_IFACE`, `PROTECTED_IFACE`, YAML Suricata, systemd ExecStart và `oifname` trong nftables; env không tự render tất cả file này.
- Rule mới có9SID, trong đó rule auth dùng cú pháp Suricata8; bản đã kiểm là8.0.3. Kiểm version sensor trước nạp rule; không chép rule mới lên engine cũ rồi coi là tương thích.
- Giữ IP_WHITELIST hiện có, bổ sung IP quản trị/gateway/WebVM đúng thực tế. Root policy `config/firewall-policy.json.example` phải được điều chỉnh tương ứng; ENV backend không thay thế policy root.
- Nếu bật enforcement, cài đồng bộ wrapper `pbl4-firewall`, Python module `pbl4-firewall-policy.py`, root policy và nft set cótimeout/protected_ips. Helper cũ chỉ nhận dảiKali và không có đối sốTTL, không tương thích đầy đủ backend mới.
- Chỉ kiểm/giám sát trước bằng ENFORCEMENT_MODE=OFF; mode này chủ động không thực thiPENDING/RESTORE. AUTO_BLOCK=false riêng lẻ không có cùng nghĩa.
- Không chạy deploy.sh --deploy (vẫn bị khóa). Guide này không tự nạp ruleset hoặc bật block trên bất kỳ máy nào; nghiệm thu packet thật là bước riêng theo [HOST_SECURITY_SETUP.md](../security-web/docs/HOST_SECURITY_SETUP.md).

## 9. Trình tự chuyển đổi và dấu hiệu thành công

| Bước | Người giữ Web VM | Người giữ máy Security |
|---|---|---|
| 1 | Nhận code đầy đủ; giữ.env và backup DB/site | Giữ.env/auth/DB và backup site/rules; enforcementOFF |
| 2 | Bổ sung audit key/path/reads/instance, xác nhận DB_URL | Chốt DATABASE_URL/port, WebVMIP và NIC đúng máy |
| 3 | Nối NginxVM80 vào app loopback, chuyển tiếp ID/IP | Đổi upstream thànhWebVM80, giữ structured edge log |
| 4 | Build/test rồi khởi động app để chạy V2 | Build/test rồi khởi động security để chạy0003/0004 |
| 5 | Xác nhận JSONL mới sinh và không chứa secret | Nối transport rồi bậtStudentwatcher + COLLECT_ALL_EVENTS |
| 6 | Đối chiếu ID/IP theo request | Hai source cùngrequestID, parse errors không tăng, kiểm benign row |

Ví dụ kiểm từ máy Security sau khi các dịch vụ đã được nhóm cấu hình:

```bash
# Chỉ kiểm syntax site đã cài; reload là thao tác do người vận hành thực hiện sau đó.
nginx -t
# Kiểm Web VM qua edge, không đổi database hoặc tạo traffic tấn công.
curl -i http://192.168.10.1/api/auth/csrf
```

Trên Web VM, kiểm listener8080/5173 ởloopback và listenerWebVM80; `/api/auth/csrf` quaedge trả200 kèmX-Request-Id; audit JSONL có cùngrequest_id, client_ip làIP client thay vìproxy, user_agent không bị bỏ trống nếu request cóheader. Đối chiếu vớiNginx structured log tạiSecurity.

Trong Security DB, dùng cùngrequestID thu được để truy vấn có tham số hoặc clientSQL an toàn:

```sql
SELECT source, request_id, client_ip, uri_path, status_code
FROM normalized_events
WHERE request_id = '<request_id_vua_kiem_tra>'
ORDER BY id;
```

Phải thấy observationNGINX vàSTUDENT_AUDIT; đây là hai quan sát của một request, không phải hai cuộc tấn công. Testunit/integration/local/offline đãPASS ở máy tác giả không thay cho việc nghiệm thu topology trênVM của bạn cùng làm.

## 10. Những gì thường giữ nguyên

IP/subnet/VMware adapters đã hoạt động, dữ liệuStudentDB, credentials đã có, SMTP và tài khoản ứng dụng không cần chuyển sangmáySecurity. Schema/frontend/backend chức năng Student vẫn cùng stack. Chỉ thay đổi những trường hợp thực sự lệch kết nối mới: key/pathaudit, bind/proxyheaders, sourceinstance, migrations, upstream và logtransport. Không dùng bộscriptdemo gộp máy để thay thế cấu hìnhVM cũ đang chạy.
