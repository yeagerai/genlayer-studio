from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import time
import sys


class MockWebServer(BaseHTTPRequestHandler):
    def do_GET(self):
        print(f"[DEBUG] MockWebServer received request for path: {self.path}")
        print(f"[DEBUG] Client address: {self.client_address}")
        print(f"[DEBUG] Headers: {self.headers}")

        mock_response = """
        <html>
            <body>
                <div>
                    Georgia 2 - 0 Portugal
                </div>
            </body>
        </html>
        """
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(mock_response.encode())
        print("[DEBUG] MockWebServer sent response")


def run_server():
    server = HTTPServer(("0.0.0.0", 8000), MockWebServer)
    print(f"[DEBUG] Starting mock server on 0.0.0.0:8000")
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    return server


if __name__ == "__main__":
    server = run_server()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()
