"""Image, model, and Notion operations for transaction tracking."""

import json
import io
import base64
import time
from PIL import Image, UnidentifiedImageError
from shared.utils import get_title

MAX_IMAGE_SIZE = 1536
JPEG_QUALITY = 90
MAX_TOKENS = 120
DEFAULT_ACCOUNT_TYPE = "checking"
INCOME_ICON = "https://www.notion.so/icons/arrow-down_green.svg"
EXPENSE_ICON = "https://www.notion.so/icons/arrow-up_red.svg"


class ImageProcessingError(ValueError):
    """Raised when an uploaded file cannot be processed as an image."""


class ModelResponseError(ValueError):
    """Raised when the vision model returns an unusable response."""


class TransactionCache:
    """Caches category and account mappings from Notion to reduce API calls."""

    def __init__(self, notion_client, cache_ttl_seconds):
        self.notion_client = notion_client
        self.cache_ttl_seconds = cache_ttl_seconds
        self._category_map = {}
        self._account_map = {}
        self._cached_at = 0.0

    def get_category_and_account_maps(self, category_db_id, account_db_id):
        """Refreshes the category and account mappings if the cache has expired."""
        if time.monotonic() - self._cached_at < self.cache_ttl_seconds:
            return self._category_map, self._account_map

        results = self.notion_client.databases.query(database_id=category_db_id).get(
            "results", []
        )
        category_map = {}

        for page in results:
            props = page["properties"]
            name = get_title(props)
            if not name:
                continue

            # Extract category type (Income/Expense) and ID
            category_type = (
                props.get("Type", {}).get("select", {}).get("name", "Expense")
            )
            category_map[name] = {"type": category_type, "id": page["id"]}

        results = self.notion_client.databases.query(database_id=account_db_id).get(
            "results", []
        )
        account_map = {}

        for page in results:
            props = page["properties"]
            name = get_title(props)
            if not name:
                continue

            # Filter by account type
            account_type = props.get("Type", {}).get("select", {}).get("name", "")
            if account_type.lower() == DEFAULT_ACCOUNT_TYPE.lower():
                account_map[name] = page["id"]

        self._category_map = category_map
        self._account_map = account_map
        self._cached_at = time.monotonic()
        return category_map, account_map


def prepare_image(image_bytes):
    """Resize an uploaded image when needed and convert it to JPEG."""
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image = image.convert("RGB")

        # Resize large images to reduce API latency and cost
        if max(image.size) > MAX_IMAGE_SIZE:
            image.thumbnail((MAX_IMAGE_SIZE, MAX_IMAGE_SIZE), Image.Resampling.LANCZOS)

        # Convert to JPEG bytes
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=JPEG_QUALITY)
        return buffer.getvalue()

    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise ImageProcessingError("Invalid image file") from e


def _parse_model_json(content):
    """Parses the JSON object in the model response."""
    text = str(content or "").strip()
    if not text:
        raise ModelResponseError("Model returned empty response.")

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        preview = text[:200].replace("\n", "\\n")
        raise ModelResponseError(
            f"Model did not return a JSON object. Response preview: {preview}"
        )

    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        preview = text[:200].replace("\n", "\\n")
        raise ModelResponseError(
            f"Model returned invalid JSON. Response preview: {preview}"
        ) from e


def extract_transaction_data(
    image_bytes, openai_client, model_name, category_map, account_map
):
    """Extracts transaction details from an image using a vision model."""
    if openai_client is None:
        raise ValueError("OpenAI client is not initialized")

    # Separate categories by income/expense type
    incomes = [name for name, data in category_map.items() if data["type"] == "Income"]
    expenses = [
        name for name, data in category_map.items() if data["type"] == "Expense"
    ]

    income_str = json.dumps(incomes, ensure_ascii=False)
    expense_str = json.dumps(expenses, ensure_ascii=False)
    account_str = json.dumps(list(account_map), ensure_ascii=False)

    prompt = f"""
Analyze this image and extract transaction details.

Return ONLY raw JSON in this format:
{{"merchant": "store/merchant name", "amount": number, "category": "from list", "account": "from list", "date": "YYYY-MM-DD"}}

Field rules:
- Merchant: select '商品说明' if available, otherwise use the bold title text.
- Amount: determine income or expense from the original amount, but return its absolute value.
- Category:
  - Income: choose the best match from {income_str}
  - Expense: choose the best match from {expense_str}
- Account: read '支付方式' or '付款方式'
  - WeChat keywords: '零钱', '微信支付'
  - Alipay keywords: '支付宝', '余额', '花呗', '余额宝'
  - Bank cards: match the bank name shown
  - Choose the best match from {account_str}

General rules:
1. If the image is NOT a receipt, transaction, or bill, set all fields to null.
2. Infer the best reasonable value for every field. Use null only when a field cannot be read or reasonably inferred.
3. Return JSON only. No explanation, no markdown, no code fences.
"""

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

    response = openai_client.chat.completions.create(
        model=model_name,
        temperature=0,
        max_tokens=MAX_TOKENS,
        messages=messages,
        response_format={"type": "json_object"},
        extra_body={"enable_thinking": False},
    )
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as e:
        raise ModelResponseError(
            "Model response did not contain message content."
        ) from e
    return _parse_model_json(content)


def create_transaction_page(
    notion_client,
    database_id,
    transaction,
    category_map,
    account_map,
):
    """Creates a new Notion Income/Expense page.

    Callers should have validated that amount and date are present.
    """

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
        "Name": {"title": [{"text": {"content": transaction.get("merchant") or ""}}]},
        "Amount": {"number": float(transaction.get("amount"))},
        "Date": {"date": {"start": transaction.get("date")}},
    }

    # Link category and account relations using provided maps
    if category_name in category_map:
        category_id = category_map[category_name]["id"]
        props["Category"] = {"relation": [{"id": category_id}]}

    if account_name in account_map:
        account_id = account_map[account_name]
        props["Account"] = {"relation": [{"id": account_id}]}

    # Create the Notion page
    page = notion_client.pages.create(
        parent={"database_id": database_id},
        properties={k: v for k, v in props.items() if v},  # Filter out None values
        icon={"type": "external", "external": {"url": icon_url}},
    )
    return page["url"]
