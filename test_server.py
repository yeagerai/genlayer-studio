from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import time
import sys


class MockWebServer(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        """Override to ensure all logs are printed to stdout"""
        print(
            "[DEBUG-MOCK-SERVER] %s - - %s" % (self.address_string(), format % args),
            flush=True,
        )

    def do_GET(self):
        print("[DEBUG-MOCK-SERVER] -------- New Request --------", flush=True)
        print(f"[DEBUG-MOCK-SERVER] Path: {self.path}", flush=True)
        print(f"[DEBUG-MOCK-SERVER] Client: {self.client_address}", flush=True)
        print("[DEBUG-MOCK-SERVER] Headers:", flush=True)
        for header, value in self.headers.items():
            print(f"[DEBUG-MOCK-SERVER]   {header}: {value}", flush=True)

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
        print("[DEBUG-MOCK-SERVER] Sending response...", flush=True)
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.send_header("Content-Length", str(len(mock_response.encode())))
        self.end_headers()
        self.wfile.write(mock_response.encode())
        print("[DEBUG-MOCK-SERVER] Response sent successfully", flush=True)
        print("[DEBUG-MOCK-SERVER] -----------------------------", flush=True)


def run_server():
    server = HTTPServer(("0.0.0.0", 8000), MockWebServer)
    print(f"[DEBUG-MOCK-SERVER] Starting mock server on 0.0.0.0:8000", flush=True)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    print(f"[DEBUG-MOCK-SERVER] Server thread started", flush=True)
    return server


if __name__ == "__main__":
    server = run_server()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[DEBUG-MOCK-SERVER] Shutting down server...", flush=True)
        server.shutdown()
        print("[DEBUG-MOCK-SERVER] Server shutdown complete", flush=True)
