import json
import io
import base64
from PIL import Image
from openai import OpenAI
from backend.services.utils import get_title

MAX_IMAGE_SIZE = 1024
JPEG_QUALITY = 85
MAX_TOKEN = 120
DEFAULT_ACCOUNT_TYPE = "checking"
INCOME_ICON = "https://www.notion.so/icons/arrow-down_green.svg"
EXPENSE_ICON = "https://www.notion.so/icons/arrow-up_red.svg"


class XactService:
    """Stateful service for transaction (Income/Expense) tracking operations."""

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


def _parse_model_json(content):
    """Parses the JSON object in the model response."""
    if isinstance(content, list):
        text = "\n".join(
            item.get("text") if isinstance(item, dict) else getattr(item, "text", "")
            for item in content
        )
    else:
        text = str(content or "")

    text = text.strip()
    if not text:
        raise ValueError("Model returned empty response.")

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        preview = text[:200].replace("\n", "\\n")
        raise ValueError(
            f"Model did not return a JSON object. Response preview: {preview}"
        )

    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        preview = text[:200].replace("\n", "\\n")
        raise ValueError(f"Model returned invalid JSON. Response preview: {preview}")


def extract_xact_data(
    image_bytes, api_key, base_url, model_name, category_map, account_map
):
    """Extracts transaction details from an image using vision LLM."""
    if not api_key:
        raise ValueError("API key is missing")

    # Separate categories by income/expense type
    incomes = [name for name, data in category_map.items() if data["type"] == "Income"]
    expenses = [
        name for name, data in category_map.items() if data["type"] == "Expense"
    ]

    income_str = ", ".join(incomes) if incomes else "N/A"
    expense_str = ", ".join(expenses) if expenses else "N/A"
    account_str = ", ".join(account_map.keys())

    prompt = f"""
Analyze this image and extract transaction details.

Return ONLY raw JSON in this format:
{{"merchant": "store/merchant name", "amount": number, "category": "from list", "account": "from list", "date": "YYYY-MM-DD"}}

Field rules:
- Merchant: select the value from '商品说明' field if available, otherwise use the bold title text.
- Amount: determine income or expense from the original amount shown in the image, but return the absolute value only.
- Category:
  - If the original amount is positive, choose only from [{income_str}]
  - If the original amount is negative, choose only from [{expense_str}]
- Account: read '支付方式' or '付款方式'
  - WeChat keywords: '零钱', '微信支付'
  - Alipay keywords: '余额', '花呗', '支付宝'
  - Bank cards: use the exact bank name shown
  - MUST choose from: [{account_str}]

General rules:
1. If the image is NOT a receipt, transaction, or bill, set all fields to null.
2. If any specific field is missing or uncertain, set only that field to null.
3. Return JSON only. No explanation, no markdown, no code fences.
"""

    client = OpenAI(api_key=api_key, base_url=base_url)
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"},
                },
            ],
        },
    ]

    request_kwargs = {
        "model": model_name,
        "temperature": 0,
        "max_tokens": MAX_TOKEN,
        "messages": messages,
    }
    res = client.chat.completions.create(**request_kwargs)
    return _parse_model_json(res.choices[0].message.content)


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
