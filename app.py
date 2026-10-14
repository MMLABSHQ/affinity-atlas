"""Local demo server. No pip install required. Run: python3 app.py"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from engine import run_research
from qloo_client import QlooError
from agent_reviewer import configured as llm_configured

ROOT = Path(__file__).resolve().parent
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8765"))
ENV_KEY = os.environ.get("QLOO_API_KEY", "").strip()
FILES = {"/": ("index.html", "text/html; charset=utf-8"),
         "/style.css": ("style.css", "text/css; charset=utf-8"),
         "/app.js": ("app.js", "text/javascript; charset=utf-8")}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        # Avoid accidentally logging request content or secrets.
        pass

    def _headers(self, code, content_type):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()

    def _json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._headers(code, "application/json; charset=utf-8")
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self._json(200, {"ok": True, "server_key_configured": bool(ENV_KEY), "llm_configured": llm_configured()})
        if self.path not in FILES:
            return self._json(404, {"error": "Ruta no encontrada"})
        filename, content_type = FILES[self.path]
        body = (ROOT / filename).read_bytes()
        self._headers(200, content_type)
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/program":
            return self._json(404, {"error": "Ruta no encontrada"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 16384:
                return self._json(400, {"error": "Solicitud demasiado grande o vacía"})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"error": "Solicitud JSON no válida"})
        artist = str(data.get("artist", "")).strip()
        city = str(data.get("city", "")).strip()
        objective = str(data.get("objective", "")).strip()
        if not (2 <= len(artist) <= 80 and 2 <= len(city) <= 80 and 3 <= len(objective) <= 180):
            return self._json(400, {"error": "Comprueba los campos: artista, ciudad y objetivo"})
        # Browser-supplied keys are allowed ONLY for the locally bound demo.
        # In public deployment, require server-side environment key.
        key = ENV_KEY or (str(data.get("api_key", "")).strip() if HOST in ("127.0.0.1", "localhost", "::1") else "")
        if not key:
            return self._json(400, {"error": "Falta la clave Qloo. En modo local, introdúcela en el formulario."})
        try:
            return self._json(200, run_research(key, artist, city, objective))
        except QlooError as exc:
            return self._json(502, {"error": str(exc)})
        except Exception:
            return self._json(500, {"error": "Error interno. Comprueba la terminal, sin compartir claves."})


if __name__ == "__main__":
    if HOST not in ("127.0.0.1", "localhost", "::1") and not ENV_KEY:
        raise SystemExit("Para publicar en red, configura QLOO_API_KEY en el servidor")
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[OK] Cultural Programming Agent disponible en http://127.0.0.1:{PORT}", flush=True)
    print("[INFO] Para cerrar, pulsa Ctrl+C. La clave no se guarda en archivos.", flush=True)
    httpd.serve_forever()
