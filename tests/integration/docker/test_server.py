from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import os
import time
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class MockWebServer(BaseHTTPRequestHandler):
    def do_GET(self):
        logger.info(f"Received GET request for path: {self.path}")
        logger.debug(f"Headers: {self.headers}")

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
        try:
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(mock_response.encode())
            logger.info("Response sent successfully")
        except Exception as e:
            logger.error(f"Error sending response: {e}")
            raise


def parse_bool_env_var(env_var: str, default: str) -> bool:
    env_var = os.getenv(env_var, default)
    if env_var == "true":
        return True
    elif env_var == "false":
        return False
    else:
        raise ValueError(f"{env_var} must be true or false")


def run_server():
    if parse_bool_env_var("TEST_CI", "false"):
        port = 8000  # CI does not have permissions to use 80
    else:
        port = 80  # to run locally, no reverse proxy needed

    logger.info(f"Starting server on port {port}")
    try:
        server = HTTPServer(("0.0.0.0", port), MockWebServer)
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        logger.info("Server started successfully")
        return server, server_thread
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        raise


def stop_server(server: HTTPServer | None, server_thread: threading.Thread | None):
    if server:
        logger.info("Shutting down server")
        try:
            server.shutdown()
            server.server_close()
            logger.info("Server shutdown complete")
        except Exception as e:
            logger.error(f"Error during server shutdown: {e}")
    if server_thread:
        try:
            server_thread.join()
            logger.info("Server thread joined")
        except Exception as e:
            logger.error(f"Error joining server thread: {e}")


if __name__ == "__main__":
    load_dotenv()
    logger.info("Starting mock web server")
    server, server_thread = run_server()
    try:
        while True:  # keep server running until test is finished
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        stop_server(server, server_thread)
        logger.info("Server stopped")
