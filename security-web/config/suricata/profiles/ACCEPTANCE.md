# Nghiệm thu tích hợp Suricata post-proxy → Rust → Dashboard

**Trạng thái:** code/test offline; chưa chuyển runtime, chưa nghiệm thu hệ thống thật.
Đây là checklist cho một đợt chuyển đổi; các lệnh sudo do người vận hành thực hiện.
Không chạy đồng thời hai Suricata. Giữ AUTO_BLOCK=false, ENFORCEMENT_MODE=OFF.

## 1. Hợp đồng tin cậy và thay đổi dữ liệu

- `SURICATA_CAPTURE_MODE=post-proxy`: tất cả EVE giữ IP mạng riêng; không có
  bằng chứng thì `client_ip=null`. Mặc định vẫn là `pre-proxy` để giữ cách đọc cũ.
- `SURICATA_TRUSTED_EDGE_CONFIRMED=true` là xác nhận của người vận hành, KHÔNG
  phải phát hiện topology tự động. Chỉ bật khi đã kiểm tra NGINX ghi đè XFF bằng
  `$remote_addr`, không có cấu hình real_ip tin header của client bừa bãi, VM
  chỉ nhận HTTP từ proxy, attacker không có quyền truy cập mạng backend/EVE.
- Cần đồng thời: src_ip=proxy đã cấu hình, dest_ip=VM, dest_port=80, TCP,
  app_proto=http, in_iface=vmnet3, flow_id và tx_id hợp lệ, một IP XFF hợp lệ.
- Suricata 8.0.3 được test: dùng `alert.xff` cho alert, `http.xff` cho HTTP.
  Không lấy XFF từ sự kiện HTTP khác, không cache theo flow, không ghép thời gian.
  Nếu các vị trí XFF mâu thuẫn thì không xác minh. Thiếu tx_id: không xác minh.
- `suricata_origin` trong canonical giữ network_src_ip, tx_id, post_proxy và
  client_ip_verified. Flow_id/source_instance tiếp tục ở các trường có sẵn.
- Migration **0014_suricata_origin.sql** chỉ thêm cột nullable vào security_alerts:
  client_ip, network_src_ip, client_ip_verified, suricata_post_proxy và index.
  normalized_events giữ metadata trong canonical JSONB có sẵn. Không backfill.
- src_ip của bản ghi cảnh báo mới là client đã xác minh hoặc NULL ở post-proxy;
  dữ liệu EVE gốc không bị ghi đè. API chi tiết/tìm kiếm/recent có các cột mới.
  Lọc IP tìm được cả client và network; top IP nhóm riêng client/network.
  Bản ghi pre-proxy/lịch sử được ghi nhãn IP mạng, không tự nâng thành Verified.
- AUTO response luôn bị vô hiệu cho event post-proxy; startup post-proxy từ chối
  AUTO_BLOCK khác false hoặc ENFORCEMENT_MODE khác OFF. IP proxy cấu hình được bảo
  vệ ở firewall::validate, kể cả thao tác thủ công. Cơ chế block/unblock khác giữ nguyên.
- Dedup/checkpoint/event_key giữ nguyên. Không sinh alert thứ hai để bổ sung IP.
  Alert đến trước/sau HTTP đều độc lập; replay không cần cache attribution RAM.
  Sự kiện EVE thô vẫn dùng cơ chế identity/offset hiện có, không hứa dedup mọi bản
  sao file độc lập không có sensor_event_id.

XFF không phải chữ ký mật mã. Host NGINX/EVE bị chiếm quyền hoặc backend network
cho phép giả IP sẽ phá giả định tin cậy. Chưa xác minh điều kiện này thì để cờ false.
Request ID NGINX vẫn liên kết với Audit/AI; EVE không xuất X-Request-Id tùy ý trong
profile này. Không bật dump-all-headers để lấy ID. Không tuyên bố correlation ba
nguồn chính xác chỉ vì IP/thời gian giống nhau. IP không định danh tài khoản.

## 2. Chuẩn bị trước cửa sổ nghiệm thu

Từ repository root:

