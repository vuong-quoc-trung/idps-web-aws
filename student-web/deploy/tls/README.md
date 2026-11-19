# Giai đoạn B — HTTPS trên NGINX Student VM (chưa áp dụng)

Mục tiêu: cùng site hiện tại phục vụ HTTP :80 và HTTPS 192.168.20.10:443,
frontend -> 127.0.0.1:5173, /api/ -> 127.0.0.1:8080. Không đổi Spring profile,
DB, Audit, Suricata, Edge Protection hay upstream production của Defender.
Không redirect HTTP hoặc bật HSTS ở giai đoạn này.

Repository chưa có site VM tương ứng. prepare.py đọc site thật và chèn TLS vào
cùng server block, giữ nguyên toàn bộ nội dung cũ (location, proxy_pass, URI,
header, WebSocket/HMR, timeout). Nếu có nhiều server, TLS hoặc include không rõ,
script dừng để review thay vì đoán. Phải đọc bản diff trước triển khai. Các cơ chế
header hiện tại được bảo toàn, không có nghĩa đã kiểm chứng chúng đúng; đặc biệt
X-Request-Id, XFF và scheme cần được kiểm tra bằng audit của request lab.

## 1. Chuẩn bị không sudo trên Student VM

Đảm bảo có openssl, python3, nginx; không tự cài package bằng các script này.
Chạy từ root repository:

```bash
bash student-web/deploy/tls/create-lab-cert.sh "$HOME/ws-student-lab-pki"
python3 student-web/deploy/tls/prepare.py \
  --source /etc/nginx/sites-enabled/student-web \
  --output /tmp/student-web.https.candidate
 diff -u /etc/nginx/sites-enabled/student-web /tmp/student-web.https.candidate
```

Output/PKI phải chưa tồn tại. Nếu site không đọc được, operator sao chép nó ra
staging sau khi phê duyệt. Không chạy lại để ghi đè khóa. Lab CA hạn 365 ngày,
leaf 90 ngày, SAN IP:192.168.20.10 và DNS:student.lab, serverAuth. CA key và leaf
key mode600 trong thư mục700 ngoài repo. CA key cần lưu offline sau ký; chỉ leaf
key được cài trên VM, chỉ public ca.crt được chuyển sang Defender. Đây là CA lab,
không phải CA công khai. Không đưa password/key vào Git hoặc chat.

## 2. Điểm phê duyệt — chưa chạy tự động

Trước apply: ghi nhận baseline HTTP / và /api/auth/me, login bằng tài khoản lab,
asset/HMR WebSocket, log Audit + request ID; xác nhận IP còn gắn trên VM, port443
chưa có listener. `sudo nginx -T` để kiểm tra site enabled và xung đột tên/listener;
không chia sẻ output có bí mật. Lưu bản baseline/status để rollback đối chiếu.

Sau khi người dùng phê duyệt, operator chạy TRÊN STUDENT VM:

```bash
sudo nginx -t
sudo bash student-web/deploy/tls/operator-apply.sh apply \
  /tmp/student-web.https.candidate "$HOME/ws-student-lab-pki" \
  /var/backups/student-https-before-UNIQUE
```

Thay UNIQUE bằng mốc mới; thư mục backup phải chưa tồn tại. Script backup site gốc
và đường dẫn thật (giữ symlink sites-enabled), cài leaf key600/cert644 trong thư mục
root700, ghi candidate, nginx -t rồi reload. Không restart backend/frontend/DB.
Nếu nginx-t lỗi: phục hồi site, không reload. Nếu reload lỗi: phục hồi và thử
reload bản cũ, báo lỗi để operator kiểm tra. Thư mục TLS được giữ lại khi lỗi;
không tự chạy apply lại, cần review. Dừng nếu TLS directory đã tồn tại.

Không đổi firewall. Nếu 443 bị chặn, báo rõ và xin phê duyệt riêng. Không mở port
8080/5173 ra ngoài để xử lý lỗi TLS.

## 3. Nghiệm thu từ Security Host (operator chạy)

Chuyển DUY NHẤT ca.crt sang Defender bằng kênh đáng tin và đối chiếu SHA256 hai bên.
Không cài CA vào trust store toàn hệ thống; dùng đường dẫn CA rõ ràng.

```bash
bash student-web/deploy/tls/verify-from-defender.sh /path/to/student-ca.crt
curl --noproxy '*' --max-time 15 -o /dev/null -w '%{http_code}\n' http://192.168.20.10/
```

Script xác minh TLS qua IP và DNS SAN, CA sai/tên sai phải trả curl exit60.
Không coi timeout/refused là negative TLS PASS. HTTP401 tại auth/me chưa đăng nhập
có thể đúng; 5xx không đạt nghiệm thu ứng dụng dù TLS hợp lệ. Kiểm tra thêm browser
trust CA lab, frontend/assets, WebSocket nếu ứng dụng dùng, login/logout, CSRF,
request ID/XFF và log Audit. Không tự test ghi dữ liệu thật. Kiểm tra PostgreSQL
qua health/log hiện có, không chạy migration hoặc thay schema.

## 4. Egress dự kiến — CHƯA đổi Defender production

Giữ IP upstream nhưng xác minh tên DNS SAN rõ ràng, không phụ thuộc DNS resolver:

```nginx
proxy_pass https://192.168.20.10:443;
proxy_ssl_server_name on;
proxy_ssl_name student.lab;
proxy_ssl_trusted_certificate /etc/nginx/student-ca/ca.crt;
proxy_ssl_verify on;
proxy_ssl_verify_depth 2;
proxy_ssl_protocols TLSv1.2 TLSv1.3;
```

Các directive này đã được renderer Egress hiện có hỗ trợ qua --egress-name
student.lab --egress-port 443 --egress-ca PATH. Chỉ chuẩn bị, không chạy sync --apply
ở Defender. Chưa đổi Suricata capture hoặc Rust Shadow/Verified.

## 5. Rollback (Student VM, sau phê duyệt)

```bash
sudo bash student-web/deploy/tls/operator-apply.sh rollback \
  /var/backups/student-https-before-UNIQUE
sudo nginx -t
systemctl status nginx --no-pager -l
```

Khôi phục site gốc, kiểm tra rồi reload. Leaf cert/key giữ lại để điều tra, không
xóa file không liên quan. HTTP80 không bị xóa trong bản HTTPS nên vẫn là đường
rollback. Nếu syntax/health lỗi, dừng và đọc log, không thay DB hay restart các
thành phần không liên quan.

## Kết quả chuẩn bị

6 unit tests PASS; Bash syntax PASS. Tạo PKI tạm không sudo: xác minh IP và DNS đúng
PASS, tên sai bị OpenSSL từ chối. Chưa chạy nginx-t trên candidate VM, chưa apply,
chưa có kết quả TLS mạng thật, login, Audit hoặc WebSocket; không tuyên bố những
mục này đã nghiệm thu. Các script không tự kết nối VM khi chưa operator chạy.
