import threading
from dataclasses import dataclass
from typing import List, Dict


@dataclass
class UpdateError:
    """Represents a single failure during the update process."""

    name: str
    message: str


class UpdateState:
    """Thread-safe state manager for the update process."""

    def __init__(self):
        self.lock = threading.Lock()
        self._phase = "Idle"  # ["Idle", "Starting...", "Updating XXX..."]
        self._total_items = 0
        self._processed_items = 0
        self._errors: List[UpdateError] = []
        self._last_message = ""  # most recent status message (e.g. "✅ Updated AAPL")
        self._last_status = "normal"  # "normal", "success", "error"

    def start_cycle(self):
        """Resets all variables to begin a new cycle. Should be called at the beginning of run_all_updates."""
        with self.lock:
            self._phase = "Starting..."
            self._total_items = 0
            self._processed_items = 0
            self._errors.clear()
            self._last_message = ""
            self._last_status = "normal"

    def finish_cycle(self):
        """Marks the update cycle as complete. Should be called at the end of run_all_updates."""
        with self.lock:
            self._phase = "Idle"
            self._last_message = ""
            self._last_status = "normal"

    def set_phase(self, phase: str, total: int):
        """Updates the current phase and resets the progress counters for that phase."""
        with self.lock:
            self._phase = phase
            self._total_items = total
            self._processed_items = 0
            self._last_message = ""
            self._last_status = "normal"

    def update_progress(self, msg, status="normal"):
        """Increments the processed item count and updates the scrolling bar."""
        with self.lock:
            self._processed_items += 1
            self._last_message = msg
            self._last_status = status

    def add_error(self, name: str, message: str):
        """Records an error for the final report."""
        with self.lock:
            self._errors.append(UpdateError(name, message))

    def get_snapshot(self) -> Dict:
        """Returns a thread-safe copy of the current state for the Web UI."""
        with self.lock:
            return {
                "isRunning": self._phase != "Idle",
                "success": len(self._errors) == 0,
                "phase": self._phase,
                "progress": {
                    "current": self._processed_items,
                    "total": self._total_items,
                    "percent": (
                        int((self._processed_items / self._total_items * 100))
                        if self._total_items > 0
                        else 0
                    ),
                },
                "lastMessage": self._last_message,
                "lastStatus": self._last_status,
                "errors": [
                    {"name": e.name, "message": e.message} for e in self._errors
                ],
            }


# Global state instance
global_state = UpdateState()
