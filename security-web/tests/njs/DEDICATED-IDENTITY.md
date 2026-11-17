# Dedicated NGINX worker identity (optional, not deployed)

Use one NGINX master and the existing two server blocks. The master remains root
for startup; workers use an EXCLUSIVE non-login `websentinel-edge` UID and group.
No shell, cron, application, simulator or other service may execute as this user.
Do not reuse www-data or nobody. Do not grant sudo, capabilities, supplementary
groups, writable NGINX/njs configuration or writable module directories to it.
The account and numeric IDs must be checked against actual host allocations.
`prepare-proof-identity.py` renders the main-context user directive only; it never
creates accounts or writes runtime configuration.

Root owns the configuration, njs module and key parent directory. The intended
production key layout is root:websentinel-edge, directory 0750, file 0640,
read-only to workers. Rotation is performed by the trusted root lifecycle owner,
using atomic replacement, fresh epoch and key before any new worker accepts
traffic. Reload retains epoch only while the existing shared nonce dictionary
survives. Crash/restart must not reuse an epoch with lost replay state.

The njs test loader now supports an opt-in `probe_key_gid` variable: it requires
a root-owned regular 0640 key and root-owned 0750 parent directory with that exact
nonzero GID; key symlinks are rejected. Leave the variable empty for existing
0600 fixtures. The managed-group path still needs privileged runtime acceptance,
including supplementary-group isolation and ancestor directory ownership. This
is a deployment gate, not permission to install the fragment in production.

Changing the global NGINX user also affects every server block on that instance:
audit TLS certificate access, log/temp directories, AI Unix socket group ACL and
existing sites before applying. Do not broadly chmod directories or add unrelated
groups just to get NGINX running. No production apply script is supplied yet.

Trust boundary: protects against other unprivileged UIDs when kernel permissions
and service isolation are enforced. An attacker executing as the worker UID,
NGINX/njs compromise, root, CAP_DAC_OVERRIDE, ptrace-capable administration or a
compromised verification process holding symmetric HMAC keys is INSIDE the trust
boundary and can forge proofs. UID+cgroup socket rules do not fix key exposure
within that boundary. Same-UID confidentiality is not claimed.

Timing remains unaccepted: randomized double-HMAC comparison has functional tests,
not a proof of constant-time execution. Do not infer timing safety from latency
averages or successful MAC rejection tests.
