"""Validate mutual TLS and transaction-specific RELP acknowledgements."""
import re
import socket
import ssl
import sys
from pathlib import Path


def frame(number, command, payload):
    return b"%d %s %d " % (number, command, len(payload)) + payload + b"\n"


def acknowledged(reader, number):
    # RELP open replies can contain embedded newlines. Consume one whole frame
    # before examining the next transaction on this connection.
    header = bytearray()
    while header.count(b" ") < 3 and len(header) < 64:
        char = reader.read(1)
        if not char:
            return False
        header.extend(char)
    parts = bytes(header).split(b" ")
    if len(parts) != 4 or parts[:2] != [str(number).encode(), b"rsp"]:
        return False
    if not parts[2].isdigit() or not 0 < int(parts[2]) <= 65536:
        return False
    length = int(parts[2])
    body = reader.read(length)
    return (len(body) == length and reader.read(1) == b"\n"
            and body.split(b"\n", 1)[0] == b"200 OK")


def main():
    tls = Path(sys.argv[1])
    port = int(sys.argv[2])
    event = sys.argv[3] if len(sys.argv) > 3 else ""
    if event and (port != 32514 or not re.fullmatch(r"[a-f0-9]{32}", event)):
        sys.exit("Invalid canary event or port")
    host = "127.0.0.1" if port == 32514 else "192.168.20.1"
    offer = b"relp_version=0\nrelp_software=WebSentinel probe\ncommands=syslog"
    for case in ("authorized", "no-cert", "wrong-name", "TLS1.2", "plaintext"):
        ctx = ssl.create_default_context(cafile=str(tls / "ca.crt"))
        ctx.minimum_version = ctx.maximum_version = (
            ssl.TLSVersion.TLSv1_2 if case == "TLS1.2" else ssl.TLSVersion.TLSv1_3)
        if case not in ("no-cert", "plaintext"):
            cert = "wrong-name.crt" if case == "wrong-name" else "sender.crt"
            ctx.load_cert_chain(tls / cert, tls / "sender.key")
        with socket.create_connection((host, port), timeout=5) as raw:
            try:
                with (raw if case == "plaintext" else
                      ctx.wrap_socket(raw, server_hostname="audit-receiver.lab")) as stream:
                    # The TLS listener may wait for a complete record before rejecting plaintext.
                    stream.sendall(frame(1, b"open", offer))
                    if case == "plaintext":
                        stream.shutdown(socket.SHUT_WR)
                    with stream.makefile("rb") as reader:
                        ack = acknowledged(reader, 1)
                        if case == "authorized" and ack and event:
                            payload = ('{"schema_version":"1.0","source":"STUDENT_AUDIT",'
                                       '"event_id":"%s"}' % event).encode()
                            stream.sendall(frame(2, b"syslog", payload))
                            ack = acknowledged(reader, 2)
            except (ssl.SSLError, ConnectionResetError, BrokenPipeError) as error:
                if case == "authorized":
                    sys.exit(f"FAIL authorized TLS/RELP at {host}:{port}: {error}")
                ack = False
        if ack != (case == "authorized"):
            sys.exit(f"FAIL {case}: unexpected RELP acknowledgement state")
        print("PASS", case)


if __name__ == "__main__":
    main()
