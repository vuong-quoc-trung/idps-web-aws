# WebSentinel AI-IDPS 0.1.0-beta.2 · Local Monitoring

Gói cài Local dành cho máy Ubuntu 26.04 amd64 riêng. Hai ứng dụng phục vụ trên loopback qua HTTPS. Khi cài xong, mở Student Web ở `https://127.0.0.1/` và Security Web ở `https://127.0.0.1:9443/`. Scorer dùng R37 HGB/URI100 đã huấn luyện, với R36 ExtraTrees làm rollback.

## Yêu cầu

- Ubuntu 26.04 amd64, systemd, cgroup v2, CPU Intel Core Ultra 9 285H có telemetry package/core `coretemp` hợp lệ theo Resource Contract. Mục tiêu 2 vCPU, 4 GiB RAM, 10 GiB trống. Cấu hình đề xuất 4 vCPU, 8 GiB RAM và dung lượng log/backup riêng. Scorer KVM thiếu mapping cảm biến sẽ bị từ chối. Dùng `python3 manage.py hardware-check` từ gói đã xác minh để kiểm tra trước khi cấp root.
- Quyền root để tạo service accounts cục bộ, system units, hai database PostgreSQL 18, ACL Unix socket và một nftables table bảo vệ leg giải mã. Sử dụng máy riêng cho Beta. Cluster PostgreSQL mặc định cần nghe IPv4 loopback 5432 với SCRAM. Dành riêng cổng 443, 9443, 3000, 8080 và loopback 127.77.0.2:18080.
- Cài packages Ubuntu cùng repository phát hành và security updates. Nhật ký nghiệm thu ghi phiên bản cụ thể đã giải được.

```sh
sudo apt-get update
sudo apt-get install acl ca-certificates curl nginx libnginx-mod-http-js nftables \
  openjdk-25-jre-headless openssl postgresql-18 python3-yaml suricata
# On the dedicated Beta machine after a fresh dependencies installation.
sudo systemctl disable --now nginx.service suricata.service
```

## TLS, cài đặt và vận hành

Tải archive và `SHA256SUMS` từ **cùng prerelease**. Đối chiếu checksum trước khi giải nén. Dùng chứng thư có IP SAN `127.0.0.1`, private key tương ứng và CA tin cậy của bạn. Với trình duyệt, dùng CA đã cài vào trust store của chính máy. Với curl, chỉ định CA tường minh. Tài liệu cấu hình root chứa thông tin xác thực được tách khỏi archive. Installer tạo chứng thư và pin riêng cho TLS trên leg Student nội bộ.

```sh
sha256sum -c SHA256SUMS
tar -xzf idps-local-monitoring-0.1.0-beta.2-linux-amd64.tar.gz
cd idps-local-monitoring-0.1.0-beta.2-linux-amd64
python3 manage.py verify
python3 manage.py hardware-check
python3 manage.py fetch-student-deps "$STUDENT_JAR_CACHE"
sudo python3 manage.py preflight
sudo python3 manage.py install --cert "$EDGE_CERT" --key "$EDGE_KEY" --ca "$EDGE_CA" \
  --student-cache "$STUDENT_JAR_CACHE"
sudo python3 manage.py health
```

Maven Central cung cấp các JAR đúng phiên bản đã pin. Chạy bước tải bằng user thường. Installer đối chiếu SHA-256 trước khi nhập JAR vào thư mục do root sở hữu. Installer hỏi hai mật khẩu khác nhau và tạo mật khẩu DB ngẫu nhiên. Máy đầu tiên dùng tài khoản `admin` riêng cho mỗi ứng dụng. Model load được kiểm qua Unix socket dưới UID của NGINX. Health trả SHA mặc định `91fe8bad280f7c103adc3601579e350fccd1e3b0de65d43c062aec5b34e60aff`.

