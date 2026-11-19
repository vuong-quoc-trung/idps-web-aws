# HTTPS lab: TLS termination trên Security Host

Client → HTTPS :443 → NGINX → **HTTP** Student VM :80; Suricata passive
vmnet3 tiếp tục đọc HTTP. HTTP :80 vẫn hoạt động, không redirect/HSTS.
Không sửa Rust, database, Suricata, AI Worker hoặc firewall.

## Thiết kế và trạng thái kiểm thử

`pbl4-proxy.conf` dùng chung server block và các location cho HTTP/HTTPS.
TLS 1.2/1.3; session tickets tắt. Giữ nguyên admission limits, body limit,
timeouts, XFF=$remote_addr, X-Real-IP, X-Request-Id và X-Forwarded-Proto=$scheme.
Upstream luôn HTTP. AI Unix socket và hai access log không đổi.

`sync-nginx-edge.py` nhận `--tls-cert` + `--tls-key`. Những lần sync tiếp theo
không truyền cặp này sẽ đọc lại đường dẫn từ site HTTPS được quản lý trên đĩa.
`--disable-https` là cách gỡ HTTPS rõ ràng. HTTPS ngoài định dạng được quản lý
bị từ chối khi tự suy ra cấu hình, không âm thầm bị thay thế. IP host/LAN/upstream
vẫn phải truyền theo môi trường như trước; LAN tùy chọn không hardcode.
`prepare-nginx-host.py` chỉ render: phải truyền cặp TLS nếu dùng để staging HTTPS;
không dùng bản HTTP render mặc định để ghi đè site đã bật HTTPS.
AI installer giữ nguyên site đã có marker, bao gồm HTTPS.

Đã kiểm thử NGINX cô lập, chứng chỉ tạm SAN loopback và upstream HTTP giả:
TLS 1.2/1.3, IP SAN đúng/sai, HTTP song song, 200/401/403/429/413,
XFF/request ID, các signal và telemetry đã che dữ liệu nhạy cảm.
Telemetry test dùng file sink thay Unix socket thật. Chưa nghiệm thu worker AI,
Student Web, Suricata, DB/API/Dashboard trên traffic HTTPS lab thật.
`nginx -T` runtime cần sudo tương tác; mới đọc site trên đĩa, không khẳng định
đã xác minh toàn bộ includes hoặc trạng thái cấu hình của tiến trình đang chạy.

## 1. Kiểm tra và tạo chứng chỉ (người vận hành chạy)

Chạy từ root repository trên Defender, kiểm tra đúng interface/IP trước:

```bash
ip -br addr
sudo nginx -T
systemctl is-active nginx suricata pbl4-ai-shadow
```

Tạo key ngoài Git, quyền 600, chứng chỉ chỉ dùng lab. Lệnh sau từ chối ghi đè
chứng chỉ/key hiện có. Nếu cần thêm IP LAN, thêm `,IP:IP_LAN_THUC_TE` vào SAN;
không dùng chứng chỉ IP này cho hostname/IP khác.

```bash
sudo install -d -m 700 /etc/nginx/pbl4-tls
sudo sh -c '
set -eu
cd /etc/nginx/pbl4-tls
test ! -e lab.key && test ! -e lab.crt
umask 077
openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 90 \
  -subj "/CN=WebSentinel Lab" \
  -addext "subjectAltName=IP:192.168.10.1" \
  -addext "extendedKeyUsage=serverAuth" \
  -keyout lab.key -out lab.crt
chmod 600 lab.key
chmod 644 lab.crt
'
sudo openssl x509 -in /etc/nginx/pbl4-tls/lab.crt -noout \
  -dates -ext subjectAltName -fingerprint -sha256
```

Chỉ chuyển **lab.crt** sang Kali/client qua kênh tin cậy và đối chiếu fingerprint.
Không chuyển private key. Dùng `curl --cacert ./lab.crt`, không dùng `-k` để
nghiệm thu TLS. Trình duyệt cần tin cậy chứng chỉ lab riêng; tự ký không mặc
định được tin cậy. Không commit key/chứng chỉ máy vào repository.

