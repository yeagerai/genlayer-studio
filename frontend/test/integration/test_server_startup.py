import subprocess
import time
import requests

def start_containers():
    """Start the Docker containers using docker-compose."""
    subprocess.run(["docker-compose", "up", "-d"], check=True)

def stop_containers():
    """Stop the Docker containers using docker-compose."""
    subprocess.run(["docker-compose", "down"], check=True)

def wait_for_service(url, timeout=60):
    """Wait for a service to become available."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url)
            if response.status_code == 200:
                return True
        except requests.ConnectionError:
            pass
        time.sleep(1)
    return False

def test_backend_service():
    """Test if the backend service is running and accessible."""
    backend_url = f"http://localhost:{os.environ.get('RPCPORT')}/api"
    assert wait_for_service(backend_url), "Backend service is not available."

def test_webrequest_service():
    """Test if the webrequest service is running and accessible."""
    webrequest_url = f"http://localhost:{os.environ.get('WEBREQUESTPORT')}/api"
    assert wait_for_service(webrequest_url), "Webrequest service is not available."

def test_gunicorn_deployment():
    """Verify that Gunicorn is serving the application correctly."""
    backend_url = f"http://localhost:{os.environ.get('RPCPORT')}/api"
    response = requests.get(backend_url)
    assert response.status_code == 200
    assert 'result' in response.json()

def test_gunicorn_workers():
    """Ensure Gunicorn is running with the specified number of workers."""
    workers = os.getenv('GUNICORN_WORKERS')
    assert workers == '4'

if __name__ == "__main__":
    try:
        start_containers()
        test_backend_service()
        test_webrequest_service()
        test_gunicorn_deployment()
        test_gunicorn_workers()
        print("All services are running and accessible.")
    finally:
        stop_containers()