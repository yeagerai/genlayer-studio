from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import time
import sys


class MockWebServer(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        """Override to ensure all logs are printed to stdout"""
        print("[DEBUG-MOCK-SERVER] %s - - %s" % (self.address_string(), format % args))

    def do_GET(self):
        print("[DEBUG-MOCK-SERVER] -------- New Request --------")
        print(f"[DEBUG-MOCK-SERVER] Path: {self.path}")
        print(f"[DEBUG-MOCK-SERVER] Client: {self.client_address}")
        print("[DEBUG-MOCK-SERVER] Headers:")
        for header, value in self.headers.items():
            print(f"[DEBUG-MOCK-SERVER]   {header}: {value}")

        # Return the same response regardless of the path
        mock_response = """
        <html>
            <body>
                <div class="match-summary">
                    <h2>Match Summary</h2>
                    <div class="score">
                        Georgia 2 - 0 Portugal
                    </div>
                    <div class="status">
                        Full Time
                    </div>
                </div>
            </body>
        </html>
        """
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.send_header("Content-Length", str(len(mock_response.encode())))
        self.end_headers()
        self.wfile.write(mock_response.encode())
        print("[DEBUG-MOCK-SERVER] Response sent successfully")
        print("[DEBUG-MOCK-SERVER] -----------------------------")


def run_server():
    server = HTTPServer(("0.0.0.0", 8000), MockWebServer)
    print(f"[DEBUG-MOCK-SERVER] Starting mock server on 0.0.0.0:8000")
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
