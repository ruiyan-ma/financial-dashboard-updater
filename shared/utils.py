import logging
import os


def setup_logging():
    """Configure application logs to use one consistent console format."""
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Replace existing handlers so repeated setup does not duplicate log messages.
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Both applications use httpx internally; keep its request logs out of INFO.
    logging.getLogger("httpx").setLevel(logging.WARNING)


def required_env(name):
    """Return a required environment variable or raise a clear error."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Set {name} in .env")
    return value


def get_title(properties):
    """Extract the Name title from Notion page properties."""
    title = properties.get("Name", {}).get("title", [])
    return title[0]["plain_text"] if title else None
