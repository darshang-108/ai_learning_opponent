"""
aggression_system.py – Human-like pressure, match-flow adaptation, and
dynamic tempo control.

Responsibilities:
- Close distance aggressively when appropriate
- Never stand idle in attack range
- Strafe / micro-move during cooldown
- Chain combos on hit-confirm
- Dynamic attack cooldown based on aggression mode
- Match flow tracking (last N seconds) for organic scaling
- Personality tempo modes (Aggressive / Defensive / Balanced / Comeback)
- Punish system for missed attacks and spam

All state is per-enemy-instance; no globals.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


# ══════════════════════════════════════════════════════════
#  Configuration
# ══════════════════════════════════════════════════════════

@dataclass
class AggressionConfig:
    """Tunable knobs for the aggression / pressure system."""

    # Cooldown ranges (seconds)
    base_cooldown_min: float = 0.6
    base_cooldown_max: float = 0.8
    aggressive_cooldown_min: float = 0.3
    aggressive_cooldown_max: float = 0.5
    comeback_cooldown_min: float = 0.25
    comeback_cooldown_max: float = 0.45

    # Strafe / micro-move
    strafe_speed: float = 2.5         # pixels/frame at 60fps
    strafe_change_interval: float = 0.4  # seconds between direction changes

    # Combo chaining
    combo_chain_chance_base: float = 0.35
    combo_chain_chance_aggressive: float = 0.55
    combo_chain_cooldown: float = 0.18   # seconds between combo hits

    # Pressure chase
    chase_speed_mult_aggressive: float = 1.40
    chase_speed_mult_comeback: float = 1.55
    chase_speed_mult_defensive: float = 0.85

    # Match flow tracking
    match_flow_window: float = 10.0    # Rolling window in seconds

    # Punish system
    punish_reaction_time: float = 0.08  # seconds (near-instant)
    punish_window_after_whiff: float = 0.25  # seconds the window stays open
    spam_counter_threshold: int = 4    # attacks in 2s = spam


# ══════════════════════════════════════════════════════════
#  Match Flow Tracker
# ══════════════════════════════════════════════════════════

class MatchFlowTracker:
    """Tracks damage dealt/taken in a rolling time window to determine
    who is winning the fight moment-to-moment."""

    def __init__(self, window: float = 10.0):
        self.window = window
        self._player_dmg: list[tuple[float, int]] = []
        self._enemy_dmg: list[tuple[float, int]] = []

    def record_player_damage(self, now: float, amount: int):
        self._player_dmg.append((now, amount))

    def record_enemy_damage(self, now: float, amount: int):
        self._enemy_dmg.append((now, amount))

    def _prune(self, now: float):
        cutoff = now - self.window
        self._player_dmg = [(t, d) for t, d in self._player_dmg if t >= cutoff]
        self._enemy_dmg = [(t, d) for t, d in self._enemy_dmg if t >= cutoff]

    def player_damage_total(self, now: float) -> int:
        self._prune(now)
        return sum(d for _, d in self._player_dmg)

    def enemy_damage_total(self, now: float) -> int:
        self._prune(now)
        return sum(d for _, d in self._enemy_dmg)

    def flow_ratio(self, now: float) -> float:
        """Returns -1.0 (enemy losing badly) to +1.0 (enemy dominating).
        0.0 = even."""
        self._prune(now)
        p = sum(d for _, d in self._player_dmg)
        e = sum(d for _, d in self._enemy_dmg)
        total = p + e
        if total == 0:
            return 0.0
        return (e - p) / total  # positive = enemy winning

    def clear(self):
        self._player_dmg.clear()
        self._enemy_dmg.clear()


# ══════════════════════════════════════════════════════════
#  Punish Detector
# ══════════════════════════════════════════════════════════

class PunishDetector:
    """Detects punishable moments: player whiffs or spams attacks."""

    def __init__(self, cfg: AggressionConfig):
        self.cfg = cfg
        self._player_was_attacking: bool = False
        self._whiff_timer: float = 0.0
        self.punish_ready: bool = False

        # Spam tracking
        self._recent_player_attacks: list[float] = []
        self.player_is_spamming: bool = False

    def update(self, dt: float, now: float, player_is_attacking: bool,
               distance: float, attack_range: float):
        """Call every frame."""
        # ── Whiff detection ───────────────────────────────
        if self._player_was_attacking and not player_is_attacking:
            # Player attack just ended
            if distance < attack_range * 1.8:
                self._whiff_timer = self.cfg.punish_window_after_whiff
                self.punish_ready = True
        self._player_was_attacking = player_is_attacking

        if self._whiff_timer > 0:
            self._whiff_timer -= dt
            if self._whiff_timer <= 0:
                self.punish_ready = False

        # ── Spam tracking ─────────────────────────────────
        if player_is_attacking and not self._player_was_attacking:
            self._recent_player_attacks.append(now)
        # Prune old
        self._recent_player_attacks = [
            t for t in self._recent_player_attacks if now - t < 2.0
        ]
        self.player_is_spamming = (
            len(self._recent_player_attacks) >= self.cfg.spam_counter_threshold
        )

    def reset(self):
        self._player_was_attacking = False
        self._whiff_timer = 0.0
        self.punish_ready = False
        self._recent_player_attacks.clear()
        self.player_is_spamming = False


# ══════════════════════════════════════════════════════════
#  Aggression System (main class)
# ══════════════════════════════════════════════════════════

class AggressionSystem:
    """Drives human-like pressure behavior for enemy AI.

    Provides:
    - get_dynamic_cooldown()  → seconds until next attack allowed
    - get_chase_speed_mult()  → multiplier on chase speed
    - get_combo_chance()      → probability of chaining a combo
    - get_strafe_direction()  → -1 / 0 / +1 for micro-movement
    - tempo_mode              → current mode string
    - punish                  → PunishDetector instance
    - flow                    → MatchFlowTracker instance
    """

    def __init__(self, config: AggressionConfig | None = None):
        self.cfg = config or AggressionConfig()

        # Sub-systems
        self.flow = MatchFlowTracker(self.cfg.match_flow_window)
        self.punish = PunishDetector(self.cfg)

        # ── Tempo mode ─────────────────────────────────
        self.tempo_mode: str = "balanced"  # aggressive | defensive | balanced | comeback

        # ── Strafe state ────────────────────────────────
        self._strafe_dir: int = 0          # -1, 0, +1
        self._strafe_timer: float = 0.0

        # ── Combo state ─────────────────────────────────
        self._combo_chain_timer: float = 0.0
        self.combo_pending: bool = False

    # ── Per-frame update ──────────────────────────────────

    def update(self, dt: float, now: float, enemy_hp_frac: float,
               attack_intent: float, aggression_level: float,
               player_is_attacking: bool, distance: float,
               attack_range: float):
        """Call every frame to update tempo mode, punish detection, strafe."""

        # ── Tempo mode selection ──────────────────────────
        flow_ratio = self.flow.flow_ratio(now)

        if enemy_hp_frac < 0.35:
            self.tempo_mode = "comeback"
        elif flow_ratio < -0.3:
            # Enemy is losing → escalate aggression gradually
            self.tempo_mode = "aggressive"
        elif flow_ratio > 0.3:
            # Enemy is winning → slightly defensive
            self.tempo_mode = "defensive"
        else:
            # Even fight → follow intent
            if aggression_level > 0.65:
                self.tempo_mode = "aggressive"
            elif aggression_level < 0.35:
                self.tempo_mode = "defensive"
            else:
                self.tempo_mode = "balanced"

        # ── Punish detector ───────────────────────────────
        self.punish.update(dt, now, player_is_attacking, distance, attack_range)

        # ── Strafe timer ──────────────────────────────────
        self._strafe_timer -= dt
        if self._strafe_timer <= 0:
            self._strafe_dir = random.choice([-1, 0, 1])
            self._strafe_timer = self.cfg.strafe_change_interval + random.uniform(-0.1, 0.1)

        # ── Combo chain timer ─────────────────────────────
        if self._combo_chain_timer > 0:
            self._combo_chain_timer -= dt
            if self._combo_chain_timer <= 0:
                self.combo_pending = True

    # ── Queries ───────────────────────────────────────────

    def get_dynamic_cooldown(self) -> float:
        """Return the attack cooldown in seconds based on current tempo."""
        cfg = self.cfg
        if self.tempo_mode == "aggressive":
            return random.uniform(cfg.aggressive_cooldown_min,
                                  cfg.aggressive_cooldown_max)
        elif self.tempo_mode == "comeback":
            return random.uniform(cfg.comeback_cooldown_min,
                                  cfg.comeback_cooldown_max)
        elif self.tempo_mode == "defensive":
            return random.uniform(cfg.base_cooldown_min,
                                  cfg.base_cooldown_max) * 1.15
        else:
            return random.uniform(cfg.base_cooldown_min,
                                  cfg.base_cooldown_max)

    def get_chase_speed_mult(self) -> float:
        """Return speed multiplier for chasing the player."""
        cfg = self.cfg
        if self.tempo_mode == "aggressive":
            return cfg.chase_speed_mult_aggressive
        elif self.tempo_mode == "comeback":
            return cfg.chase_speed_mult_comeback
        elif self.tempo_mode == "defensive":
            return cfg.chase_speed_mult_defensive
        return 1.0

    def get_combo_chance(self) -> float:
        """Probability of chaining a combo after a hit."""
        cfg = self.cfg
        if self.tempo_mode in ("aggressive", "comeback"):
            return cfg.combo_chain_chance_aggressive
        return cfg.combo_chain_chance_base

    def get_strafe_direction(self) -> int:
        """Return micro-movement direction: -1, 0, or +1."""
        return self._strafe_dir

    def queue_combo_followup(self):
        """Called when a hit confirms – queue a combo follow-up."""
        self._combo_chain_timer = self.cfg.combo_chain_cooldown
        self.combo_pending = False

    def consume_combo(self) -> bool:
        """Returns True if a combo follow-up is ready to fire."""
        if self.combo_pending:
            self.combo_pending = False
            return True
        return False

    def reset(self):
        self.flow.clear()
        self.punish.reset()
        self.tempo_mode = "balanced"
        self._strafe_dir = 0
        self._strafe_timer = 0.0
        self._combo_chain_timer = 0.0
        self.combo_pending = False
