"""One authenticated GET. Never persist the cookie, response body or session HMAC."""
import getpass
import hashlib
import hmac
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import time

from urllib.parse import urlsplit
print("Origin của request /api/auth/me trong Network (ví dụ https://student.lab): ",end="",file=sys.stderr,flush=True)
origin=urlsplit(sys.stdin.readline().strip())
if origin.scheme!="https" or origin.hostname not in ("student.lab","192.168.20.10"):
    sys.exit("BLOCKED COOKIE_ORIGIN: đăng nhập qua HTTPS Student VM; localhost có cookie jar riêng. Dùng cookie của request backend, không dùng cookie của trang frontend.")
sid=getpass.getpass("JSESSIONID của một phiên STUDENT/STAFF lab đã đăng nhập trên VM (ẩn): ")
if not re.fullmatch("[a-fA-F0-9]{32}",sid):
    sys.exit("BLOCKED: expected a Tomcat lab session")
ctx=ssl.create_default_context(cafile="/etc/ws-native/edge.crt")
c=http.client.HTTPSConnection("127.0.0.1",24443,context=ctx,timeout=6)
c.request("GET","/api/auth/me",headers={"Host":"student.lab","Cookie":"JSESSIONID="+sid,"Accept":"application/json"})
r=c.getresponse()
rid=r.getheader("X-Request-Id","")
if r.status==401:
    sys.exit("BLOCKED SESSION_UNAUTHENTICATED: VM từ chối cookie (hết hạn, cookie trước login rotation hoặc sai backend).")
if r.status!=200 or not re.fullmatch("[a-f0-9]{32}",rid):
    sys.exit(f"BLOCKED: authenticated Edge canary HTTP {r.status} or missing request ID")
if sys.argv[1:] == ["full"] and r.getheader("X-WebSentinel-Lab-Leases") != "native-v1":
    sys.exit("BLOCKED VM_LEASES: VM backend must load native lease mode and permit this authenticated lab user")
body=r.read(8193)
c.close()
try:
    me=json.loads(body) if len(body)<=8192 else None
except ValueError:
    me=None
if not isinstance(me,dict) or me.get("enabled") is not True or me.get("role") not in ("STAFF","STUDENT") or type(me.get("id")) is not int or me["id"]<=0 or not me.get("username"):
    sys.exit("BLOCKED VM_PRINCIPAL: /api/auth/me phải trả UserSummary của STUDENT/STAFF đang hoạt động")
del body
key=Path("/etc/ws-native/session.key").read_bytes().rstrip(b"\n")
expected="hmac-sha256:"+hmac.digest(key,("session:"+sid).encode(),"sha256").hex()
del key,sid
sql=f"""
SELECT json_build_object(
 'nginx',EXISTS(SELECT FROM normalized_events WHERE source='NGINX' AND request_id='{rid}'),
 'sensor',EXISTS(SELECT FROM suricata_lua_shadow WHERE request_id='{rid}' AND proof_present AND receipt_present AND NOT mismatched),
 'r37',EXISTS(SELECT FROM https_research_observations WHERE request_id='{rid}' AND NOT conflicted AND observation->>'status'='SCORED' AND observation->>'version'='r37-hgb-uri100-v1'),
 'decision',EXISTS(SELECT FROM hybrid_incidents WHERE request_id='{rid}' AND decision#>>'{{dev_prevention,request_id}}'='{rid}'),
 'audit',(SELECT json_agg(json_build_array(source_instance,canonical->>'session_hmac',canonical->>'role',canonical->>'user_id',canonical->>'uri_path',status_code,canonical->>'http_method'))
 FROM normalized_events WHERE source='STUDENT_AUDIT' AND request_id='{rid}'))"""
for i in range(30):
    data=json.loads(subprocess.check_output(["docker","exec","-e","PGOPTIONS=-cdefault_transaction_read_only=on","pbl4-postgres","psql","-XAt","-v","ON_ERROR_STOP=1","-U","pbl4","-d","ws_native_security","-c",sql],text=True))
    rows=data.pop("audit") or []
    if not rows:
        reason="AUDIT_MISSING: không thấy Student Audit cùng Request ID; kiểm tra exporter/RELP của VM và receiver, không đổi cookie để xử lý lỗi này"
    elif len(rows)!=1:
        reason="AUDIT_AMBIGUOUS: nhiều sự kiện cùng Request ID"
    else:
        instance,session,role,actor,path,status,method=rows[0]
        if (path,status,method)!=("/api/auth/me",200,"GET") or role!=me["role"]:
            sys.exit("BLOCKED AUDIT_CONTEXT: method/path/status/role khác phản hồi VM")
        if not re.fullmatch("hmac-sha256:[a-f0-9]{64}",actor or ""):
            sys.exit("BLOCKED AUDIT_USER: thiếu pseudonym của user đã đăng nhập")
        if not session or not hmac.compare_digest(expected,session):
            sys.exit("BLOCKED SESSION_BINDING: session_hmac của VM khác Gate. Hai bên phải dùng cùng khóa riêng app.native.session-key; không thay khóa Gate bằng audit master key.")
        if not re.fullmatch("[a-zA-Z0-9_.:-]{1,128}",instance or ""):
            sys.exit("BLOCKED AUDIT_SOURCE: invalid source instance")
        if all(data.values()):
            # Verify the VM-generated principal pseudonym independently of session identity.
            audit_key=getpass.getpass("Khóa HMAC Student Audit của VM để kiểm tra user_id (ẩn, chỉ trong bộ nhớ): ").encode()
            match="hmac-sha256:"+hmac.digest(audit_key,("user_id:"+str(me["id"])).encode(),"sha256").hex()
            if len(audit_key)<32 or not hmac.compare_digest(actor,match):
                sys.exit("BLOCKED USER_BINDING: pseudonym user_id không khớp principal của VM")
            print(json.dumps(dict(instance=instance,actor=actor[12:])) if sys.argv[1:] == ["full"] else instance)
            print("PASS VM principal/session/audit request",rid,file=sys.stderr)
            break
        reason="DETECTOR_PENDING"
    time.sleep(1)
else:
    sys.exit(f"BLOCKED request={rid} {reason} detectors={data}")
