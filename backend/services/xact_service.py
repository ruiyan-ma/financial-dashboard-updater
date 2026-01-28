import json
import io
from PIL import Image
from google.genai import Client, types
from backend.services.utils import get_title

MAX_IMAGE_SIZE = 1024
JPEG_QUALITY = 85
DEFAULT_ACCOUNT_TYPE = "checking"
INCOME_ICON = "https://www.notion.so/icons/arrow-down_green.svg"
EXPENSE_ICON = "https://www.notion.so/icons/arrow-up_red.svg"


class XactService:
    """Stateful service for income and expense tracking operations."""

    def __init__(self, notion_client):
        """Initialize the service with a Notion Client instance."""
        self.notion = notion_client
        self._category_map = {}
        self._account_map = {}

    def fetch_category_map(self, db_id, refresh=False):
        """Fetches categories with type (Income/Expense) and page ID."""
        if not refresh and self._category_map:
            return self._category_map

        try:
            results = self.notion.databases.query(database_id=db_id).get("results", [])
            category_map = {}

            for page in results:
                props = page["properties"]
                name = get_title(props)
                if not name:
                    continue

                # Extract category type (Income/Expense) and ID
                typ_val = props.get("Type", {}).get("select", {}).get("name", "Expense")
                category_map[name] = {"type": typ_val, "id": page["id"]}

            self._category_map = category_map
            return category_map
        except Exception as e:
            raise RuntimeError(f"Failed to fetch categories: {e}")

    def fetch_account_map(self, db_id, refresh=False):
        """Fetches accounts with page ID."""
        if not refresh and self._account_map:
            return self._account_map

        try:
            results = self.notion.databases.query(database_id=db_id).get("results", [])
            account_map = {}

            for page in results:
                props = page["properties"]
                name = get_title(props)
                if not name:
                    continue

                # Filter by account type
                acc_type = props.get("Type", {}).get("select", {}).get("name", "")
                if acc_type.lower() == DEFAULT_ACCOUNT_TYPE.lower():
                    account_map[name] = page["id"]

            self._account_map = account_map
            return account_map
        except Exception as e:
            raise RuntimeError(f"Failed to fetch accounts: {e}")


def process_image(image_bytes):
    """Optimizes images for AI analysis by resizing and converting to JPEG."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert("RGB")

        # Resize large images to reduce API latency and cost
        if max(img.size) > MAX_IMAGE_SIZE:
            img.thumbnail((MAX_IMAGE_SIZE, MAX_IMAGE_SIZE), Image.Resampling.LANCZOS)

        # Convert to JPEG bytes
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_QUALITY)
        return buf.getvalue()
    except Exception as e:
        raise ValueError(f"Image processing failed: {e}")


def extract_xact_data(image_bytes, api_key, category_map, account_map):
    """Extracts transaction details from an image using Gemini AI."""
    if not api_key:
        raise ValueError("Gemini API key is missing")

    client = Client(api_key=api_key)

    # Separate categories by income/expense type
    incomes = [name for name, data in category_map.items() if data["type"] == "Income"]
    expenses = [
        name for name, data in category_map.items() if data["type"] == "Expense"
    ]

    income_str = ", ".join(incomes) if incomes else "N/A"
    expense_str = ", ".join(expenses) if expenses else "N/A"
    account_str = ", ".join(account_map.keys())

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


def create_new_entry(client, db_id, transaction, category_map, account_map):
    """Creates a new Income/Expense entry."""

    # Determine icon based on transaction type
    category_name = transaction.get("category")
    account_name = transaction.get("account")

    icon_url = (
        INCOME_ICON
        if category_map.get(category_name, {}).get("type") == "Income"
        else EXPENSE_ICON
    )

    # Build page properties
    props = {
        "Name": {
            "title": [{"text": {"content": transaction.get("merchant", "Unknown")}}]
        },
        "Amount": {"number": float(transaction.get("amount", 0))},
        "Date": (
            {"date": {"start": transaction.get("date")}}
            if transaction.get("date")
            else None
        ),
    }

    # Link category and account relations using provided maps
    if category_name in category_map:
        category_id = category_map[category_name]["id"]
        props["Category"] = {"relation": [{"id": category_id}]}

    if account_name in account_map:
        account_id = account_map[account_name]
        props["Account"] = {"relation": [{"id": account_id}]}

    # Create the Notion page
    page = client.pages.create(
        parent={"database_id": db_id},
        properties={k: v for k, v in props.items() if v},  # Filter out None values
        icon={"type": "external", "external": {"url": icon_url}},
    )
    return page["url"]