## 2. Staging, backup và áp dụng

```bash
python3 security-web/scripts/prepare-nginx-host.py \
  --host-ip 192.168.10.1 --upstream-ip 192.168.20.10 \
  --tls-cert /etc/nginx/pbl4-tls/lab.crt \
  --tls-key /etc/nginx/pbl4-tls/lab.key --output /tmp/pbl4-https-stage
sudo python3 security-web/scripts/prepare-nginx-host.py \
  --tls-cert /etc/nginx/pbl4-tls/lab.crt \
  --tls-key /etc/nginx/pbl4-tls/lab.key \
  --output /tmp/pbl4-https-stage --check-system
sudo python3 security-web/scripts/sync-nginx-edge.py \
  --host-ip 192.168.10.1 --upstream-ip 192.168.20.10 \
  --tls-cert /etc/nginx/pbl4-tls/lab.crt \
  --tls-key /etc/nginx/pbl4-tls/lab.key --apply
sudo nginx -t
sudo ss -ltnp '( sport = :80 or sport = :443 )'
```

`--check-system` dùng `nginx -t` với các includes hiện có nhưng site candidate;
không reload. `--apply` kiểm tra candidate, backup site + format tại
`/var/backups/pbl4-nginx-edge/<timestamp>/rollback.json`, cài atomically từng file,
`nginx -t`, rồi reload nếu đang chạy hoặc start nếu dừng. Ghi lại đường dẫn backup
được in ra. Khi lỗi, script khôi phục file và báo lỗi phục hồi riêng nếu có.
Không tự mở firewall; nếu client không kết nối được 443, kiểm tra chính sách
mạng hiện có trước. Giữ AUTO_BLOCK=false và ENFORCEMENT_MODE=OFF.

Các lần sync sau không mất TLS:

```bash
sudo python3 security-web/scripts/sync-nginx-edge.py --apply
```

Nếu dùng LAN, thêm `--lan-ip IP_LAN_THUC_TE` vào **mọi lần** render/sync và cấp
SAN tương ứng. Không đổi upstream thành HTTPS.

## 3. Nghiệm thu từ Kali/client được phép

```bash
export TARGET=https://192.168.10.1
export LAB_CERT=./lab.crt
curl --noproxy '*' --cacert "$LAB_CERT" -i --max-time 10 "$TARGET/"
curl --noproxy '*' --cacert "$LAB_CERT" -i --max-time 10 "$TARGET/api/auth/me"
curl --noproxy '*' --cacert "$LAB_CERT" -i --max-time 10 "$TARGET/.env"
curl --noproxy '*' -I --max-time 10 http://192.168.10.1/
openssl s_client -connect 192.168.10.1:443 -CAfile "$LAB_CERT" \
  -verify_ip 192.168.10.1 -verify_return_error -tls1_2 </dev/null
openssl s_client -connect 192.168.10.1:443 -CAfile "$LAB_CERT" \
  -verify_ip 192.168.10.1 -verify_return_error -tls1_3 </dev/null
```

200 tùy trang Student hiện có; `/api/auth/me` chưa đăng nhập dự kiến401;
`/.env` bị NGINX chặn403. 401/403 không phải lỗi TLS. HTTP vẫn trả response,
không bị NGINX ép sang HTTPS. Kiểm tra đăng nhập/session/CSRF Student riêng
bằng tài khoản lab; không thay cấu hình Student nếu gặp khác biệt forwarded scheme.

Probe không sửa dữ liệu, lưu response headers để lấy X-Request-Id:

```bash
curl --noproxy '*' --cacert "$LAB_CERT" --max-time 10 -D /tmp/xss.headers \
  -o /dev/null --get --data-urlencode 'q=<script>alert(1)</script>' "$TARGET/api/probe"
curl --noproxy '*' --cacert "$LAB_CERT" --max-time 10 -D /tmp/sqli.headers \
  -o /dev/null --get --data-urlencode "q=1' OR '1'='1" "$TARGET/api/probe"
```

