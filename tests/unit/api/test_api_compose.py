"""The compose service of the API keeps the localhost-only exposure."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")


def _api_block() -> str:
    match = re.search(r"^  api:\n(.*?)(?=^  \w)", COMPOSE, re.MULTILINE | re.DOTALL)
    assert match is not None
    return match.group(1)


def test_api_port_is_published_on_localhost_only() -> None:
    assert '"127.0.0.1:8000:8000"' in _api_block()


def test_api_listens_on_all_container_interfaces() -> None:
    assert 'WAGGLE_API_HOST: "0.0.0.0"' in _api_block()
