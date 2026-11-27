"""Read-only health checks for the two deployed WebSentinel websites."""

from http.client import HTTPException
from ipaddress import ip_address
import json
import re
import ssl
from time import monotonic

from .http_client import PinnedHTTP, Target, ValidationError, resolve


PROBES = (
    ("Student Web", "student-dut.duckdns.org", "/api/auth/csrf"),
    ("Security Dashboard", "websentinal.duckdns.org", "/"),
)


def check():
    results = []
    for name, host, path in PROBES:
        started = monotonic()
        result = {"name": name, "url": f"https://{host}{path}", "status": None,
                  "tls_verified": False, "request_id": None}
        connection = None
        try:
            addresses = resolve(host, 443)
            if not all(ip_address(address).is_global for address in addresses):
                raise ValidationError("Expected public addresses")
            # Keep the verified hostname for TLS while dialing the DNS result.
            target = Target("https", host, 443, f"https://{host}:443", addresses[0])
            connection = PinnedHTTP(target, timeout=5)
            connection.request("GET", path, headers={"Connection": "close"})
            with connection.getresponse() as response:
                request_id = response.getheader("X-Request-Id") or ""
                result.update(status=response.status, tls_verified=True)
                if re.fullmatch(r"[0-9a-f]{32}", request_id):
                    result["request_id"] = request_id
        except ValidationError:
            result["error"] = "DNS không trả về địa chỉ công khai hợp lệ."
        except ssl.SSLError:
            result["error"] = "Không xác minh được kết nối TLS."
        except (TimeoutError, OSError, HTTPException):
            result["error"] = "Không nhận được phản hồi HTTPS."
        finally:
            if connection is not None:
                connection.close()
        result["elapsed_ms"] = round((monotonic() - started) * 1000, 1)
        result["pass"] = result["status"] == 200 and result["tls_verified"]
        results.append(result)
    return results


if __name__ == "__main__":
    results = check()
    print(json.dumps(results, ensure_ascii=False, indent=2))
    raise SystemExit(0 if all(row["pass"] for row in results) else 1)
