"""
Automatically extracts transaction details from payment screenshots using Gemini AI
and creates entries in Notion with intelligent categorization and icons.

Usage: python auto_expense.py <image_path>
"""

import os
import sys
import json
import io
from pathlib import Path
from dotenv import load_dotenv
import google.genai as genai
from google.genai import types
from notion_client import Client
from PIL import Image


# ============================================================================
# UI Helpers
# ============================================================================


class UI:
    """Simple colored terminal output helper."""

    BLUE, GREEN, YELLOW, RED, BOLD, RESET = (
        "\033[96m",
        "\033[92m",
        "\033[93m",
        "\033[91m",
        "\033[1m",
        "\033[0m",
    )

    @staticmethod
    def info(msg):
        print(f"{UI.BLUE}ℹ️ {msg}{UI.RESET}")

    @staticmethod
    def success(msg):
        print(f"{UI.GREEN}✅ {msg}{UI.RESET}")

    @staticmethod
    def warn(msg):
        print(f"{UI.YELLOW}⚠️ {msg}{UI.RESET}")

    @staticmethod
    def error(msg):
        print(f"{UI.RED}❌ {msg}{UI.RESET}")


# ============================================================================
# Core Functions
# ============================================================================


def process_image(image_path):
    """Loads and optimizes an image for AI analysis."""
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGB")

            # Resize large images to reduce API latency and cost
            if max(img.size) > 1024:
                img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)

            # Convert to JPEG bytes
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            img_bytes = buf.getvalue()

            UI.success(f"Image processed: {len(img_bytes)/1024:.1f} KB")
            return img_bytes
    except Exception as e:
        UI.error(f"Image processing failed: {e}")
        sys.exit(1)


def _get_title(properties):
    """Helper function to extract title from Notion page properties."""
    for prop in properties.values():
        if prop["type"] == "title" and prop["title"]:
            return prop["title"][0]["plain_text"]
    return None


def fetch_categories(notion, db_id):
    """Fetches categories from Notion database with their types (Income/Expense)."""
    try:
        results = notion.databases.query(database_id=db_id).get("results", [])
        categories = {}

        for page in results:
            props = page["properties"]
            name = _get_title(props)
            if not name:
                continue

            # Extract category type (Income/Expense)
            type = props.get("Type", {}).get("select", {}).get("name", "Expense")
            categories[name] = type

        return categories
    except Exception as e:
        UI.warn(f"Failed to fetch categories: {e}")
        return {}


def fetch_accounts(notion, db_id, account_type="checking"):
    """Fetches account names from Notion database, filtered by type."""
    try:
        results = notion.databases.query(database_id=db_id).get("results", [])
        accounts = []

        for page in results:
            props = page["properties"]
            name = _get_title(props)
            if not name:
                continue

            # Filter by account type
            acc_type = props.get("Type", {}).get("select", {}).get("name", "")
            if acc_type.lower() == account_type.lower():
                accounts.append(name)

        return accounts
    except Exception as e:
        UI.warn(f"Failed to fetch accounts: {e}")
        return []


def extract_with_ai(image_bytes, api_key, category_map, accounts):
    """Extracts transaction details from an image using Gemini AI."""
    client = genai.Client(api_key=api_key)

    # Separate categories by income/expense type
    incomes = [category for category, type in category_map.items() if type == "Income"]
    expenses = [category for category, type in category_map.items() if type == "Expense"]

    income_str = ", ".join(incomes) if incomes else "N/A"
    expense_str = ", ".join(expenses) if expenses else "N/A"
    account_str = ", ".join(accounts)

    # AI Prompt (DO NOT MODIFY - carefully tuned for accuracy)
    prompt = f"""
Analyze this transaction and return ONLY raw JSON:
{{"merchant": "store/merchant name", "amount": number, "category": "from list", "account": "from list", "date": "YYYY-MM-DD"}}

Rules:
1. Merchant logic:
   - WeChat: Use bold text at the top.
   - Alipay: Use '商品说明' field.
   - Avoid generic names like '淘宝闪购' if a specific store is visible.

2. Amount logic: MUST be positive number without sign (e.g. -41.4 → 41.4, +100 → 100)

3. Category logic:
   - If the number is POSITIVE (e.g. +100 or 100), this is INCOME, category MUST be from [{income_str}]
   - If the number is NEGATIVE (e.g. -50), this is EXPENSE, category MUST be from [{expense_str}]

4. Account keywords: Read "支付方式" or "付款方式" field
   - WeChat keywords: '零钱', '微信零钱'
   - Alipay keywords: '余额', '账户余额', '花呗'
   - Bank cards: Use the exact bank name if mentioned (e.g. '招商银行信用卡')
   - MUST be from: [{account_str}]
"""

    UI.info("Analyzing with Gemini 2.5 Flash...")
    res = client.models.generate_content(
        model="models/gemini-2.5-flash",
        contents=[
            prompt,
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
        ],
    )

    # Parse JSON response (remove markdown formatting if present)
    clean_text = res.text.strip(" `\n")
    if clean_text.startswith("json"):
        clean_text = clean_text[4:].strip()
    return json.loads(clean_text)


