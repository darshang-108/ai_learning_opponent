"""
data_logger.py  –  Phase 2: Per-match behavior logging.

Tracks player actions during each match and appends a summary
row to 'player_data.csv' when the match ends.

Uses only the built-in `csv` module (no pandas).
Designed to be lightweight — one dict in memory, one file write per match.
"""

import csv
import os
import time

# Path to the CSV file (project root)
CSV_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "player_data.csv")

# Column order written to CSV
FIELDNAMES = [
    "match_id",
    "total_attacks",
    "avg_distance",
    "movement_count",
    "match_duration",
    "result",
]


class DataLogger:
    """Collects per-frame stats and writes one row per match."""

    def __init__(self):
        # Persistent across the whole session
        self._next_match_id = 1

        # Per-match accumulators (reset every start_match)
        self.match_id = 0
        self.total_attacks = 0
        self.total_distance = 0.0
        self.frame_count = 0
        self.movement_count = 0
        self.match_start_time = 0.0

    # ── Match lifecycle ───────────────────────────────────

    def start_match(self):
        """Call at the beginning of each match / after a reset."""
        self.match_id = self._next_match_id
        self._next_match_id += 1

        self.total_attacks = 0
        self.total_distance = 0.0
        self.frame_count = 0
        self.movement_count = 0
        self.match_start_time = time.time()

    def end_match(self, result: str):
        """Call when the match ends ('win' or 'lose').

        Calculates summary stats and appends a row to the CSV.
        """
        # Avoid division by zero on an instant match
        avg_distance = (
            self.total_distance / self.frame_count
            if self.frame_count > 0
            else 0.0
        )
        match_duration = time.time() - self.match_start_time

        row = {
            "match_id": self.match_id,
            "total_attacks": self.total_attacks,
            "avg_distance": round(avg_distance, 2),
            "movement_count": self.movement_count,
            "match_duration": round(match_duration, 2),
            "result": result,
        }

        self._write_row(row)

    # ── Per-frame / per-event logging ─────────────────────

    def log_attack(self):
        """Call once each time the player presses attack."""
        self.total_attacks += 1

    def log_distance(self, distance: float):
        """Call once per frame with the player-enemy distance."""
        self.total_distance += distance
        self.frame_count += 1

    def log_movement(self):
        """Call once per frame when the player is moving."""
        self.movement_count += 1

    # ── CSV helpers ───────────────────────────────────────

    def _write_row(self, row: dict):
        """Append one row to the CSV, creating headers if needed."""
        file_exists = os.path.isfile(CSV_FILE)

        with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)

            # Write header only when creating the file for the first time
            if not file_exists:
                writer.writeheader()

            writer.writerow(row)
