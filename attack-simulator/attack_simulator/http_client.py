"""No proxies, redirects, raw packets or environment credentials. DNS is pinned."""
import http.client
import ipaddress
import queue
import re
import socket
import ssl
import threading
from dataclasses import dataclass
from urllib.parse import urlsplit


class ValidationError(ValueError):
    pass


PRIVATE = tuple(ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '127.0.0.0/8', '::1/128', 'fc00::/7'))


def parse_origin(url):
    if not isinstance(url, str) or len(url) > 512 or any(ord(c) <= 32 for c in url):
        raise ValidationError('Target phải là HTTP(S) origin hợp lệ, không có khoảng trắng.')
    try:
        u = urlsplit(url)
        if u.scheme not in ('http', 'https') or not u.hostname or u.username is not None or u.password is not None or u.path not in ('', '/') or u.query or u.fragment:
            raise ValueError()
        host = u.hostname.encode('idna').decode('ascii')
        if '%' in host or '\\' in url or not re.fullmatch(r'[A-Za-z0-9.:-]+', host):
            raise ValueError()
        port = u.port if u.port is not None else (443 if u.scheme == 'https' else 80)
        if not 1 <= port <= 65535: raise ValueError()
        authority = f'[{host}]' if ':' in host else host
        return u.scheme, host.lower(), port, f'{u.scheme}://{authority.lower()}:{port}'
    except (ValueError, UnicodeError):
        raise ValidationError('Chỉ nhận origin, ví dụ http://host:80; không credentials/path/query.') from None


def resolve(host, port):
    # Bounded caller wait; a stalled OS resolver cannot block Stop indefinitely.
    out = queue.Queue(maxsize=1)
    def work():
        try:
            out.put(socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
        except OSError:
            out.put(None)
    threading.Thread(target=work, daemon=True).start()
    try:
        rows = out.get(timeout=3)
    except queue.Empty:
        raise ValidationError('DNS timeout.') from None
    if not rows:
        raise ValidationError('Không phân giải được target.')
    return sorted({r[4][0] for r in rows})


@dataclass(frozen=True)
class Target:
    scheme: str
    host: str
    port: int
    origin: str
    ip: str

    @classmethod
    def create(cls, url, allowlist=(), resolver=resolve):
        scheme, host, port, origin = parse_origin(url)
        allowed = origin in {parse_origin(v)[3] for v in allowlist}
        ips = resolver(host, port)
        if not ips:
            raise ValidationError('Target không có địa chỉ.')
        for value in ips:
            ip = ipaddress.ip_address(value)
            if ip.is_multicast or ip.is_unspecified or ip.is_link_local or ip.is_reserved and not ip.is_loopback:
                raise ValidationError('Không cho phép địa chỉ multicast/link-local/reserved.')
            if not allowed and not any(ip in n for n in PRIVATE if ip.version == n.version):
                raise ValidationError('Target ngoài mạng lab; cần origin allowlist cấu hình rõ ràng.')
        return cls(scheme, host, port, origin, ips[0])


class PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, target, timeout):
        super().__init__(target.host, target.port, timeout=timeout)
        self.target = target

    def connect(self):
        family = socket.AF_INET6 if ':' in self.target.ip else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        self.sock = sock
        sock.settimeout(self.timeout)
        sock.connect((self.target.ip, self.target.port))
        if self.target.scheme == 'https':
            self.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.target.host)


@dataclass
class Response:
    status: int
    headers: dict
    body: bytes
    truncated: bool = False


class Client:
    def __init__(self, target, timeout=5):
        self.target, self.timeout = target, timeout

    def request(self, method, path, headers=None, body=None, timeout=None):
        if not path.startswith('/') or path.startswith('//') or '\r' in path or '\n' in path or len(path) > 4096:
            raise ValidationError('Invalid request path.')
        conn = PinnedHTTP(self.target, min(self.timeout, timeout or self.timeout))
        def abort():
            if conn.sock:
                try:
                    conn.sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            conn.close()
        timer = threading.Timer(conn.timeout, abort)
        timer.daemon = True
        timer.start()
        try:
            conn.request(method, path, body=body, headers={'User-Agent': 'WebSentinel-Lab-Simulator/0.1', 'Connection': 'close', **(headers or {})})
            response = conn.getresponse()
            data = response.read(262145)
            # Never follow redirects, even same-origin; never retain response body in reports.
            return Response(response.status, {k.lower(): v for k, v in response.getheaders()}, data[:262144], len(data) > 262144)
        finally:
            timer.cancel()
            conn.close()
