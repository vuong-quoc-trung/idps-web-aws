# Live capture fixture

Generated 2026-11-16 by test-local-egress-capture.py using Suricata8.0.3 AF_PACKET
inside a disposable user/network namespace. Real HTTP on127.77.0.1→127.77.0.2:18080;
Edge client TLS and TLS mock upstream. Four legitimate probes from namespace-only
192.0.2.10 and one source-bound forgery claiming192.0.2.99.

Only allowlisted attribution fields retained; raw URLs, body, credentials, keys
and packets are omitted. Missing app_proto in HTTP records is actual sensor output.
No database or production traffic used. Do not treat forged XFF as verified.
