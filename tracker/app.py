"""Flask routes for the transaction tracker."""

import hmac
import logging
import openai
from flask import Flask, render_template, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge
from tracker.service import (
    config,
    get_category_and_account,
    extract_transaction_from_image,
    create_transaction,
)
from tracker.transactions import ImageProcessingError, ModelResponseError

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES


def _validate_transaction(data, accounts):
    """Validate transaction data and return invalid fields."""
    invalid_fields = []

    if not isinstance(data, dict):
        invalid_fields.append("body")
    else:
        amount = data.get("amount")
        account = data.get("account")
        date = data.get("date")

        if not isinstance(amount, (int, float)) or isinstance(amount, bool):
            invalid_fields.append("amount")
        if account not in accounts:
            invalid_fields.append("account")
        if not isinstance(date, str) or not date:
            invalid_fields.append("date")

    return invalid_fields


@app.errorhandler(RequestEntityTooLarge)
def upload_too_large(_error):
    return jsonify({"success": False, "error": "Image size cannot exceed 10MB"}), 413


@app.before_request
def authenticate_api():
    """Require a Bearer token for transaction APIs when one is configured."""
    expected_token = config.tracker_api_token
    if request.path.startswith("/api/transaction/") and expected_token:
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme != "Bearer" or not hmac.compare_digest(
            token.encode(), expected_token.encode()
        ):
            return jsonify({"success": False, "error": "Unauthorized request"}), 401
    return None


@app.route("/")
def index():
    return render_template("index.html", auth_required=bool(config.tracker_api_token))


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/transaction/options")
def transaction_options():
    """
    API endpoint to fetch available categories and accounts.

    This endpoint is called by the frontend on page load to populate
    the category and account dropdown options.

    Returns:
        JSON response:
            - success: bool - Whether the request succeeded
            - categories: List[str] - Available category names
            - accounts: List[str] - Available account names

    Status Codes:
        200: Success
        401: Unauthorized request
        500: Server error (database query failed)
    """
    try:
        options = get_category_and_account()
        return jsonify({"success": True, **options})
    except Exception:
        logger.exception("Failed to load transaction options.")
        return (
            jsonify(
                {"success": False, "error": "Failed to load categories and accounts"}
            ),
            500,
        )


@app.route("/api/transaction/upload", methods=["POST"])
def transaction_upload():
    """
    API endpoint to handle transaction image upload and AI extraction.

    Request:
        - Content-Type: multipart/form-data
        - file: Image file (JPG/PNG, max 10MB)

    Returns:
        JSON response:
            - success: bool - Whether extraction succeeded
            - data: dict - Extracted transaction data
            - error: str - Error message (only if success=false)

    Status Codes:
        200: Success
        400: Bad request (no file, empty filename, or invalid image)
        401: Unauthorized request
        413: Request body exceeds 10MB
        422: Model response does not contain valid transaction fields
        500: Server error (processing or AI extraction failed)
        502: Upstream model returned an invalid response or API failure
        504: Upstream model API timeout
    """
    try:
        # Validate file upload
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file uploaded"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"success": False, "error": "Empty filename"}), 400

        # Read image bytes
        image_bytes = file.read()

        # Extract transaction data
        extracted_data = extract_transaction_from_image(image_bytes)

        # Validate transaction data
        valid_accounts = get_category_and_account()["accounts"]
        invalid_fields = _validate_transaction(extracted_data, valid_accounts)
        if invalid_fields:
            message = f"Invalid transaction data: {', '.join(invalid_fields)}"
            return jsonify({"success": False, "error": message}), 422
        extracted_data["amount"] = abs(extracted_data["amount"])

        return jsonify({"success": True, "data": extracted_data})

    except RequestEntityTooLarge:
        raise
    except ImageProcessingError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except ModelResponseError as e:
        logger.warning("Invalid model response: %s", e)
        return jsonify({"success": False, "error": "Model returned invalid data"}), 502
    except openai.APITimeoutError as e:
        logger.warning("Model API timed out: %s", e)
        return jsonify({"success": False, "error": "Model API timed out"}), 504
    except openai.APIError as e:
        logger.warning("Model API failed: %s", e)
        return jsonify({"success": False, "error": "Model API unavailable"}), 502
    except Exception:
        logger.exception("Failed to extract transaction from image.")
        return (
            jsonify({"success": False, "error": "Failed to process transaction image"}),
            500,
        )


