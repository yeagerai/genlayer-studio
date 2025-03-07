from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import time


class MockWebServer(BaseHTTPRequestHandler):
    def do_GET(self):
        # Return the same response regardless of the path
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


def run_server():
    server = HTTPServer(("0.0.0.0", 8000), MockWebServer)
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