```bash
git status --short
cargo fmt --manifest-path security-web/Cargo.toml --check
cargo check --offline --manifest-path security-web/Cargo.toml
python3 security-web/scripts/test-suricata-post-proxy.py
(cd security-web/frontend && npm test && npm run build)
systemctl status nginx suricata pbl4-ai-shadow --no-pager
sudo nginx -T  # xem tại máy; không đưa toàn bộ output chứa dữ liệu riêng vào Git
ip -br addr show vmnet3
ip route get 192.168.20.10
curl --noproxy '*' --max-time 5 -o /dev/null -w '%{http_code}\n' http://192.168.20.10/api/auth/me
```

Kiểm tra NGINX nạp đúng upstream, XFF/X-Real-IP=$remote_addr, X-Request-Id=$request_id;
không có override ở location khác. Kiểm tra cấu hình mạng/firewall VM hiện có:
Kali và LAN không được truy cập thẳng Student VM:80. **Nếu vẫn truy cập được, dừng
nghiệm thu tin cậy**, xử lý mạng bằng quy trình riêng, không tự bật cờ xác nhận.
Không có thay đổi firewall hay Student Web trong bản cập nhật này.

Backup DB theo quy trình hiện có trước migration. Backend chạy migration tự động
khi khởi động; xem SQL 0014 trước khi chạy. Không sửa migration lịch sử.
Ghi số lượng alert, phiên bản code, thời gian UTC, trạng thái AI/Audit/edge và
firewall actions để so sánh sau. Không xóa log/DB, không xuất cookie/token.

Chuẩn bị environment cho **đúng tiến trình Rust** (không chỉ shell khác):

```bash
export AUTO_BLOCK=false ENFORCEMENT_MODE=OFF
export SURICATA_CAPTURE_MODE=post-proxy
export SURICATA_TRUSTED_EDGE_CONFIRMED=true  # CHỈ sau khi kiểm tra boundary phía trên
export SURICATA_PROXY_IP=192.168.20.1 SURICATA_WEB_IP=192.168.20.10
export SURICATA_WEB_PORT=80 SURICATA_POST_PROXY_INTERFACE=vmnet3
```

Giữ đường dẫn EVE, SENSOR_ID, DB và môi trường AI hiện có. Không khởi chạy thêm
Rust thứ hai trên cùng ingestion. Dừng instance cũ bằng quy trình đang dùng rồi
khởi động bản đã build với environment này. Giữ cờ an toàn cả trong .env/systemd.
Không phát request thử cho đến khi hoàn thành bước chuyển capture bên dưới.

## 3. Backup và chuyển một service Suricata

