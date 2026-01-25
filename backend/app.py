import threading
from flask import Flask, render_template, jsonify
from backend.core.state import global_state
from backend.core.logic import run_all_updates, config

app = Flask(
    __name__,
    template_folder="../frontend/templates",
    static_folder="../frontend/static",
)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def status():
    return jsonify(global_state.get_snapshot())


@app.route("/api/trigger", methods=["POST"])
def trigger():
    if global_state.get_snapshot()["isRunning"]:
        return jsonify({"success": False, "message": "Update already in progress"}), 409

    # Start in background
    threading.Thread(target=run_all_updates, daemon=True).start()
    return jsonify({"success": True, "message": "Update started"})


def start_web_server():
    """Starts the Flask server."""
    # Turn off banner to keep console clean
    import logging

    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)

    # Host needs to be 0.0.0.0 to be accessible if using tools like Tailscale mentioned in README
    app.run(host="0.0.0.0", port=config.port)
