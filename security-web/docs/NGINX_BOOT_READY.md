# Nginx boot recovery on the Security host

Install from `security-web`:

```bash
sudo bash scripts/install-nginx-ready.sh
```

The installer backs up existing target files and records enablement in a unique
`/var/backups/pbl4-nginx-ready.*` directory, installs root-owned copies, verifies the
unit, reloads systemd, enables and starts the oneshot. It never modifies nginx.conf,
VMware networking, nftables or any other PBL4 service. Keep the printed backup path.

`pbl4-nginx-ready.service` Wants/After network-online.target and is ordered After
nginx.service. It deliberately recovers a failed initial Nginx boot attempt without
adding a reverse dependency to nginx.service (which could deadlock its start job).
Do not add Before=nginx.service to this helper service.

The bounded wait checks exact IPv4 CIDRs using `ip -4 -o addr`: vmnet2 must have
192.168.10.1/24 and vmnet3 must have 192.168.20.1/24. It does not require operstate UP
(VMware host interfaces may report UNKNOWN), probe Web VM, or alter networking.
Wait limit: 90 seconds; config check: 15 seconds; start command: 25 seconds;
outer systemd TimeoutStartSec: 140 seconds. No timer or automatic restart loop.
On readiness, nginx -t must pass. If Nginx is active, do nothing; otherwise clear
its failed/start-limit status and start it once. Timeout/config/start errors fail
the oneshot and are visible in journal. RemainAfterExit=yes records successful
completion; this is not ongoing health monitoring. If interfaces appear after the
90-second deadline, manually restart only pbl4-nginx-ready.service.

## Verify now and again after a manual reboot

```bash
systemctl status pbl4-nginx-ready.service --no-pager -l
systemctl is-enabled pbl4-nginx-ready.service
systemctl is-active nginx
ip -br addr show vmnet2
ip -br addr show vmnet3
sudo ss -ltnp 'sport = :80'
curl --noproxy '*' --connect-timeout 3 --max-time 10 -I http://192.168.10.1/
journalctl -u pbl4-nginx-ready.service -b --no-pager
```

Expected: oneshot active/exited, enabled; Nginx active; correct two CIDRs;
192.168.10.1:80 LISTEN. HTTP 502 while Web VM is off is acceptable for boot recovery.
When Web VM starts, requests should succeed without restarting Nginx.
No reboot or removal of interfaces is performed by the installer/test procedure.

## Rollback (first installation)

```bash
sudo systemctl disable --now pbl4-nginx-ready.service
sudo rm -- /etc/systemd/system/pbl4-nginx-ready.service /usr/local/libexec/pbl4-wait-nginx
sudo systemctl daemon-reload
sudo systemctl reset-failed pbl4-nginx-ready.service
```

If reset-failed reports the removed unit is not loaded, no further action is needed.
Nginx remains running: there is no ExecStop or PartOf relationship to stop it.
For a replacement installation, restore the two files from the printed backup
instead of deleting them; daemon-reload and restore previous enablement recorded
in previous-enabled-state.txt. Never remove nginx.service or other PBL4 units.
