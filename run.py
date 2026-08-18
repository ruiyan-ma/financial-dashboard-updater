import warnings
from backend.services.utils import Colors, setup_logging
from backend.core.logic import config
from backend.app import start_web_server


def main():
    setup_logging()

    # Ignore all DeprecationWarnings and their subclasses (e.g., Pandas4Warning)
    warnings.filterwarnings("ignore", category=DeprecationWarning)

    # Display startup info
    msg = f"\n{Colors.CYAN}📡 Web Dashboard active at http://localhost:{config.port}{Colors.ENDC}\n"
    print(msg)

    # Start Flask Web Server in the MAIN thread
    try:
        start_web_server()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}👋 Shutdown requested. Goodbye!{Colors.ENDC}")
    except Exception as e:
        logger.critical("Application crashed with an unexpected error", exc_info=True)
        print(f"\n{Colors.RED}❌ ERROR: {str(e)}{Colors.ENDC}")
        print(f"{Colors.YELLOW}Server exited unexpectedly. See logs/app.log for details.{Colors.ENDC}")


if __name__ == "__main__":
    main()
