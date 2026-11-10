#!/usr/bin/env python3
"""Render Host -> VM config only. Never install files or reload services."""
import argparse
import importlib.util
import ipaddress
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def address(value):
    ip = ipaddress.IPv4Address(value)
    if ip.is_unspecified or ip.is_multicast:
        raise ValueError("Use a specific unicast IPv4 address")
    return str(ip)


def render(host="192.168.10.1", upstream="192.168.20.10", lan=None):
    host, upstream = address(host), address(upstream)
    lan = address(lan) if lan else None
    site = (ROOT / "nginx/pbl4-proxy.conf").read_text()
    site = site.replace("listen 192.168.10.1:80;", f"listen {host}:80;")
    site = site.replace("# OPTIONAL_LAN_LISTENER",
                        f"listen {lan}:80;" if lan and lan != host else "# No additional LAN listener")
    site = site.replace("http://192.168.20.10:80;", f"http://{upstream}:80;")
    formats = ((ROOT / "nginx/pbl4-access.conf").read_text() + "\n"
               + (ROOT / "deploy/ai-shadow/telemetry.conf").read_text())
    return site, formats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-ip", default="192.168.10.1")
    parser.add_argument("--upstream-ip", default="192.168.20.10")
    parser.add_argument("--lan-ip", help="Optional existing LAN IPv4 on Defender")
    parser.add_argument("--output", type=Path, required=True, help="New/reusable staging directory, NOT /etc")
    parser.add_argument("--check-system", action="store_true",
                        help="Validate candidate with other installed includes (sudo may be needed); no reload")
    args = parser.parse_args()
    output = args.output.resolve()
    if output == Path("/etc") or Path("/etc") in output.parents:
        parser.error("Output must be a staging directory outside /etc")
    site, formats = render(args.host_ip, args.upstream_ip, args.lan_ip)
    output.mkdir(parents=True, exist_ok=True)
    for name, content in [("pbl4-proxy", site), ("pbl4-ai-shadow.conf", formats)]:
        target = output / name
        if target.is_symlink():
            parser.error("Refusing symlink output")
        target.write_text(content)
    if args.check_system:
        spec = importlib.util.spec_from_file_location("installer", Path(__file__).with_name("install-ai-shadow-host.py"))
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        installer.syntax(Path("/etc/nginx/sites-available/pbl4-proxy").resolve(), site, formats)
    print(f"Prepared {output}. No host config or service changed. Review both files before installation.")


if __name__ == "__main__":
    main()
