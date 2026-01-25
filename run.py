import time
import warnings
import threading
import logging
import traceback
import schedule
from backend.services.common import Colors, setup_logging
from backend.core.logic import run_all_updates, config
from backend.app import start_web_server


def scheduler_loop():
    # Schedule updates to run every hour at :30
    schedule.every().hour.at(":30").do(run_all_updates)
    run_all_updates()

    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute


def main():
    setup_logging()

    # Ignore all DeprecationWarnings and their subclasses (e.g., Pandas4Warning)
    warnings.filterwarnings("ignore", category=DeprecationWarning)

    # Start Scheduler in a background thread
    threading.Thread(target=scheduler_loop, daemon=True).start()

    # Display startup info
    msg = f"\n{Colors.CYAN}📡 Web Dashboard active at http://localhost:{config.port}{Colors.ENDC}\n"
    print(msg)

    # Start Flask Web Server in the MAIN thread
    try:
        start_web_server()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}👋 Shutdown requested. Goodbye!{Colors.ENDC}")
    except Exception as e:
        # Write full traceback to the file log
        logging.critical("Application crashed with an unexpected error", exc_info=True)

        # Print detailed error to console
        print(f"\n{Colors.RED}❌ ERROR: {str(e)}{Colors.ENDC}")
        traceback.print_exc()
        print(f"{Colors.YELLOW}Server exited unexpectedly.{Colors.ENDC}")


if __name__ == "__main__":
    main()
