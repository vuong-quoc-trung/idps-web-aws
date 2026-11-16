#!/usr/bin/env python3
"""Render Host -> VM config only. Never install files or reload services."""
import argparse
import importlib.util
import ipaddress
import re
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def address(value):
    ip = ipaddress.IPv4Address(value)
    if ip.is_unspecified or ip.is_multicast:
        raise ValueError("Use a specific unicast IPv4 address")
    return str(ip)


def certificate_path(value):
    # Paths are embedded in NGINX directives; reject whitespace and metacharacters.
    if not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(value)):
        raise ValueError("TLS paths must be absolute paths without spaces or NGINX metacharacters")
    return str(value)


def existing_tls(text):
    active = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
    certs = re.findall(r"^\s*ssl_certificate\s+([^;]+);", active, re.M)
    keys = re.findall(r"^\s*ssl_certificate_key\s+([^;]+);", active, re.M)
    if not certs and not keys and not re.search(r"\bssl\b|:443\b", active):
        return None, None
    if ("# PBL4 HTTPS BEGIN" not in text or len(certs) != 1 or len(keys) != 1):
        raise ValueError("Unmanaged HTTPS found; refusing to silently replace it. Review manually.")
    return certificate_path(certs[0]), certificate_path(keys[0])


def egress_options(ca, name, port=443):
    ca = certificate_path(ca)
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", name):
        raise ValueError("Upstream TLS name must be a DNS name")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("Invalid upstream TLS port")
    return dict(ca=ca, name=name, port=port)


def existing_egress(text):
    markers = re.findall(r"^# PBL4 EGRESS OPTIONS (.+)$", text, re.M)
    if not markers:
        if 'PBL4 TLS EGRESS' in text:
            raise ValueError("Missing managed egress metadata")
        return None
    if len(markers) != 1:
        raise ValueError("Ambiguous egress metadata")
    return egress_options(**json.loads(markers[0]))


def add_egress_arguments(parser):
    parser.add_argument('--egress-ca', help='Enable local TLS egress with this CA file')
    parser.add_argument('--egress-name', help='Verified upstream certificate DNS name')
    parser.add_argument('--egress-port', type=int, default=None)
    parser.add_argument('--disable-egress', action='store_true')


def select_egress(args, current=''):
    supplied = any(v is not None for v in (args.egress_ca, args.egress_name, args.egress_port))
    if args.disable_egress:
        if supplied:
            raise ValueError('Cannot disable egress and supply egress options')
        return None
    if supplied:
        if not args.egress_ca or not args.egress_name:
            raise ValueError('--egress-ca and --egress-name are required together')
        return egress_options(args.egress_ca, args.egress_name,
                              args.egress_port if args.egress_port is not None else 443)
    return existing_egress(current)


def render(host="192.168.10.1", upstream="192.168.20.10", lan=None,
           tls_cert=None, tls_key=None, egress=None):
    host, upstream = address(host), address(upstream)
    lan = address(lan) if lan else None
    site = (ROOT / "nginx/pbl4-proxy.conf").read_text()
    site = site.replace("listen 192.168.10.1:80;", f"listen {host}:80;")
    site = site.replace("# OPTIONAL_LAN_LISTENER",
                        f"listen {lan}:80;" if lan and lan != host else "# No additional LAN listener")
    site = site.replace("http://192.168.20.10:80;", f"http://{upstream}:80;")
    if bool(tls_cert) != bool(tls_key):
        raise ValueError("Both --tls-cert and --tls-key are required")
    tls = "# HTTPS disabled (HTTP retained)"
    if tls_cert:
        cert, key = certificate_path(tls_cert), certificate_path(tls_key)
        listeners = [host] + ([lan] if lan and lan != host else [])
        tls = "# PBL4 HTTPS BEGIN\n    " + "\n    ".join(
            f"listen {ip}:443 ssl;" for ip in listeners)
        tls += (f"\n    ssl_certificate {cert};\n    ssl_certificate_key {key};"
                "\n    ssl_protocols TLSv1.2 TLSv1.3;"
                "\n    ssl_session_tickets off;\n    # PBL4 HTTPS END")
    site = site.replace("# OPTIONAL_HTTPS", tls)
    if egress is not None:
        egress = egress_options(**egress)
        if not tls_cert:
            raise ValueError('TLS egress requires Edge HTTPS; disable egress first for HTTP-only rollback')
        site = site.replace(f'proxy_pass http://{upstream}:80;',
                            'proxy_bind 127.77.0.1;\n        proxy_pass http://127.77.0.2:18080;')
        template = (ROOT / 'nginx/pbl4-egress.conf.template').read_text()
        for token, value in {'UPSTREAM': upstream, 'PORT': egress['port'],
                             'NAME': egress['name'], 'CA': egress['ca']}.items():
            template = template.replace('@' + token + '@', str(value))
        site += '\n# PBL4 EGRESS OPTIONS ' + json.dumps(egress, sort_keys=True) + '\n' + template
    formats = ((ROOT / "nginx/pbl4-access.conf").read_text() + "\n"
               + (ROOT / "deploy/ai-shadow/telemetry.conf").read_text()
               + "\n" + (ROOT / "nginx/pbl4-edge-limits.conf").read_text())
    return site, formats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-ip", default="192.168.10.1")
    parser.add_argument("--upstream-ip", default="192.168.20.10")
    parser.add_argument("--lan-ip", help="Optional existing LAN IPv4 on Defender")
    add_egress_arguments(parser)
    parser.add_argument("--tls-cert")
    parser.add_argument("--tls-key")
    parser.add_argument("--output", type=Path, required=True, help="New/reusable staging directory, NOT /etc")
    parser.add_argument("--check-system", action="store_true",
                        help="Validate candidate with other installed includes (sudo may be needed); no reload")
    args = parser.parse_args()
    output = args.output.resolve()
    if output == Path("/etc") or Path("/etc") in output.parents:
        parser.error("Output must be a staging directory outside /etc")
    site, formats = render(args.host_ip, args.upstream_ip, args.lan_ip, args.tls_cert, args.tls_key, select_egress(args))
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
