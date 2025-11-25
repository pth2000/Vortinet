from http.server import HTTPServer, BaseHTTPRequestHandler
import sys

class Simple(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Hello from Vortinet Custom Service!")
        print(f"Handled request from {self.client_address}")

print("Starting server on port 8000...")
sys.stdout.flush()
httpd = HTTPServer(('0.0.0.0', 8000), Simple)
httpd.serve_forever()
