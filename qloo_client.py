"""Small Qloo HTTP client using only the Python standard library."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

BASE_URL = "https://hackathon.api.qloo.com"
ARTIST_TYPE = "urn:entity:artist"


class QlooError(RuntimeError):
    pass


@dataclass
class QlooClient:
    api_key: str
    timeout: int = 25

    def _get(self, path: str, params: dict[str, str]) -> dict:
        url = BASE_URL + path + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url, headers={"X-Api-Key": self.api_key, "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                body = json.load(response)
                if not isinstance(body, dict):
                    raise QlooError("Qloo devolvió una estructura inesperada")
                return body
        except urllib.error.HTTPError as exc:
            raise QlooError(f"Qloo devolvió HTTP {exc.code} en {path}") from None
        except urllib.error.URLError:
            raise QlooError("No se pudo conectar con Qloo") from None
        except (TimeoutError, OSError):
            raise QlooError("La consulta a Qloo agotó el tiempo") from None
        except (ValueError, json.JSONDecodeError):
            raise QlooError("Qloo devolvió JSON no válido") from None

    def search_artist(self, name: str) -> dict:
        data = self._get("/search", {"query": name, "types": ARTIST_TYPE, "take": "5"})
        candidates = [e for e in data.get("results", []) if isinstance(e, dict)
                      and ARTIST_TYPE in e.get("types", [])]
        if not candidates:
            raise QlooError(f"Qloo no encontró ningún artista para: {name}")
        return next((e for e in candidates if e.get("name", "").casefold() == name.casefold()), candidates[0])

    def insights(self, entity_id: str, result_type: str, city: str = "") -> tuple[list[dict], list]:
        params = {
            "filter.type": f"urn:entity:{result_type}",
            "signal.interests.entities": entity_id,
            "feature.explainability": "true",
            "take": "5",
        }
        if result_type == "place":
            params["filter.location.query"] = city
        data = self._get("/v2/insights", params)
        results = data.get("results", {})
        entities = results.get("entities", []) if isinstance(results, dict) else []
        return ([e for e in entities if isinstance(e, dict)], data.get("warnings", []))
