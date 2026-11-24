"""Read-only status operation; systemd supplies a connected AF_UNIX socket."""
import os
import pwd
import socket
import struct
import subprocess

with socket.socket(fileno=os.dup(0)) as peer:
    peer.settimeout(2)
    _, uid, _ = struct.unpack("3i", peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    if uid != pwd.getpwnam("ws-native-security").pw_uid:
        raise SystemExit(1)
    with peer.makefile("rb") as reader:
        if reader.readline(16) != b"STATUS\n":
            raise SystemExit(1)
    result = subprocess.run(["/usr/sbin/nft","-j","list","set","inet","ws_native_prevention","blocked_ips"],
                            capture_output=True, timeout=2, env={"LC_ALL":"C"})
    if result.returncode == 0:
        reply = result.stdout
    elif b"No such file or directory" in result.stderr:
        reply = b"UNINITIALIZED"
    else:
        reply = b"ACTUATOR_ERROR"
    peer.sendall(reply)
