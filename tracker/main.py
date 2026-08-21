"""Run the transaction tracker locally."""

import re
import warnings
import logging
from tracker.service import config
from tracker.app import app
from shared.utils import setup_logging


class Colors:
    """ANSI color codes for the local terminal UI."""

    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    ENDC = "\033[0m"


def main():
    setup_logging()

    # Silence third-party noise
    logging.getLogger("openai").setLevel(logging.WARNING)

    # Suppress noise from HTTPS handshakes / port scanners hitting the HTTP port.
    werkzeug_noise = re.compile(r"code 400, message Bad request (version|syntax)")

    class WerkzeugNoiseFilter(logging.Filter):
        def filter(self, record):
            return not werkzeug_noise.search(record.getMessage())

    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.setLevel(logging.ERROR)
    werkzeug_logger.addFilter(WerkzeugNoiseFilter())

    # Ignore all DeprecationWarnings and their subclasses (e.g., Pandas4Warning)
    warnings.filterwarnings("ignore", category=DeprecationWarning)

    # Display startup info
    message = f"\n{Colors.CYAN}📡 Transaction Tracker active at http://localhost:{config.port}{Colors.ENDC}\n"
    print(message)

    # Start Flask Web Server in the MAIN thread
    try:
        app.run(host="0.0.0.0", port=config.port)
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}👋 Shutdown requested. Goodbye!{Colors.ENDC}")


if __name__ == "__main__":
    main()
