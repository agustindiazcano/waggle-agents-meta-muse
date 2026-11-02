"""Run the API with ``python -m waggle.api``. It binds to 127.0.0.1 unless told otherwise."""

import os

import uvicorn

from waggle.api import config
from waggle.api.app import create_app


def main() -> None:
    """Read the configuration and serve. A bad value stops the start with ConfigError."""
    cfg = config.from_env(os.environ)
    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port, log_level="info")


if __name__ == "__main__":
    main()
