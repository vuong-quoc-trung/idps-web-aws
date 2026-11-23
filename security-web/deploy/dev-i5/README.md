# WebSentinel R37 trên Core i5-12450HX (development)

Chạy trên kernel của Ubuntu Host bằng systemd-nspawn, với rootfs Ubuntu 26.04, systemd, loopback, firewall và PostgreSQL **riêng**. VMware tiếp tục dùng mạng và dịch vụ cũ. Đây là profile development cho mã tin cậy, dùng chung kernel và cảm biến vật lý. Trạng thái đã thử gồm build từ archive chính thức, kiểm checksum, hardware admission trên host và một inference R37 thật. Chưa nghiệm thu full-stack trong nspawn trên máy này.

## 1. Chuẩn bị bằng tài khoản thường trên Host

Từ root repository, chạy Bash. Dùng thư mục mới. Cần mạng để tải archive và JAR. Bộ dựng kiểm SHA-256 archive theo evidence R42 ngay trước khi giải nén. Nó tạo một cây dev riêng, giữ nguyên collector chính thức, binary, ONNX, ngưỡng scoring và rules. Installer và guardian **của bản dev** dùng chung collector dành riêng cho đúng chuỗi model i5, yêu cầu cả cảm biến package lẫn core, giới hạn phần cứng hợp lệ và alarm đọc được. Ngưỡng dừng dev tối đa 85°C, hoặc sớm hơn nếu cảm biến/platform báo nguy hiểm. Đây là ngưỡng bảo thủ do profile chọn.

```bash
DEV="$HOME/ws-i5-development"
mkdir -m 700 "$DEV" || exit 1
curl -fL --retry 2 -o "$DEV/beta.tgz" https://github.com/vuong-quoc-trung/idps-web-aws/releases/download/v0.1.0-beta.2/idps-local-monitoring-0.1.0-beta.2-linux-amd64.tar.gz &&
python3 security-web/deploy/dev-i5/prepare.py "$DEV/beta.tgz" "$DEV/profile" &&
python3 -B "$DEV/profile/manage.py" verify &&
python3 -B "$DEV/profile/manage.py" hardware-check &&
python3 -B "$DEV/profile/manage.py" fetch-student-deps "$DEV/jars"
```

Dừng nếu có lỗi. Bước verify trên host cần Python 3 có PyYAML. Bản chính thức giới hạn Ultra 9 285H ở cả installer lẫn guardian. Installer yêu cầu PostgreSQL 18, systemd/cgroup v2 và từ chối khi NGINX/Suricata distro đang active. Không chạy installer trên rootfs Host.

## 2. Tạo rootfs riêng một lần

Host cần systemd-container (nspawn, machinectl), mmdebstrap và Ubuntu archive keyring. Nếu thiếu, cài riêng công cụ host như dưới. Các gói NGINX, Suricata và PostgreSQL chỉ được cài vào rootfs dev. Dành tối thiểu 10 GiB đĩa trống; kiểm tra RAM khả dụng khi VMware đang chạy. Không khởi động máy dev khi host đang chịu áp lực bộ nhớ.

```bash
sudo apt-get install --no-install-recommends systemd-container mmdebstrap ubuntu-keyring
ROOTFS=/var/lib/machines/ws-i5-dev
test ! -e "$ROOTFS" || { echo 'Rootfs đã tồn tại; dừng để tránh ghi đè'; exit 1; }
sudo mkdir -p /var/lib/machines
sudo mmdebstrap --variant=minbase --components=main,universe \
  --include=systemd-sysv,dbus,libpam-systemd,iproute2,acl,ca-certificates,curl,nginx,libnginx-mod-http-js,nftables,openjdk-25-jre-headless,openssl,postgresql-18,python3-yaml,suricata \
  resolute "$ROOTFS" \
  'deb https://archive.ubuntu.com/ubuntu resolute main universe' \
  'deb https://archive.ubuntu.com/ubuntu resolute-updates main universe' \
  'deb https://security.ubuntu.com/ubuntu resolute-security main universe'
sudo install -d -m 0700 "$ROOTFS/root/ws"
sudo cp -r -- "$DEV/profile" "$DEV/jars" "$ROOTFS/root/ws/"
sudo chown -R root:root "$ROOTFS/root/ws"
sudo systemctl --root="$ROOTFS" mask nginx.service suricata.service
```

## 3. Boot máy dev

Trên host, giữ terminal này mở. Dùng lại đúng lệnh boot sau mỗi lần poweroff. Không thêm veth, bridge, mount /run hay thư mục PostgreSQL/NGINX của Host. Trần tài nguyên đề xuất cho cả máy dev là 3 CPU và 4 GiB; các giới hạn con của scorer tiếp tục áp dụng. Các cảm biến phải thấy qua sysfs read-only trong guest. Nếu admission trong guest từ chối, dừng trước install.

```bash
sudo systemd-nspawn --settings=no -D /var/lib/machines/ws-i5-dev -M ws-i5-dev \
  --hostname=ws-i5-dev --boot --private-network --private-users=no \
  --capability=CAP_NET_ADMIN,CAP_NET_RAW --property=CPUQuota=300% \
  --property=MemoryMax=4G --property=MemorySwapMax=0
```

