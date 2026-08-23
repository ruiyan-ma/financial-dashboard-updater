"""Read portfolio databases and publish a JSON snapshot to Notion."""

import json
import logging
from datetime import datetime, timezone

from shared.utils import query_all_pages, required_env
from updater.notion import notion_client

logger = logging.getLogger(__name__)

ASSET_FIELDS = {
    "Name": "name",
    "Market": "market",
    "Type": "type",
    "Currency": "currency",
    "Ticker": "ticker",
    "Price": "price",
    "Market Value (USD)": "market_value_usd",
    "P/L (%)": "profit_loss_percent",
}

HOLDING_FIELDS = {
    "Name": "name",
    "Quantity": "quantity",
    "Average Cost": "average_cost",
    "Current Price": "current_price",
    "Cost Basis": "total_cost",
    "Market Value": "market_value",
    "P/L": "profit_loss",
    "P/L (%)": "profit_loss_percent",
    "Total Fees": "total_fees",
}

PLATFORM_FIELDS = {
    "Name": "name",
    "Currency": "currency",
    "Market Value": "market_value",
    "Cash Balance": "cash_balance",
    "Total Value": "total_value",
    "Deposit Amount": "deposit_amount",
    "P/L": "profit_loss",
    "P/L (%)": "profit_loss_percent",
    "Holdings": "holdings",
}

NET_VALUE_FIELDS = {
    "Name": "name",
    "Type": "type",
    "Net Value (USD)": "net_value_usd",
}

GROWTH_LOG_FIELDS = {
    "Name": "name",
    "Date": "date",
    "Begin": "begin",
    "End": "end",
    "Growth": "growth",
}


def _plain_text(items):
    """Join a Notion title or rich-text array into a normal string."""
    return "".join(item.get("plain_text", "") for item in items)


def _parse_prop_value(prop_val, relation_name=None):
    """Parse a Notion property value into a simple JSON value.

    relation_name identifies the originating Relation property. It must be preserved
    through nested calls so Relation parsing can select the correct behavior.
    """
    type_val = prop_val.get("type")
    if type_val is None:
        raise ValueError("Notion property value is missing its type")

    data = prop_val.get(type_val)
    if data is None:
        raise ValueError(f"Notion property value for type {type_val!r} is None")

    if type_val in {"number", "string", "boolean", "url", "email", "phone_number"}:
        return data
    if type_val in {"title", "rich_text"}:
        return _plain_text(data)
    if type_val in {"select", "status"}:
        return data.get("name")
    if type_val == "multi_select":
        return [item["name"] for item in data]
    if type_val == "date":
        return data
    if type_val in {"formula", "rollup"}:
        return _parse_prop_value(data, relation_name)
    if type_val == "array":
        return [_parse_prop_value(item, relation_name) for item in data]
    if type_val == "relation":
        return _parse_relation(data, relation_name)

    raise ValueError(f"Unsupported Notion property type: {type_val!r}")


def _parse_relation(relations, relation_name):
    """Parse a relation according to its Relation property name."""
    if relation_name is None:
        raise ValueError("Relation property name is required.")

    if relation_name == "Currency":
        if len(relations) != 1:
            raise ValueError("Currency relation must have exactly one related page.")
        page = notion_client.pages.retrieve(page_id=relations[0]["id"])
        return _parse_prop_value(page["properties"]["Name"])

    if relation_name == "Holdings":
        holdings = [
            _parse_page(
                notion_client.pages.retrieve(page_id=relation["id"]),
                HOLDING_FIELDS,
            )
            for relation in relations
        ]
        return [holding for holding in holdings if holding["quantity"] != 0]

    raise NotImplementedError(f"Relation property {relation_name!r} is not supported")


def _parse_page(page, fields):
    """Parse selected properties from a Notion page."""
    properties = page["properties"]
    result = {}

    for prop_name, json_name in fields.items():
        if prop_name not in properties:
            raise RuntimeError(f"Page property is missing: {prop_name}")
        result[json_name] = _parse_prop_value(properties[prop_name], prop_name)
    return result


def _parse_pages(pages, fields):
    """Parse selected properties from a list of Notion pages."""
    entries = []

    for page in pages:
        entry = {"page_id": page["id"], "url": page.get("url")}
        entry.update(_parse_page(page, fields))
        entries.append(entry)
    return entries


def build_snapshot(asset_pages, platform_pages, net_value_pages, growth_log_pages):
    """Build the stable JSON snapshot for Dashboard pages."""
    assets = _parse_pages(asset_pages, ASSET_FIELDS)
    assets = [asset for asset in assets if asset["market_value_usd"] != 0]

    platforms = _parse_pages(platform_pages, PLATFORM_FIELDS)
    platforms = [platform for platform in platforms if platform["total_value"] != 0]

    net_values = _parse_pages(net_value_pages, NET_VALUE_FIELDS)
    growth_log = _parse_pages(growth_log_pages, GROWTH_LOG_FIELDS)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "assets": assets,
        "platforms": platforms,
        "net_values": net_values,
        "growth_log": growth_log,
    }


def write_snapshot_to_notion(page_id, snapshot):
    """Update the managed JSON code block on the AI Snapshot page."""
    snapshot_json = json.dumps(snapshot, ensure_ascii=False, indent=2)

    blocks = notion_client.blocks.children.list(block_id=page_id).get("results", [])
    code_block = next((block for block in blocks if block.get("type") == "code"), None)

    code = {
        "rich_text": [
            {
                "type": "text",
                "text": {"content": snapshot_json[i : i + 2000]},
            }
            for i in range(0, len(snapshot_json), 2000)
        ],
        "language": "json",
    }

    if code_block:
        notion_client.blocks.update(block_id=code_block["id"], code=code)
    else:
        notion_client.blocks.children.append(
            block_id=page_id,
            children=[{"object": "block", "type": "code", "code": code}],
        )


def generate_snapshot():
    """Read Dashboard databases and publish their snapshot to Notion."""
    asset_pages = query_all_pages(notion_client, required_env("ASSETS_DATABASE_ID"))
    platform_pages = query_all_pages(
        notion_client, required_env("PLATFORMS_DATABASE_ID")
    )
    net_value_pages = query_all_pages(
        notion_client, required_env("NET_VALUE_DATABASE_ID")
    )
    growth_log_pages = query_all_pages(
        notion_client, required_env("GROWTH_LOG_DATABASE_ID")
    )
    snapshot = build_snapshot(
        asset_pages,
        platform_pages,
        net_value_pages,
        growth_log_pages,
    )

    write_snapshot_to_notion(required_env("AI_SNAPSHOT_PAGE_ID"), snapshot)
    logger.info("Wrote Dashboard snapshot to Notion")
