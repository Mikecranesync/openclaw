"""CLI entry point: python -m openclaw"""

from __future__ import annotations

import uvicorn

from openclaw.config import OpenClawConfig
from openclaw.observability.logging import setup_logging


def main() -> None:
    config = OpenClawConfig.from_yaml()
    setup_logging(config.log_level)

    uvicorn.run(
        "openclaw.app:create_app",
        factory=True,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
    )


if __name__ == "__main__":
    main()
