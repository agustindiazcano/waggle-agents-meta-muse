import json
import re
import threading
import urllib.error
import urllib.request
from pathlib import Path

from waggle.placeholder import make_server

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")


def test_health_endpoint_reports_service_name() -> None:
    server = make_server("api", "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as response:
            body = json.loads(response.read())
            assert response.status == 200
        assert body == {"service": "api", "status": "ok"}
    finally:
        server.shutdown()
        server.server_close()


def test_unknown_path_is_404() -> None:
    server = make_server("api", "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/nope", timeout=5)
        except urllib.error.HTTPError as err:
            assert err.code == 404
        else:
            raise AssertionError("expected a 404")
    finally:
        server.shutdown()
        server.server_close()


def test_compose_declares_all_services() -> None:
    for service in ("db", "api", "worker", "mcp_server", "web"):
        assert re.search(rf"^  {service}:", COMPOSE, re.MULTILINE), service


def test_compose_has_no_rabbitmq_and_no_curl() -> None:
    lowered = COMPOSE.lower()
    assert "rabbitmq" not in lowered  # ADR-003
    assert "curl" not in lowered  # healthchecks use python


def test_every_service_has_a_healthcheck() -> None:
    assert len(re.findall(r"^    healthcheck:", COMPOSE, re.MULTILINE)) == 5


def test_compose_uses_pgvector_image() -> None:
    assert "pgvector/pgvector" in COMPOSE
