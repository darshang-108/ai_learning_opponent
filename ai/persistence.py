"""
persistence.py  –  Phase 6: Persistent archetype performance tracking.

Loads / saves archetype win-rate data from 'archetype_stats.json'
so the enemy AI can use epsilon-greedy selection across sessions.

Kept separate from enemy.py to maintain clean architecture.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

# JSON file lives in the project root
_JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "archetype_stats.json",
)

# Canonical list of all archetypes (must match ai_system.py PERSONALITIES keys)
_ALL_ARCHETYPES = [
    "Berserker", "Duelist", "Coward", "Trickster", "Mage",
    "Tactician", "Aggressor", "Defender", "Predator", "Adaptive",
]


def _default_entry() -> dict:
    """Return a fresh stats entry for one archetype."""
    return {
        "matches": 0,
        "wins": 0,
        "avg_damage": 0.0,
        "avg_survival_time": 0.0,
    }


def _default_data() -> dict:
    """Return a full default stats dict covering every archetype."""
    return {name: _default_entry() for name in _ALL_ARCHETYPES}


# ==============================================================
#  Public API
# ==============================================================

def load_archetype_stats() -> dict:
    """Load archetype stats from disk.

    If the file does not exist or is corrupt, a fresh default
    structure is returned (and written to disk for next time).
    """
    if not os.path.isfile(_JSON_PATH):
        data = _default_data()
        save_archetype_stats(data)
        return data

    try:
        with open(_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        data = _default_data()
        save_archetype_stats(data)
        return data

    # Ensure every archetype has an entry (forward-compat)
    changed = False
    for name in _ALL_ARCHETYPES:
        if name not in data:
            data[name] = _default_entry()
            changed = True
    if changed:
        save_archetype_stats(data)

    return data


def save_archetype_stats(data: dict) -> None:
    """Write the full archetype stats dict to disk."""
    with open(_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def update_after_match(
    archetype_name: str,
    enemy_won: bool,
    damage_dealt: int,
    match_duration: float,
) -> None:
    """Update persistent stats for *archetype_name* after a match.

    Parameters
    ----------
    archetype_name  : which archetype the enemy used
    enemy_won       : True if the enemy won the match
    damage_dealt    : damage the enemy dealt to the player this match
    match_duration  : length of the match in seconds
    """
    data = load_archetype_stats()
    entry = data.get(archetype_name, _default_entry())

    n = entry["matches"]

    # Running averages:  new_avg = old_avg + (value - old_avg) / (n + 1)
    entry["avg_damage"] = (
        entry["avg_damage"] + (damage_dealt - entry["avg_damage"]) / (n + 1)
    )
    entry["avg_survival_time"] = (
        entry["avg_survival_time"]
        + (match_duration - entry["avg_survival_time"]) / (n + 1)
    )

    entry["matches"] = n + 1
    if enemy_won:
        entry["wins"] += 1

    data[archetype_name] = entry
    save_archetype_stats(data)

    logger.info(
        "Updated %s: matches=%d, wins=%d, avg_dmg=%.1f, avg_surv=%.1fs",
        archetype_name, entry['matches'], entry['wins'],
        entry['avg_damage'], entry['avg_survival_time'],
    )


def get_win_rate(archetype_name: str, data: dict | None = None) -> float:
    """Return win rate for *archetype_name* (0.0 if no data).

    Avoids division by zero.
    """
    if data is None:
        data = load_archetype_stats()
    entry = data.get(archetype_name, _default_entry())
    return entry["wins"] / max(1, entry["matches"])