def create_entry(notion, config, data, category_map):
    """Creates a new Income/Expense entry."""

    def find_page_id(db_id, name):
        """Helper to find a page ID by its title."""
        results = notion.databases.query(database_id=db_id).get("results", [])
        for page in results:
            for prop in page["properties"].values():
                if (
                    prop["type"] == "title"
                    and prop["title"]
                    and prop["title"][0]["plain_text"].lower() == name.lower()
                ):
                    return page["id"]
        return None

    # Determine icon based on transaction type
    category = data.get("category")
    icon_url = (
        "https://www.notion.so/icons/arrow-down_green.svg"
        if category_map.get(category) == "Income"
        else "https://www.notion.so/icons/arrow-up_red.svg"
    )

    # Build page properties
    props = {
        "Name": {"title": [{"text": {"content": data.get("merchant", "Unknown")}}]},
        "Amount": {"number": float(data.get("amount", 0))},
        "Date": {"date": {"start": data.get("date")}} if data.get("date") else None,
    }

    # Link category and account relations
    for key, db_id in [("category", config["category_db"]), ("account", config["account_db"])]:
        value = data.get(key)
        if value:
            UI.info(f"Linking {key}: {value}...")
            page_id = find_page_id(db_id, value)
            if page_id:
                props[key.capitalize()] = {"relation": [{"id": page_id}]}

    # Create the Notion page
    page = notion.pages.create(
        parent={"database_id": config["inc_exp_db"]},
        properties={k: v for k, v in props.items() if v},  # Filter out None values
        icon={"type": "external", "external": {"url": icon_url}},
    )
    UI.success(f"Entry created: {page['url']}")


# ============================================================================
# Main Entry Point
# ============================================================================


def main():
    """Main execution flow."""
    if len(sys.argv) < 2:
        UI.error("Usage: python auto_expense.py <image_path>")
        return

    # Load environment variables
    load_dotenv(Path(__file__).parent / ".env")
    config = {
        "key": os.getenv("GEMINI_API_KEY"),
        "token": os.getenv("INTERNAL_INTEGRATION_TOKEN"),
        "inc_exp_db": os.getenv("INC_EXP_DATABASE_ID"),
        "category_db": os.getenv("CATEGORIES_DATABASE_ID"),
        "account_db": os.getenv("ACCOUNTS_DATABASE_ID"),
    }

    # Validate configuration
    if not all(config.values()):
        UI.error("Missing configuration in .env file")
        return

    # Initialize Notion client
    notion = Client(auth=config["token"])
    UI.info("Syncing Notion database data...")
    category_map = fetch_categories(notion, config["category_db"])
    accounts = fetch_accounts(notion, config["account_db"])

    # Process transaction
    try:
        img_data = process_image(sys.argv[1])
        extracted_data = extract_with_ai(img_data, config["key"], category_map, accounts)

        # Display extracted data
        print(f"\n{UI.BOLD}===== Extracted Data ====={UI.RESET}")
        for key, value in extracted_data.items():
            print(f"{key.capitalize()}: {value}")
        print()

        # Create Notion entry
        create_entry(notion, config, extracted_data, category_map)
        UI.success("\n🎉 Done!")

    except Exception as e:
        UI.error(f"Execution failed: {e}")


if __name__ == "__main__":
    main()
