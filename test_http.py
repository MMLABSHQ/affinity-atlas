"""Local HTTP contract tests; no Qloo network traffic."""
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from app import Handler


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.root = "http://127.0.0.1:%s" % cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def test_health_and_nostore(self):
        with urllib.request.urlopen(self.root + "/health", timeout=3) as res:
            data = json.load(res)
            self.assertTrue(data["ok"])
            self.assertEqual(res.headers.get("Cache-Control"), "no-store")

    def test_invalid_request_is_rejected(self):
        req = urllib.request.Request(self.root + "/api/program", data=b"{}",
                                     headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(cm.exception.code, 400)
        cm.exception.close()

    def test_local_demo_assets_exist(self):
        for path in ("/", "/app.js", "/style.css"):
            with urllib.request.urlopen(self.root + path, timeout=3) as res:
                self.assertEqual(res.status, 200)
                self.assertGreater(len(res.read()), 100)


if __name__ == "__main__":
    unittest.main()
