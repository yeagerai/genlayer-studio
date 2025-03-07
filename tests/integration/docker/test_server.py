from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from tests.integration.conftest import parse_bool_env_var


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
    if parse_bool_env_var("TEST_CI", "false"):
        port = 8000  # CI does not have permissions to use 80
    else:
        port = 80  # to run locally, no reverse proxy needed
    server = HTTPServer(("0.0.0.0", port), MockWebServer)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    return server, server_thread


def stop_server(server: HTTPServer | None, server_thread: threading.Thread | None):
    if server:
        server.shutdown()
        server.server_close()
    if server_thread:
        server_thread.join()


if __name__ == "__main__":
    server, server_thread = run_server()
