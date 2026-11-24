"""Transform the accepted native candidate, preserving the Edge protection and HMAC blocks."""
def nginx(text):
    if "proxy_pass https://192.168.20.10:443;" in text and "127.78.0.3:28443" not in text:
        return text
    start = text.index("    server {\n        listen 127.78.0.3:28443 ssl;")
    end = text.index("    server {\n        listen 127.0.0.1:29443 ssl;",start)
    origin = text[start:end]
    if origin.count("server {") != 1 or "proxy_pass http://127.0.0.1:28081;" not in origin:
        raise ValueError("Unrecognized local Student origin")
    text = text[:start]+text[end:]
    for old,new in (("proxy_pass https://127.78.0.3:28443;", "proxy_pass https://192.168.20.10:443;"),
                    ("proxy_ssl_name student.internal;", "proxy_ssl_name student.lab;"),
                    ("proxy_ssl_trusted_certificate /etc/ws-native/origin.crt;", "proxy_ssl_trusted_certificate /etc/ws-native/student-ca.crt;"),
                    ("error_log stderr crit;", "error_log /var/lib/ws-native/edge/error.log crit;")):
        if text.count(old)!=1:
            raise ValueError("Unexpected native nginx configuration: "+old)
        text=text.replace(old,new)
    return text.replace("error_log /dev/null crit;", "error_log /var/lib/ws-native/edge/error.log crit;")
