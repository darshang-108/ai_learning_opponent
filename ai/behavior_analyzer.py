"""
behavior_analyzer.py  –  Phase 3: Player behavior analysis.

Reads the match history from 'player_data.csv' (written by DataLogger),
analyzes the most recent matches, and classifies the player's style.

Uses only the built-in `csv` module (no pandas / no ML).
"""

import csv
import logging
import os

logger = logging.getLogger(__name__)

# Path to the CSV file (same location DataLogger writes to)
CSV_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "player_data.csv")

# How many recent matches to consider
LOOKBACK = 3


class BehaviorAnalyzer:
    """Analyzes recent match data and classifies the player's style."""

    def detect_player_style(self) -> str:
        """Return one of: 'Aggressive', 'Defensive', 'Balanced', 'Unknown'.

        Classification rules (based on averages of the last 3 matches):
          Aggressive  –  avg_attacks >= 12  OR  avg_distance < 140
          Defensive   –  avg_attacks < 12   AND avg_distance >= 140
          Balanced    –  middle ground (fallback)
          Unknown     –  no data available
        """
        matches = self._read_recent_matches()

        if not matches:
            return "Unknown"

        # Compute averages across the selected matches
        avg_attacks  = sum(m["total_attacks"]  for m in matches) / len(matches)
        avg_distance = sum(m["avg_distance"]   for m in matches) / len(matches)
        avg_movement = sum(m["movement_count"] for m in matches) / len(matches)

        logger.debug(
            "Last %d matches: avg_attacks=%.1f, avg_distance=%.1f, avg_movement=%.1f",
            len(matches), avg_attacks, avg_distance, avg_movement,
        )

        # Classify — thresholds tuned to real gameplay data
        if avg_attacks >= 12 and avg_distance < 140:
            style = "Aggressive"
        elif avg_attacks < 12 and avg_distance >= 140:
            style = "Defensive"
        else:
            style = "Balanced"

        return style

    # ── Internal helpers ──────────────────────────────────

    def _read_recent_matches(self) -> list[dict]:
        """Read the CSV and return the last LOOKBACK matches as dicts
        with numeric values already converted.

        Returns an empty list if the file is missing or has no rows.
        """
        if not os.path.isfile(CSV_FILE):
            return []

        try:
            with open(CSV_FILE, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except (OSError, csv.Error):
            return []

        if not rows:
            return []

        # Take the last N matches
        recent = rows[-LOOKBACK:]

        # Convert string values to numbers
        parsed = []
        for row in recent:
            try:
                parsed.append({
                    "match_id":       int(row["match_id"]),
                    "total_attacks":  int(row["total_attacks"]),
                    "avg_distance":   float(row["avg_distance"]),
                    "movement_count": int(row["movement_count"]),
                    "match_duration": float(row["match_duration"]),
                    "result":         row["result"],
                })
            except (KeyError, ValueError):
                continue  # skip malformed rows

        return parsed
