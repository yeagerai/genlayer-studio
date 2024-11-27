import unittest
from flask import Flask
from webrequest.server import app

class TestWebRequestServer(unittest.TestCase):
    def setUp(self):
        # Set up the test client
        self.app = app
        self.client = self.app.test_client()

    def test_server_is_up_and_running(self):
        # Test if the server is up and running
        response = self.client.get('/api')
        self.assertEqual(response.status_code, 200)

    def test_gunicorn_configuration(self):
        """Test if Gunicorn is configured with the correct settings."""
        self.assertEqual(os.getenv('GUNICORN_WORKERS'), '4')
        self.assertEqual(os.getenv('GUNICORN_WORKER_CLASS'), 'gevent')

    def test_jsonrpc_endpoint(self):
        # Test if the JSON-RPC endpoint is available
        response = self.client.post('/api', json={
            "jsonrpc": "2.0",
            "method": "llm_plugin_get",
            "params": {
                "plugin": "test_plugin",
                "plugin_config": {}
            },
            "id": 1
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('result', response.json)

    def test_health_check(self):
        # Test the health check endpoint
        response = self.client.get('/status')
        self.assertEqual(response.status_code, 200)
        self.assertIn('ready', response.json)
        self.assertTrue(response.json['ready'])

if __name__ == '__main__':
    unittest.main()