Mở terminal thứ hai trên Host:

```bash
sudo machinectl shell root@ws-i5-dev /bin/bash
```

**Tất cả các lệnh tiếp theo đến hết bước 5 chạy trong shell guest này.** Xác nhận hostname, chỉ có lo và cgroup có cpu, memory, pids trước khi tiếp tục. Các lệnh quản trị của profile dev kiểm tên máy, nspawn và loopback. PostgreSQL port 5432, Rust 3000, Java 8080, ingress 443/9443 và leg 127.77.0.2:18080 đều nằm trong namespace dev.

```bash
hostname
ip -br link
cat /sys/fs/cgroup/cgroup.controllers
cd /root/ws/profile
python3 -B manage.py hardware-check && python3 -B manage.py preflight
```

## 4. TLS dev, install và start

Tạo CA dev và leaf IP SAN dùng riêng trong guest, chỉ thực hiện một lần. Dừng khi một lệnh lỗi. Installer hỏi mật khẩu admin riêng cho Student và Security, tạo DB/role trong PostgreSQL của guest, cài và khởi động các unit Beta.

```bash
set -e
umask 077
mkdir -m 700 /root/ws/pki
cd /root/ws/pki
openssl req -x509 -newkey rsa:3072 -nodes -days 365 -subj /CN=WS-i5-dev-CA \
  -addext basicConstraints=critical,CA:TRUE -addext keyUsage=critical,keyCertSign,cRLSign \
  -keyout ca.key -out ca.crt
openssl req -new -newkey rsa:2048 -nodes -subj /CN=ws-i5-dev -keyout edge.key -out edge.csr
printf '%s\n' 'basicConstraints=critical,CA:FALSE' 'extendedKeyUsage=serverAuth' 'subjectAltName=IP:127.0.0.1' > edge.ext
openssl x509 -req -in edge.csr -CA ca.crt -CAkey ca.key -CAcreateserial -days 90 -extfile edge.ext -out edge.crt
umask 022
cd /root/ws/profile
python3 -B manage.py install --cert /root/ws/pki/edge.crt --key /root/ws/pki/edge.key \
  --ca /root/ws/pki/ca.crt --student-cache /root/ws/jars
python3 -B manage.py health
```

Sau các lần boot tiếp theo dùng `cd /root/ws/profile && python3 -B manage.py start && python3 -B manage.py health`. Khi install hoặc health lỗi, xem journal **trong guest** của websentinel-https-scorer, websentinel-beta-{edge,student,sensor,security} và postgresql@18-main. Lỗi cgroup delegation, guard hoặc sensor là điều kiện dừng; giữ nguyên các kiểm tra và ranh giới namespace.

## 5. Kiểm tra HTTPS → AI → Hybrid

```bash
cd /root/ws/profile
curl --fail --cacert /root/ws/pki/ca.crt -sS -D /root/ws/headers -o /dev/null https://127.0.0.1/api/auth/csrf
RID=$(awk 'tolower($1)=="x-request-id:" {gsub(/\r/,"",$2);print $2}' /root/ws/headers)
python3 -B manage.py request "$RID"
curl --cacert /root/ws/pki/ca.crt -sS -o /dev/null -w 'Security HTTPS %{http_code}\n' https://127.0.0.1:9443/
```

Đợi ingest rồi tra lại cùng RID nếu nhận NOT_INGESTED. Nghiệm thu khi health đúng SHA R37 `91fe8bad280f7c103adc3601579e350fccd1e3b0de65d43c062aec5b34e60aff`, Hybrid có research score đúng request và automatic_block tắt. HTTP 200 riêng lẻ chưa chứng minh AI hoạt động.

## 6. Truy cập trình duyệt Host khi cần

Guest chỉ có loopback. Có thể proxy **một cổng localhost của Host** tới Dashboard mà không đổi interface VMware hay firewall. Chạy trong terminal Host, kiểm tra cổng 19443 đang trống; giữ terminal mở, Ctrl+C để gỡ listener. systemd-socket-activate truyền listening FD vào socket-proxyd sau khi nsenter chuyển network namespace.

```bash
pid=$(machinectl show ws-i5-dev -p Leader --value)
sudo systemd-socket-activate -l 127.0.0.1:19443 nsenter --no-fork -t "$pid" -n /usr/lib/systemd/systemd-socket-proxyd 127.0.0.1:9443
```

Mở https://127.0.0.1:19443/ trên Host. Nếu cần Student UI, dùng terminal khác, đổi listener thành 10443 và đích thành 127.0.0.1:443. Để xác minh TLS, chỉ xuất CA công khai bằng `sudo machinectl copy-from ws-i5-dev /root/ws/pki/ca.crt "$HOME/ws-i5-development/dev-ca.crt"`, tin cậy CA trong profile trình duyệt dev riêng. Không xuất private key.

## Dừng

Trong guest: `cd /root/ws/profile && python3 -B manage.py stop`. Trên Host dừng các terminal proxy rồi chạy `sudo machinectl poweroff ws-i5-dev`. Rootfs và dữ liệu dev được giữ cho lần sau. Không dùng lệnh stop/restart NGINX, Suricata hoặc PostgreSQL của Host.
