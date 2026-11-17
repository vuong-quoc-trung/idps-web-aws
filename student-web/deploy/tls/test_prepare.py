import unittest
import prepare

SITE = '''server {
 listen 80;
 server_name _;
 location / {
  proxy_pass http://127.0.0.1:5173;
  proxy_http_version 1.1;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "upgrade";
 }
 location /api/ {
  proxy_pass http://127.0.0.1:8080;
  proxy_set_header X-Request-Id $http_x_request_id;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
 }
}
'''
class PrepareTests(unittest.TestCase):
    def render(self, text):
        return prepare.render(text, '/etc/nginx/student-tls/student.crt', '/etc/nginx/student-tls/student.key', '192.168.20.10')
    def test_preserves_all_original_routes_and_headers(self):
        value = self.render(SITE)
        self.assertEqual(value[value.index(' listen 80;'):], SITE[SITE.index(' listen 80;'):])
        self.assertIn('listen 192.168.20.10:443 ssl;', value)
        self.assertIn('ssl_protocols TLSv1.2 TLSv1.3;', value)
        self.assertNotIn('return 301', value)
    def test_existing_tls_refused(self):
        with self.assertRaises(ValueError): self.render(self.render(SITE))
    def test_multiple_servers_refused(self):
        with self.assertRaises(ValueError): self.render(SITE+SITE)
    def test_includes_refused(self):
        with self.assertRaises(ValueError): self.render(SITE.replace('listen 80;', 'listen 80; include /tmp/unknown;'))
    def test_comment_braces_not_parsed(self):
        self.render('# server { }\n'+SITE)
    def test_path_injection_refused(self):
        with self.assertRaises(ValueError): prepare.render(SITE, '/tmp/x;bad', '/tmp/key', '192.168.20.10')
if __name__ == '__main__': unittest.main(verbosity=2)
