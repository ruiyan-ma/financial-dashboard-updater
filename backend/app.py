import threading
from flask import Flask, render_template, jsonify, request
from backend.core.state import global_state
from backend.core.logic import (
    config,
    run_all_updates,
    get_cat_and_acct_opts,
    get_xact_data_from_img,
    create_xact_entry,
)

app = Flask(
    __name__,
    template_folder="../frontend/templates",
    static_folder="../frontend/static",
)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/updater")
def updater_page():
    return render_template("updater.html")


@app.route("/api/updater/status")
def updater_status():
    return jsonify(global_state.get_snapshot())


@app.route("/api/updater/trigger", methods=["POST"])
def updater_trigger():
    if global_state.get_snapshot()["isRunning"]:
        return jsonify({"success": False, "message": "Update already in progress"}), 409

    # Start in background
    threading.Thread(target=run_all_updates, daemon=True).start()
    return jsonify({"success": True, "message": "Update started"})


@app.route("/api/transaction/options")
def xact_options():
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
        500: Server error (database query failed)
    """
    try:
        options = get_cat_and_acct_opts()
        return jsonify({"success": True, **options})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/transaction/upload", methods=["POST"])
def xact_upload():
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
        400: Bad request (no file or empty filename)
        500: Server error (processing or AI extraction failed)
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

        # Extract transaction data using AI
        extracted_data = get_xact_data_from_img(image_bytes)

        return jsonify({"success": True, "data": extracted_data})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/transaction/confirm", methods=["POST"])
def xact_confirm():
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
        400: Bad request (no data provided)
        500: Server error (Notion creation failed)
    """
    try:
        # Get user-confirmed data from request
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400

        # Create Notion entry
        notion_url = create_xact_entry(data)

        return jsonify({"success": True, "notionUrl": notion_url})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/transaction/shortcut", methods=["POST"])
def xact_shortcut():
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
        400: Bad request (no file or empty filename)
        422: Unprocessable Entity (AI extraction failed to find amount or date)
        500: Server error (image processing or AI extraction failed)
    """
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file uploaded"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"success": False, "error": "Empty filename"}), 400

        # 1. Extract Data: Need to refresh category_map and account_map
        image_bytes = file.read()
        extracted_data = get_xact_data_from_img(image_bytes, refresh=True)

        # 2. Check minimal viability (Amount and Date)
        if not extracted_data.get("amount") or not extracted_data.get("date"):
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Gemini failed to find amount or date",
                    }
                ),
                422,
            )

        # 3. Create Entry
        notion_url = create_xact_entry(extracted_data)

        # 4. Construct friendly message for Shortcut
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

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def start_web_server():
    """Starts the Flask server."""
    # Turn off banner to keep console clean
    import logging

    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)

    # Host needs to be 0.0.0.0 to be accessible if using tools like Tailscale mentioned in README
    app.run(host="0.0.0.0", port=config.port)
