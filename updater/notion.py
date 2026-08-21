"""Single Notion client shared by all Dashboard updater modules."""

import httpx
from dotenv import load_dotenv
from notion_client import Client

from shared.utils import required_env

load_dotenv()

notion_client = Client(
    auth=required_env("INTERNAL_INTEGRATION_TOKEN"),
    client=httpx.Client(trust_env=False),
)
