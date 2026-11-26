"""Exercise the deployed dashboard against the disposable EC2 backend."""
import base64
import json
import os
import sys
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

root = Path(sys.argv[1])
driver = "http://127.0.0.1:20758"
host = "http://127.0.0.1:33056"
session = ""
handle = "element-6066-11e4-a52e-4f735466cecf"

def call(path, payload=None, method=None, root_path=False):
    url = driver + ("" if root_path else "/session/" + session) + path
    req = Request(url, data=None if payload is None else json.dumps(payload).encode(),
                  headers={"Content-Type":"application/json"}, method=method)
    try:
        with urlopen(req, timeout=12) as res:
            return json.load(res)["value"]
    except HTTPError as err:
        error = json.load(err)["value"]
        detail = error.get("message", "")[:240] if path == "/session" else ""
        raise RuntimeError(f"WebDriver {error.get('error')} on {path} {detail}".strip()) from None

def find(selector, using="css selector"):
    return call("/element", {"using":using, "value":selector})[handle]

def until(fn, label, seconds=15):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            if value := fn():
                return value
        except (RuntimeError, OSError):
            pass
        time.sleep(.15)
    raise AssertionError(label)

def button(text, root="//"):
    elem = until(lambda: find(root+"button[normalize-space(.)="+json.dumps(text,ensure_ascii=False)+"]","xpath"), text)
    call("/element/"+elem+"/click", {})

def fill(selector, value):
    elem = until(lambda: find(selector), selector)
    call("/element/"+elem+"/clear", {})
    call("/element/"+elem+"/value", {"text":value})

def body():
    return call("/element/"+find("#dashboard-content")+"/text")

def snapshot(name):
    call("/execute/sync", {"script":"""document.querySelector('.account-profile strong').textContent='Đã che tài khoản'; document.querySelector('.account-profile .avatar').textContent='•';""","args":[]})
    (root/name).write_bytes(base64.b64decode(call("/screenshot")))

def open_path(url):
    call("/url", {"url":url})

def block(reason, ttl):
    fill("input[placeholder='192.168.10.10']", "10.254.56.2")
    fill(".panel .filters input[maxlength='500']", reason)
    fill(".panel .filters input[type='number']", str(ttl))
    button("Gửi yêu cầu chặn")
    until(lambda: "đã được tiếp nhận" in body(), "Block API accepted")
    until(lambda: (button("Làm mới") or True) and "Hết hạn" in body(), "active lease shown")

def main():
    now = time.monotonic
    start = now()
    until(lambda: urlopen(host+"/health", timeout=2).status == 200,"lab backend health",35)
    open_path(host+"/")
    fill("input[name='username']", "admin")
    fill("input[name='password']", (root/"browser.password").read_text().strip())
    button("Đăng nhập")
    until(lambda: find("nav"),"authenticated")
    button("IP bị chặn", "//nav//")
    until(lambda: "đã sẵn sàng" in body(), "live Prevention readiness")
    block("R58 browser block", 75)
    seen = now()
    print("R58_UI_BLOCKED", flush=True)
    assert "Có trong cả DB và kernel" in body()
    snapshot("firewall-active.png")
    time.sleep(1)
    button("Bỏ chặn")
    call("/alert/accept", {})
    until(lambda: "đã được tiếp nhận" in body(),"Unblock API accepted")
    until(lambda: (button("Làm mới") or True) and "Chưa có IP bị chặn" in body(),"lease removed")
    print("R58_UI_UNBLOCKED", flush=True)
    time.sleep(max(0, 32 - (now() - seen)))
    block("R58 browser TTL", 9)
    print("R58_UI_TTL_ACTIVE", flush=True)
    until(lambda: (button("Làm mới") or True) and "Chưa có IP bị chặn" in body(),"TTL removal",17)
    button("Nhật ký thao tác", "//nav//")
    until(lambda: "R58 browser block" in body() and "R58 browser TTL" in body(), "operation history")
    snapshot("firewall-history.png")
    print("R58_BROWSER=PASS authenticated UI Block/Unblock/TTL/history", round(now()-start,2), flush=True)

try:
    session = call("/session", {"capabilities":{"alwaysMatch":{"browserName":"firefox",
        "moz:firefoxOptions":{"binary":os.environ["R58_FIREFOX"],"args":["-headless", "-profile", os.environ["R58_PROFILE"]],"prefs":{"signon.rememberSignons":False}}}}},
        root_path=True)["sessionId"]
    call("/window/rect", {"width":1280,"height":1050})
    main()
finally:
    if session:
        call("",method="DELETE")
