# njs capability acceptance — 2026-11-17

Test-only GET proof format. NOT a production authenticator or Rust trust gate.
Reuses `test-nginx-egress.py` (Edge HTTPS, local HTTP Egress, verified TLS mock).
Runs one non-root NGINX master with four workers on temporary ports. No firewall,
production services, database or /etc modifications. No njs package was installed.

## Module

Ubuntu package `libnginx-mod-http-js` 0.9.4-1build2, njs 0.9.4, amd64.
Installed NGINX: 1.28.3-2ubuntu1.12. Package requires nginx-abi-1.28.3-1;
actual extracted module passed nginx -t and served test requests.
Package SHA256: d86baa0604905acc837b25ebefdbf9545e28cc3e6ceb5a6daa06e7e13e19b569.
`ldd` found all module shared libraries. Extraction is not package installation;
it does not assert dpkg dependencies have been installed or change production.

Reproduce without sudo (download/extract only):

```sh
mkdir -p /tmp/ws-njs-package
cd /tmp/ws-njs-package
apt-get download libnginx-mod-http-js=0.9.4-1build2
dpkg-deb -x libnginx-mod-http-js_0.9.4-1build2_amd64.deb extracted
# Return to the repository root:
python3 security-web/scripts/test-njs-proof.py --module /tmp/ws-njs-package/extracted/usr/lib/nginx/modules/ngx_http_js_module.so
```

## Measured results

22 assertions passed, including the explicitly insecure negative control:

- Python HMAC-SHA256 proof verified in njs; njs receipt matches Python HMAC.
- Edge signs actual request, Egress verifies and forwards to TLS mock (204).
- Missing proof, expired proof, invalid MAC: 403, no receipt, no upstream request.
- 64 concurrent attempts of one nonce: exactly one accepted; keep-alive replay denied.
- 64 distinct concurrent requests accepted; multiple worker PIDs observed.
- Proof/receipt absent from mock upstream; receipt hidden on Edge client response.
- Reload retains nonce rejection.
- Negative control: clean restart with same key/epoch accepts previously used proof.
  This is a demonstrated security failure of relying on volatile shared state alone.
- Clean restart AND master/workers SIGKILL recovery with key/epoch rotation reject
  old proofs and accept new proofs. Rotation is performed by the test launcher,
  not automatically provided by njs or a production supervisor.
- Missing key and mode 0644 fail closed; mode 0600 works.
- 64 KiB dictionary fills within 1500 bounded probes; failure stays closed, no eviction.
- Generated key strings absent from collected test logs and mock upstream headers.

## Scope and security limitations

Keys are random test material in a TemporaryDirectory (0700), atomic key files
0600, no key in command arguments, environment, Git or generated JS/config text.
Workers share the invoking user's UID. This does NOT protect against another
process with that same UID, ptrace access, compromised NGINX or root. A dedicated
production UID and reviewed key loading/process isolation are still required.
The test reads the key file on each request; that is functional verification,
not a recommended optimized production key lifecycle.

njs 0.9.4 module crypto has createHmac, but lacks Node's randomBytes and
 timingSafeEqual APIs. Fixture uses Web Crypto getRandomValues and randomized
HMAC comparison blinding. Functional tests are NOT timing-side-channel acceptance;
review this choice or test WebCrypto verification with a suitable asynchronous
NGINX auth hook before adopting production code. No plain stable MAC comparison.

Nonce dictionary has no `evict` or persistence file. Timeout is 65 seconds, proof
age at most 60 seconds with at most 1 second future skew. Do not claim arbitrary
clock-change safety, worker-crash recovery, persisted replay recovery, or rolling
mixed-epoch reload acceptance from these tests. Full process restart must rotate
before binding listeners; old proofs deliberately fail. Rust retaining historical
verification keys is a separate concern and is not implemented here.

This format binds method and request URI and carries request ID/client metadata,
but is GET-only and does not implement all production field-consistency checks,
request body binding, duplicate-header defense, or complete canonicalization.
Receipt means admission, not successful response delivery or completed body.
No Suricata integration, delayed EVE join, partial-response test, or Rust Verified.

No nftables policy was created for the test listeners, so application rejection
works without relying on the guard. This run did NOT delete a host firewall table
or retest a combined nft-deletion transition. No production deployment is authorized
by these results. Next scope requires separate approval.