Dùng `curl --cacert "$EDGE_CA" -i https://127.0.0.1/api/auth/csrf` để gửi một request kiểm thử. Dùng header `X-Request-Id` từ response để tra `sudo python3 manage.py request ID`, hoặc mở Hybrid trong Security Web sau đăng nhập. Dòng observation đến sau response theo cursor ingest. Nếu model hoặc proof chưa sẵn sàng, giữ trạng thái thiếu nguồn, ABSTAIN hoặc kết quả trễ theo thông tin đã commit. Journal service dùng `journalctl -u websentinel-https-scorer.service`, `journalctl -u websentinel-beta-edge.service` và các unit `websentinel-beta-{student,security,sensor}.service`.

`manage.py start`, `stop` và `restart` điều khiển các unit Beta. Sau một lỗi cứng của guard, đối chiếu journal trước khi xử lý guard table. Khi xoay sensor theo kế hoạch, dừng phát request mới, chờ generation mới và đọc trạng thái các flow cũ qua helper `proof-flow-readiness.py` trong gói. Cơ chế scoring không đặt lại cutoff 1.000 ms hay guard 1 ms.

## Backup và rollback

- `sudo python3 manage.py backup /PATH/backup-moi` ghi hai dump PostgreSQL, SQLite online backup nếu đã khởi tạo và SHA-256. Thư mục backup phải mới và do người quản trị quản lý. Mỗi DB được snapshot nhất quán riêng. Khi cần đồng bộ toàn hệ thống, dừng máy Beta và sao lưu thêm state, log/cursor, release pin và cấu hình bằng kho mã hóa kiểm soát quyền.
- `sudo python3 manage.py restore-test /PATH/backup-moi rehearsal` kiểm checksum và phục hồi vào hai database mới. Thực hiện cutover DB sau đối chiếu riêng trên host có bản ghi phục hồi đã kiểm.
- `sudo python3 manage.py model rollback` chuyển sang R36. `model candidate` quay về R37. `health` xác minh SHA hoạt động. Đây là bản cài đầu tiên của profile. Nâng cấp DB từ triển khai cũ cần rehearsal và snapshot riêng.
- `sudo python3 manage.py uninstall` dừng và gỡ system units Beta. Trạng thái PostgreSQL, release, cấu hình và guard deny-only được giữ cho phục hồi. Khi gỡ toàn bộ máy Beta, quản trị viên có thể lưu snapshot và xử lý các thư mục/DB riêng đã ghi trong manifest triển khai.

## Chẩn đoán và nâng cấp

- Nếu hệ thống chưa healthy, kiểm Student Web đã mở cổng backend 8080 và đã hoàn tất Flyway. Đối chiếu `journalctl -u websentinel-beta-student.service` trước khi thử lại.
- Nếu điểm R37 hoặc Student Audit thiếu, dùng `sudo python3 manage.py health` kiểm mức truy cập của UID Rust. Thư mục journal scorer cấp quyền đọc và liệt kê cho group riêng của scorer và Security Web. SQLite vẫn ở thư mục riêng. Audit dùng thư mục setgid và journal 0640 dành cho nhóm evidence. Khi xoay Audit, đổi tên file cũ và để exporter tạo file mới cùng group.
- Installer dành cho máy riêng và yêu cầu profile sạch. Để chuyển từ Beta.1, sao lưu cả database, SQLite và cấu hình trước, thử restore trong staging mới rồi chuyển sang máy đã nghiệm thu.

## Phạm vi thử nghiệm

R37 đạt 86,04% recall và 0,41% FPR trên WAF development benchmark. Chuyển giao sang Notes và SR-BH còn hạn chế. Số đo development phụ thuộc cohort. Native HTTPS độc lập chưa đạt T07. Profile Beta dùng Hybrid để quan sát và cảnh báo. C2 execution đóng, Auto Block OFF. TLS, HTTP status và một score riêng lẻ chưa xác lập nguồn S và nhãn attack. Không cần dataset, private checkpoint hay huấn luyện.
