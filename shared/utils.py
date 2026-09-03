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
        raise RuntimeError(f"Set required environment variable: {name}")
    return value


def get_title(properties):
    """Extract the Name title from Notion page properties."""
    title = properties.get("Name", {}).get("title", [])
    return "".join(item.get("plain_text", "") for item in title) or None


def query_all_pages(notion_client, database_id, filter=None):
    """Return all pages from a Notion database query."""
    pages = []
    start_cursor = None
    query = {"database_id": database_id, "page_size": 100}

    if filter is not None:
        query["filter"] = filter

    while True:
        if start_cursor:
            query["start_cursor"] = start_cursor

        response = notion_client.databases.query(**query)
        pages.extend(response.get("results", []))

        if not response.get("has_more"):
            return pages

        start_cursor = response.get("next_cursor")
        if not start_cursor:
            raise RuntimeError("Notion response has_more but no next_cursor")
