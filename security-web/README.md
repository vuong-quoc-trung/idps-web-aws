# PBL4 Full Local Demo — Suricata + Nginx/WAF + Rust + PostgreSQL + nftables

This demo implements the first usable end-to-end security loop for the PBL4 lab:

```text
Kali (attacker)
      |
      v
Security VM
  enp1s0 = 192.168.10.1
  +------------------------------+
  | Suricata -> eve.json         |
  | Nginx reverse proxy -> log   |
  | Rust Security Core           |
  | PostgreSQL                   |
  | nftables Response Engine     |
  +------------------------------+
      |
      v
Web Server
192.168.20.10
```

## Detection rules

1. Suricata custom TCP SYN burst / port-scan demo.
2. Rust/Nginx SQL Injection demo rule.

The Rust service can manually BLOCK/UNBLOCK lab attacker IPs through the API/dashboard. `AUTO_BLOCK=false` is the safe default; set it to `true` only after manual blocking is verified.

## 0. Prepare Rust user access to logs

On Security VM:

```bash
sudo usermod -aG adm "$USER"
```

Reconnect the SSH session after the group change.

## 1. PostgreSQL

```bash
cd ~/pbl4-security-demo
sudo apt update
sudo apt install -y docker.io docker-compose-v2
sudo systemctl enable --now docker

docker compose up -d
cp .env.example .env

docker exec -i pbl4-postgres psql -U pbl4 -d pbl4_security < sql/schema.sql

docker compose ps
```

Check tables:

```bash
docker exec -it pbl4-postgres psql -U pbl4 -d pbl4_security -c '\dt'
```

## 2. Suricata custom rule

Copy the rule:

```bash
sudo cp suricata/pbl4.rules /var/lib/suricata/rules/pbl4.rules
sudo chown root:root /var/lib/suricata/rules/pbl4.rules
```

Edit `/etc/suricata/suricata.yaml` and add under `rule-files:` if not already present:

```yaml
  - pbl4.rules
```

Test:

```bash
sudo suricata -T -c /etc/suricata/suricata.yaml
```

Restart:

```bash
sudo systemctl restart suricata
sudo systemctl status suricata --no-pager
```

## 3. Nginx reverse proxy

On Security VM:

```bash
sudo cp nginx/pbl4-proxy.conf /etc/nginx/sites-available/pbl4-proxy
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -s /etc/nginx/sites-available/pbl4-proxy /etc/nginx/sites-enabled/pbl4-proxy
sudo nginx -t
sudo systemctl reload nginx
```

Use the Security VM proxy for the web demo:

```bash
curl http://192.168.10.1/
```

Direct `Kali -> 192.168.20.10:80` is not the WAF path and will be blocked after the PBL4 nftables setup below.

## 4. nftables Response Engine setup

First inspect the current firewall so you have a backup:

```bash
sudo nft list ruleset > ~/nft-before-pbl4.nft
```

Install the persistent PBL4 table:

```bash
sudo mkdir -p /etc/nftables.d
sudo cp scripts/pbl4-demo.nft /etc/nftables.d/pbl4-demo.nft

if [ ! -f /etc/nftables.conf ]; then
  echo 'include "/etc/nftables.d/*.nft"' | sudo tee /etc/nftables.conf >/dev/null
elif ! grep -Fq '/etc/nftables.d/*.nft' /etc/nftables.conf; then
  echo 'include "/etc/nftables.d/*.nft"' | sudo tee -a /etc/nftables.conf >/dev/null
fi

if ! sudo nft list table inet pbl4_demo >/dev/null 2>&1; then
  sudo nft -f /etc/nftables.d/pbl4-demo.nft
fi

sudo systemctl enable --now nftables
sudo nft list table inet pbl4_demo
```

This creates:

- `blocked_ips` set.
- `input` chain that blocks an IP when it targets Security VM.
- `forward` chain that blocks an IP when it is routed through Security VM.
- a baseline rule that prevents Kali from bypassing the Nginx proxy to `192.168.20.10:80`.

### 4.1 Install the restricted firewall helper

```bash
sudo install -m 0755 scripts/pbl4-firewall /usr/local/bin/pbl4-firewall
printf '%s\n' "$USER ALL=(root) NOPASSWD: /usr/local/bin/pbl4-firewall" | sudo tee /etc/sudoers.d/pbl4-security >/dev/null
sudo chmod 0440 /etc/sudoers.d/pbl4-security
sudo visudo -cf /etc/sudoers.d/pbl4-security
```

Test the helper before Rust calls it:

```bash
sudo /usr/local/bin/pbl4-firewall list
sudo /usr/local/bin/pbl4-firewall block 192.168.10.10
sudo nft list set inet pbl4_demo blocked_ips
sudo /usr/local/bin/pbl4-firewall unblock 192.168.10.10
```

Do not use an attacker IP that you need for your current SSH path. The PBL4 helper only allows lab attacker-side `192.168.10.2-254` and is meant for the lab environment.

## 5. Build the Rust Security Core

```bash
cp .env.example .env
cargo check
cargo run
```

The server listens on `0.0.0.0:3000`.

Health check from Security VM:

```bash
curl http://127.0.0.1:3000/health
```

From the host, use the Security VM management IP:

```text
http://192.168.122.X:3000/
```

## 6. Demo A — Nginx SQL Injection detection

On Kali:

```bash
curl 'http://192.168.10.1/login?user=%27%20OR%201%3D1'
```

Rust reads the Nginx access log, detects the pattern, and stores an alert:

```text
NGINX: SQL Injection
source=NGINX
severity=2
action=ALERT
```

Check API:

```bash
curl 'http://127.0.0.1:3000/api/alerts?limit=20'
```

Check PostgreSQL:

```bash
docker exec -it pbl4-postgres psql -U pbl4 -d pbl4_security -c \
"SELECT id,source,rule_name,src_ip,severity,action FROM security_alerts ORDER BY id DESC LIMIT 10;"
```

## 7. Demo B — Suricata TCP SYN scan

On Kali:

```bash
nmap -sS -p 1-100 192.168.10.1
```

Check Suricata:

```bash
sudo tail -n 30 /var/log/suricata/eve.json
```

Expected signature:

```text
PBL4 DEMO TCP SYN port scan
```

Rust stores it in PostgreSQL.

## 8. Demo C — Manual BLOCK from dashboard/API

Make sure Kali is `192.168.10.10` before using this demo.

From the Security VM or host management path:

```bash
curl -X POST http://127.0.0.1:3000/api/blocked-ips \
  -H 'Content-Type: application/json' \
  -d '{"ip":"192.168.10.10","reason":"manual PBL4 demo block"}'
```

Check:

```bash
sudo nft list set inet pbl4_demo blocked_ips
curl http://127.0.0.1:3000/api/blocked-ips
```

Then from Kali:

```bash
curl http://192.168.10.1/
```

The request should be dropped.

Unblock:

```bash
curl -X DELETE http://127.0.0.1:3000/api/blocked-ips/192.168.10.10
```

Then test again from Kali:

```bash
curl http://192.168.10.1/
```

The web request should work again.

## 9. Demo D — Auto-block

Only after manual block/unblock works:

Edit `.env`:

```env
AUTO_BLOCK=true
```

Restart Rust:

```bash
cargo run
```

Trigger the SQLi demo again:

```bash
curl 'http://192.168.10.1/login?user=%27%20OR%201%3D1'
```

The flow becomes:

```text
Kali
  ↓
Nginx access.log
  ↓
Rust SQLi detector
  ↓
security_alerts
  ↓
Policy: severity <= 2 + AUTO_BLOCK
  ↓
Rust Response Engine
  ↓
sudo /usr/local/bin/pbl4-firewall block 192.168.10.10
  ↓
nftables set blocked_ips
  ↓
DROP
```

For the Suricata rule the flow is analogous:

```text
Kali nmap
  ↓
Suricata
  ↓
eve.json
  ↓
Rust parser
  ↓
security_alerts
  ↓
auto-block (when enabled)
```

## 10. Audit log

```bash
docker exec -it pbl4-postgres psql -U pbl4 -d pbl4_security -c \
"SELECT id,ip,action,source,reason,status,created_at FROM firewall_actions ORDER BY id DESC LIMIT 20;"
```

## Safety / architecture notes

- The demo only allows blocking `192.168.10.2-192.168.10.254` to avoid accidentally blocking management or unrelated addresses.
- `AUTO_BLOCK=false` is the default.
- Before changing firewall rules, keep the SSH management NIC `192.168.122.x` available.
- Always test BLOCK/UNBLOCK from the management connection or VM console, not from the IP you are about to block.
- The demo uses simple regex/pattern matching for SQLi; it is a learning MVP, not a production WAF.

## 11. Optional systemd service

After `cargo build` succeeds:

```bash
sudo cp deploy/pbl4-security.service /etc/systemd/system/pbl4-security.service
sudo systemctl daemon-reload
sudo systemctl enable --now pbl4-security
sudo systemctl status pbl4-security --no-pager
```

Logs:

```bash
journalctl -u pbl4-security -f
```
