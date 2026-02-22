"""
stats.py  –  Phase 6: Per-match statistics tracking.

MatchStats collects combat events during a single match and
computes an aggression score every 10 seconds.  At match end
it prints a formatted summary and displays an aggression-trend
line graph via matplotlib.

No changes to FSM logic or combat timing.
"""

import logging
import time

logger = logging.getLogger(__name__)

import matplotlib
matplotlib.use("Agg")  # non-interactive backend so the plot doesn't block pygame
import matplotlib.pyplot as plt

# Aggression snapshot interval (seconds)
_AGGRESSION_INTERVAL = 10.0


class MatchStats:
    """Tracks events for one match and produces end-of-match reports.

    Attributes tracked:
        player_style        – str
        enemy_archetype     – str
        damage_dealt        – int  (damage the enemy dealt to the player)
        damage_taken        – int  (damage the enemy received from the player)
        quick_attacks       – int
        heavy_attacks       – int
        combos              – int
        retreats            – int
        match_duration      – float (seconds, set at end_match)
        forward_moves       – int  (frames where enemy moved toward player)
        aggression_history  – list[int]
    """

    def __init__(self, player_style: str, enemy_archetype: str):
        self.player_style: str = player_style
        self.enemy_archetype: str = enemy_archetype

        # Cumulative counters
        self.damage_dealt: int = 0       # enemy → player
        self.damage_taken: int = 0       # player → enemy
        self.quick_attacks: int = 0
        self.heavy_attacks: int = 0
        self.combos: int = 0
        self.retreats: int = 0
        self.forward_moves: int = 0      # frames chasing player

        # Timing
        self._start_time: float = time.time()
        self.match_duration: float = 0.0

        # Aggression snapshots
        self.aggression_history: list[int] = []
        self._last_aggression_time: float = self._start_time

    # ===========================================================
    #  Per-frame / per-event recorders
    # ===========================================================

    def record_enemy_attack(self, attack_type: str, damage: int, was_combo: bool):
        """Call after the enemy commits to a swing (hit or miss).

        Parameters
        ----------
        attack_type : "quick" or "heavy"
        damage      : actual damage applied (0 on miss)
        was_combo   : True if cooldown was halved by combo logic
        """
        if attack_type == "quick":
            self.quick_attacks += 1
        else:
            self.heavy_attacks += 1

        self.damage_dealt += damage

        if was_combo:
            self.combos += 1

    def record_enemy_retreat(self):
        """Call when the enemy enters the retreat state."""
        self.retreats += 1

    def record_player_damage(self, damage: int):
        """Call when the player lands a hit on the enemy."""
        self.damage_taken += damage

    def record_forward_move(self):
        """Call once per frame when the enemy is in chase state."""
        self.forward_moves += 1

    def tick(self):
        """Call once per frame.  Snapshots aggression when interval elapses."""
        now = time.time()
        if now - self._last_aggression_time >= _AGGRESSION_INTERVAL:
            score = self.quick_attacks + self.forward_moves - self.retreats
            self.aggression_history.append(score)
            self._last_aggression_time = now

    # ===========================================================
    #  End-of-match
    # ===========================================================

    def end_match(self, result: str):
        """Finalise stats, print summary, and show aggression graph.

        Parameters
        ----------
        result : "win" (player won) or "lose" (enemy won)
        """
        self.match_duration = time.time() - self._start_time

        # Take a final aggression snapshot so the graph is never empty
        final_score = self.quick_attacks + self.forward_moves - self.retreats
        self.aggression_history.append(final_score)

        self._print_summary(result)
        self._plot_aggression()

    # ===========================================================
    #  Reports
    # ===========================================================

    def _print_summary(self, result: str):
        """Print a clean formatted match summary to stdout."""
        print("\n" + "=" * 52)
        print("  MATCH SUMMARY")
        print("=" * 52)
        print(f"  Result           : {'Player Wins' if result == 'win' else 'Enemy Wins'}")
        print(f"  Player Style     : {self.player_style}")
        print(f"  Enemy Archetype  : {self.enemy_archetype}")
        print(f"  Match Duration   : {self.match_duration:.1f}s")
        print("-" * 52)
        print(f"  Damage Dealt (enemy→player) : {self.damage_dealt}")
        print(f"  Damage Taken (player→enemy) : {self.damage_taken}")
        print(f"  Quick Attacks    : {self.quick_attacks}")
        print(f"  Heavy Attacks    : {self.heavy_attacks}")
        print(f"  Combos           : {self.combos}")
        print(f"  Retreats         : {self.retreats}")
        print("-" * 52)
        print(f"  Aggression snapshots ({len(self.aggression_history)}): "
              f"{self.aggression_history}")
        print("=" * 52 + "\n")

    def _plot_aggression(self):
        """Save a simple line graph of aggression_history to disk."""
        if not self.aggression_history:
            return

        x = [i * _AGGRESSION_INTERVAL for i in range(len(self.aggression_history))]
        y = self.aggression_history

        fig, ax = plt.subplots()
        ax.plot(x, y, marker="o")
        ax.set_xlabel("Time (seconds)")
        ax.set_ylabel("Aggression Score")
        ax.set_title(f"Aggression Trend  —  {self.enemy_archetype} vs {self.player_style}")
        ax.grid(True)

        filename = "aggression_trend.png"
        fig.savefig(filename, dpi=100, bbox_inches="tight")
        plt.close(fig)
        logger.info("Aggression graph saved to %s", filename)

    # ===========================================================
    #  Data accessors (used by persistence layer)
    # ===========================================================

    def as_dict(self) -> dict:
        """Return a plain dict snapshot (useful for JSON serialisation)."""
        return {
            "player_style":       self.player_style,
            "enemy_archetype":    self.enemy_archetype,
            "damage_dealt":       self.damage_dealt,
            "damage_taken":       self.damage_taken,
            "quick_attacks":      self.quick_attacks,
            "heavy_attacks":      self.heavy_attacks,
            "combos":             self.combos,
            "retreats":           self.retreats,
            "match_duration":     round(self.match_duration, 2),
            "aggression_history": list(self.aggression_history),
        }