Làm lần lượt mục **Stage and validate** và **Operator-only activation** trong
[README](README.md#stage-and-validate-no-deployment). Các lệnh ở đó tạo snapshot
pre-proxy byte-for-byte, lưu hash rule, chạy `suricata -T`, backup `/etc/suricata`,
rule và unit, rồi cài duy nhất drop-in `90-pbl4-post-proxy.conf`.
Không ghi đè snapshot/drop-in tồn tại mà chưa kiểm tra. Khi restart xong:

```bash
systemctl status suricata --no-pager -l
ps -eo pid,args | grep '[s]uricata'
sudo journalctl -u suricata -n 50 --no-pager
sudo timeout 60 tcpdump -ni vmnet3 -c 80 'host 192.168.20.1 and host 192.168.20.10 and tcp port 80'
```

Chạy capture ở terminal riêng trong khi làm bước 4. Phải thấy request và response;
chỉ trạng thái running không đủ. Không lưu PCAP thật/cookie/body vào báo cáo.

## 4. Một đợt request từ Kali (không chạy từ proxy)

```bash
export EDGE=http://192.168.10.1
curl --noproxy '*' --max-time 5 -sS -D - -o /dev/null "$EDGE/api/auth/me"
curl --noproxy '*' --max-time 5 -sS -D - -o /dev/null --get --data-urlencode "q=' OR 1=1" "$EDGE/api/probe"
curl --noproxy '*' --max-time 5 -sS -D - -o /dev/null --get --data-urlencode 'q=<script>alert(1)</script>' "$EDGE/api/probe"
curl --noproxy '*' --max-time 5 -sS -D - -o /dev/null --get --data-urlencode 'file=../../etc/passwd' "$EDGE/api/probe"
# Header giả phải bị NGINX ghi đè; tuyệt đối không thành 198.51.100.99 trong Verified:
curl --noproxy '*' --max-time 5 -sS -D - -o /dev/null -H 'X-Forwarded-For: 198.51.100.99' --get --data-urlencode "q=' OR 1=1" "$EDGE/api/probe"
# Edge từ chối: không được coi là request đã đến VM:
curl --noproxy '*' --max-time 5 -sS -D - -o /dev/null "$EDGE/.env"
```

Ghi UTC và request ID trả về. 401/404 không đồng nghĩa detector thất bại. `/.env`
phải bị NGINX từ chối và không xuất hiện ở upstream; dùng capture yên tĩnh cùng
NGINX log để kiểm tra, không suy ra từ việc thiếu một alert.

## 5. Đối chiếu một chuỗi bằng chứng

- EVE mới: SID1000002/3/4, src_ip=.20.1, dest_ip=.20.10, in_iface=vmnet3,
  flow_id, tx_id, alert.xff=.10.10. Dùng output chọn trường, không in toàn payload:

```bash
sudo tail -n 300 /var/log/suricata/eve.json | jq -c 'select(.event_type=="alert") | {timestamp,in_iface,src_ip,dest_ip,flow_id,tx_id,app_proto,sid:.alert.signature_id,xff:.alert.xff}'
```

- Rust: watcher không lỗi, checkpoint tăng, không có ingestion_errors mới.
- Trong phiên PostgreSQL **chỉ đọc**, đối chiếu các hàng mới:

```sql
SELECT id,occurred_at,source,host(src_ip),host(client_ip),host(network_src_ip),
       client_ip_verified,suricata_post_proxy,
       evidence::jsonb->>'flow_id' AS flow_id,
       evidence::jsonb->'suricata_origin'->>'tx_id' AS tx_id
FROM security_alerts WHERE source='SURICATA' AND network_src_ip IS NOT NULL
ORDER BY id DESC LIMIT 10;
```

- Dashboard/API bằng phiên viewer: tìm `.10.10` và `.20.1` đều ra cảnh báo phù hợp;
  Client=.10.10 Verified, Network=.20.1, Destination=.20.10. Không hiển thị proxy
  như Attacker. Top IP không gộp network với client. Xem chi tiết canonical tx_id.
- Tạm dừng/khởi động **Rust bằng quy trình hiện tại** một lần, không truncate log:
  không sinh lại alert cũ. Có thể xem watcher/checkpoint trước/sau; không thay DB.
- Baseline mới vẫn có NGINX log, Audit; AI worker có kết quả mới nếu endpoint nằm
  trong phạm vi worker. Score thấp không phải lỗi. Không cần AI alert.
- Kiểm tra edge rate limiting theo quy trình có sẵn bằng bài lab giới hạn đã được
  duyệt; không gửi flood trong checklist này. Đối chiếu 429 và upstream không nhận
  phần bị từ chối. Kiểm thử offline NGINX cũng phải đạt.
- Không có firewall action/block mới do Suricata post-proxy. Rule tần suất của
  Suricata vẫn tính theo proxy IP, không tự chuyển thành bộ đếm theo từng client.

**Chỉ kết luận E2E đạt khi tất cả bước có output thực tế.** Test keep-alive bốn
transaction với XFF khác nhau là PCAP cô lập; không giả XFF qua edge để tạo fixture.

## 6. Rollback

Làm mục [Rollback](README.md#rollback-same-single-service) để bỏ đúng drop-in mới,
`daemon-reload`, `suricata -T` profile gốc và restart đúng service.
Đặt `SURICATA_CAPTURE_MODE=pre-proxy`, `SURICATA_TRUSTED_EDGE_CONFIRMED=false`
cho Rust rồi khởi động lại bằng quy trình cũ. Giữ OFF/false, whitelist và bảo vệ
proxy. Không xóa cột migration 0014 hay các alert đã ghi; không sửa SQLx history.
Không backfill XFF lịch sử. Kiểm tra source network hoạt động lại trên vmnet2.

## 7. Kiểm thử tự động và giới hạn

- Rust unit: `cargo test --offline --manifest-path security-web/Cargo.toml suricata_origin::tests`.
- Parser: `cargo test --offline --manifest-path security-web/Cargo.toml events::tests`.
- Test DB mới: trong `security-web`, với **DATABASE_URL của PostgreSQL kiểm thử
  dùng riêng, có quyền tạo DB**, chạy:
  `cargo test --offline post_proxy_origin_persists_replay_restart_search_and_stats`.
  SQLx tạo DB test/migrations. Không dùng URL DB đồ án. Test đã đạt trên
  PostgreSQL 17 tạm, network none, Unix socket, không volume DB đồ án.
- `python3 security-web/scripts/test-suricata-post-proxy.py` kiểm tra Suricata thật
  offline, gồm -T, SID SQLi/XSS/traversal, keep-alive và redaction.
- `python3 security-web/scripts/test-config-contracts.py` và
  `python3 security-web/scripts/test-nginx-host.py`: NGINX tạm/loopback, không service thật.
- Frontend `npm test && npm run build`: nhãn Verified/Chưa xác minh/lịch sử.

Trước HTTPS: giữ mạng lab tách biệt, không gửi thông tin thật qua HTTP. Nếu đoạn
NGINX→VM chuyển thành HTTPS, sensor passive ở vmnet3 sẽ mất nội dung HTTP;
không coi profile này là cơ chế giải mã TLS. Không bật AUTO_BLOCK dựa vào tài liệu này.

## 8. Kết quả kiểm tra tại workspace (2026-11-15)

| Kiểm tra | Kết quả |
|---|---|
| cargo fmt --check, cargo check --offline | Đạt |
| Toàn bộ Rust unit + SQLx integration | 84/84 đạt trên PostgreSQL 17 cô lập |
| Suricata post-proxy PCAP + -T | 2 đạt |
| Extended Suricata rules | 14 đạt |
| NGINX config contracts | 6 đạt |
| NGINX host/edge/AI | 12 đạt |
| Frontend node tests | 6 file test đạt |
| TypeScript + Vite production build | Đạt |
| Canonical JSON schema | 2 đạt, 1 skip (không cung cấp runtime JSONL) |
| PostgreSQL migration/restart/dedup/API queries | Đạt trong bộ 84 test; không phải runtime thật |
| Browser layout với dữ liệu runtime mới | Chưa nghiệm thu trực quan |
| Capture vmnet3, endpoint thật, Dashboard thật | Chưa thực hiện |

Lần chạy NGINX ban đầu bị sandbox chặn socket; chạy lại test loopback cô lập
ngoài sandbox đã đạt. Lần regression Rust đầu có lỗi kiểm tra tập trường schema;
đã cập nhật test cho metadata tùy chọn theo nguồn. Test nâng cấp DB cũ cần đổi
số migration cố định 13 thành số migration hiện có; đã bổ sung kiểm tra không
tự điền IP lịch sử. Cuối cùng 84/84 test Rust đạt. Container test lúc đầu lỗi
socket khởi tạo; đã sửa bằng cách giữ socket mặc định và thêm socket riêng.
Container cuối dùng network none/tmpfs và đã xóa sau test.
Không có sửa DB thật, reload service, áp dụng profile, commit hoặc push.

Các file của phần attribution:
- `src/suricata_origin.rs`, `events.rs`, `ingest.rs`, `main.rs`, `firewall.rs`.
- `migrations/0014_suricata_origin.sql`.
- `src/alert_search.sql`, `alert_detail.sql`, `overview.sql`.
- `frontend/src/sourceIp.ts`, `main.tsx`, `AlertDetail.tsx`.
- `frontend/tests/source-ip.test.mjs`, `src/foundation_tests.rs`, `integration_tests.rs`.
- `security-web/.env.example`, `contracts/canonical-event-v1.schema.json`, `contracts/README.md`.
- `config/suricata/profiles/README.md` và checklist này.

Các file profile/generator/PCAP của giai đoạn trước vẫn được giữ nguyên trong
working tree chưa commit. Không thay tập rule, NGINX runtime, AI Worker hay Student Web.