Trên Defender, quan sát HTTP nội bộ (không ghi payload/cookie bằng tcpdump):

```bash
sudo timeout 30 tcpdump -ni vmnet3 -c 30 'host 192.168.20.10 and tcp port 80'
sudo tail -n 100 /var/log/suricata/eve.json | jq -c \
 'select(.event_type=="alert" or .event_type=="http") | {timestamp,event_type,src_ip,dest_ip,flow_id,tx_id,sid:.alert.signature_id,xff:(.alert.xff // .http.xff),method:.http.http_method}'
sudo tail -n 30 /var/log/nginx/access.log | jq -c '{request_id,status,rule_signals}'
systemctl is-active pbl4-ai-shadow
```

Đối chiếu SID1000002/1000003, network_src_ip=192.168.20.1,
Client IP Verified=IP client thực tế (Kali thường192.168.10.10; chạy từ Host
có thể192.168.10.1). Dùng flow_id+tx_id đối chiếu EVE; không giả định EVE luôn
có X-Request-Id. Trên Dashboard kiểm tra cảnh báo mới, request ID NGINX/Audit,
AI Shadow SCORED cùng request nếu worker READY. Worker chưa chạy thì ghi rõ
AI chưa nghiệm thu, không coi HTTP thành công là bằng chứng AI hoạt động.
Request403/429/413 ở edge không được xuất hiện như HTTP request đã tới VM.

429/413 đã có test cô lập. Nếu muốn nghiệm thu thực tế, chỉ chạy trên lab với
sự đồng ý của người vận hành: 9 POST rỗng tới endpoint auth không thay dữ liệu,
hoặc body >1MiB tới `/api/probe`; giới hạn max-time10 mỗi request. Kiểm tra log
và upstream không nhận request bị từ chối; không dùng flood kéo dài.

Ví dụ kiểm tra giới hạn (chỉ chạy sau khi xác nhận lab):

```bash
# Tối đa 9 request rỗng, không dùng tài khoản/password thật.
for i in $(seq 1 9); do
  curl --noproxy '*' --cacert "$LAB_CERT" --max-time 10 -sS -o /dev/null \
    -w '%{http_code}\n' -X POST --data '' "$TARGET/api/auth/reset-password"
done
# Body 1MiB + 1 byte; NGINX phải trả413 trước khi chuyển upstream.
python3 -c 'import sys; sys.stdout.buffer.write(b"x" * (1048576 + 1))' | \
  curl --noproxy '*' --cacert "$LAB_CERT" --max-time 10 -sS -o /dev/null \
    -w '%{http_code}\n' -X POST --data-binary @- "$TARGET/api/probe"
```

429 phụ thuộc tốc độ thực tế và trạng thái bucket; nếu chưa đạt ngưỡng do mạng
chậm, ghi nhận chưa nghiệm thu thay vì tự tăng số request không giới hạn.

## 4. Rollback

Chỉ gỡ HTTPS, giữ cấu hình HTTP hiện tại và AI/Edge Protection:

```bash
sudo python3 security-web/scripts/sync-nginx-edge.py --disable-https --apply
sudo nginx -t
```

Hoặc khôi phục chính xác site/formats trước lần apply bằng manifest đã lưu:

```bash
sudo python3 security-web/scripts/sync-nginx-edge.py \
  --rollback /var/backups/pbl4-nginx-edge/THOI_DIEM_BACKUP/rollback.json
```

Rollback không thay Suricata/Rust/DB. Key giữ lại ngoài Git để có thể bật lại;
không xóa key đang được site khác sử dụng. Không đổi profile, SID hoặc XFF.

## Tests

```bash
python3 security-web/scripts/test-sync-nginx-edge.py
python3 security-web/scripts/test-nginx-host.py
python3 security-web/scripts/test-nginx-https.py
```

Cần nginx, openssl và quyền tạo socket loopback; không cần quyền root.