@app.route("/api/transaction/confirm", methods=["POST"])
def transaction_confirm():
    """
    API endpoint to create Notion entry from user-confirmed transaction data.

    Request:
        - Content-Type: application/json
        - Body: Transaction data object
            {
                "merchant": str,
                "amount": float,
                "category": str,
                "account": str,
                "date": str (YYYY-MM-DD)
            }

    Returns:
        JSON response:
            - success: bool - Whether creation succeeded
            - notionUrl: str - URL of created Notion page (only if success=true)
            - error: str - Error message (only if success=false)

    Status Codes:
        200: Success
        400: Bad request (invalid transaction data)
        401: Unauthorized request
        413: Request body exceeds 10MB
        500: Server error (Notion creation failed)
    """
    try:
        # Get user-confirmed data from request
        data = request.get_json(silent=True)
        valid_accounts = get_category_and_account()["accounts"]
        invalid_fields = _validate_transaction(data, valid_accounts)
        if invalid_fields:
            message = f"Invalid transaction data: {', '.join(invalid_fields)}"
            return jsonify({"success": False, "error": message}), 400
        data["amount"] = abs(data["amount"])

        # Create Notion entry
        notion_url = create_transaction(data)

        return jsonify({"success": True, "notionUrl": notion_url})

    except RequestEntityTooLarge:
        raise
    except Exception:
        logger.exception("Failed to create confirmed transaction.")
        return (
            jsonify({"success": False, "error": "Failed to create Notion entry"}),
            500,
        )


@app.route("/api/transaction/shortcut", methods=["POST"])
def transaction_shortcut():
    """
    API endpoint for one-step transaction tracking (extraction + page creation).

    Designed for iOS Shortcut automation.

    Request:
        - Content-Type: multipart/form-data
        - file: Image file

    Returns:
        JSON response:
            - success: bool - Whether extraction succeeded
            - notionUrl: str - URL of created Notion page (only if success=true)
            - message: str - Friendly message for Shortcut (only if success=true)
            - error: str - Error message (only if success=false)

    Status Codes:
        200: Success
        400: Bad request (no file, empty filename, or invalid image)
        401: Unauthorized request
        413: Request body exceeds 10MB
        422: Model response does not contain valid transaction fields
        500: Server error (image processing or AI extraction failed)
        502: Upstream model returned an invalid response or API failure
        504: Upstream model API timeout
    """
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file uploaded"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"success": False, "error": "Empty filename"}), 400

        # Extract transaction data
        image_bytes = file.read()
        extracted_data = extract_transaction_from_image(image_bytes)

        # Validate transaction data
        valid_accounts = get_category_and_account()["accounts"]
        invalid_fields = _validate_transaction(extracted_data, valid_accounts)
        if invalid_fields:
            message = f"Invalid transaction data: {', '.join(invalid_fields)}"
            return jsonify({"success": False, "error": message}), 422
        extracted_data["amount"] = abs(extracted_data["amount"])

        # Create Notion page
        notion_url = create_transaction(extracted_data)

        # Construct a friendly response for Shortcut
        message = (
            f"🏪 {extracted_data.get('merchant') or 'Unknown'}\n"
            f"💰 {extracted_data.get('amount') or 0}\n"
            f"📅 {extracted_data.get('date') or 'Today'}\n"
            f"🏷️ {extracted_data.get('category') or 'Unknown'}\n"
            f"💳 {extracted_data.get('account') or 'Unknown'}"
        )

        return (
            jsonify(
                {
                    "success": True,
                    "notionUrl": notion_url,
                    "message": message,
                }
            ),
            200,
        )

    except RequestEntityTooLarge:
        raise
    except ImageProcessingError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except ModelResponseError as e:
        logger.warning("Invalid model response for Shortcut: %s", e)
        return jsonify({"success": False, "error": "Model returned invalid data"}), 502
    except openai.APITimeoutError as e:
        logger.warning("Model API timed out for Shortcut: %s", e)
        return jsonify({"success": False, "error": "Model API timed out"}), 504
    except openai.APIError as e:
        logger.warning("Model API failed for Shortcut: %s", e)
        return jsonify({"success": False, "error": "Model API unavailable"}), 502
    except Exception:
        logger.exception("Failed to create transaction for Shortcut.")
        return (
            jsonify({"success": False, "error": "Failed to create Notion entry"}),
            500,
        )
