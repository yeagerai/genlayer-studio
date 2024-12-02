import unittest
from flask import Flask
from backend.protocol_rpc.server import create_app

class TestServerStartup(unittest.TestCase):
    def setUp(self):
        # Set up the Flask test client
        self.app, _, _, _, _, _, _, _, _, _, _ = create_app()
        self.client = self.app.test_client()

    def test_server_starts(self):
        # Test if the server starts and responds to a simple request
        response = self.client.get('/api')
        self.assertEqual(response.status_code, 200)

    def test_gunicorn_configuration(self):
        """Test if Gunicorn is configured with the correct settings."""
        self.assertEqual(os.getenv('GUNICORN_WORKERS'), '4')
        self.assertEqual(os.getenv('GUNICORN_WORKER_CLASS'), 'gevent')

    def test_server_performance_under_load(self):
        """Simulate load to test server performance with Gunicorn."""
        with self.client:
            for _ in range(100):
                response = self.client.get('/api')
                self.assertEqual(response.status_code, 200)

    def test_jsonrpc_endpoint(self):
        # Test if the JSON-RPC endpoint is available
        response = self.client.post('/api', json={
            "jsonrpc": "2.0",
            "method": "llm_plugin_get",
            "params": {"plugin": "test_plugin", "plugin_config": {}},
            "id": 1
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('result', response.json)

if __name__ == '__main__':
    unittest.main()