"""Update market data once, then publish the Dashboard snapshot."""

import logging
import time

from backend.services.utils import setup_logging
from gen_snapshot import main as generate_snapshot

FORMULA_REFRESH_DELAY_SECONDS = 5
SNAPSHOT_ATTEMPTS = 3

logger = logging.getLogger(__name__)


def publish_snapshot():
    """Publish the snapshot with retries for transient Notion failures."""
    time.sleep(FORMULA_REFRESH_DELAY_SECONDS)
    for attempt in range(1, SNAPSHOT_ATTEMPTS + 1):
        try:
            generate_snapshot()
            return
        except Exception:
            if attempt == SNAPSHOT_ATTEMPTS:
                raise
            delay = 2**attempt
            logger.warning(
                "Snapshot attempt %d/%d failed; retrying in %ds",
                attempt,
                SNAPSHOT_ATTEMPTS,
                delay,
                exc_info=True,
            )
            time.sleep(delay)


def main():
    setup_logging()
    from backend.core.logic import run_all_updates

    result = run_all_updates()
    if not result["success"]:
        details = "; ".join(
            f"{error['name']}: {error['message']}" for error in result["errors"]
        )
        raise RuntimeError(details)


if __name__ == "__main__":
    main()
