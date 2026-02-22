"""
combat_intent_system.py – Frame-by-frame intent evaluation for enemy AI.

Replaces cooldown-only logic with a continuous INTENT-BASED decision system.
Every frame, the enemy evaluates its desire to attack, defend, and reposition
based on real-time combat context.

Intent signals (all 0.0–1.0):
- attack_intent   : desire to strike right now
- aggression_level: overall offensive posture
- defensive_bias  : desire to block/dodge
- risk_tolerance  : willingness to trade hits

These signals are consumed by ai_core.py to produce actual FSM transitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # avoid circular imports


# ══════════════════════════════════════════════════════════
#  Configuration (tweak without touching logic)
# ══════════════════════════════════════════════════════════

@dataclass
class IntentConfig:
    """All tunable knobs for the intent system – no magic numbers."""

    # Distance-based intent curve
    optimal_range: float = 70.0       # ideal melee distance
    max_chase_range: float = 300.0    # beyond this, intent is 0
    close_range_bonus: float = 0.35   # bonus intent when very close

    # Stamina influence
    stamina_penalty_threshold: float = 0.30  # below this, reduce intent
    stamina_penalty_mult: float = 0.5        # how much to reduce

    # Recent-damage window (seconds)
    damage_window: float = 2.0

    # Base intent floor (enemy always has *some* desire to attack)
    base_intent: float = 0.15

    # Personality multipliers (keyed by personality name)
    personality_attack_mult: dict = field(default_factory=lambda: {
        "Berserker": 1.35,
        "Duelist":   1.20,
        "Coward":    0.60,
        "Trickster": 0.90,
        "Mage":      0.55,
    })
    personality_defense_mult: dict = field(default_factory=lambda: {
        "Berserker": 0.30,
        "Duelist":   0.80,
        "Coward":    1.20,
        "Trickster": 0.70,
        "Mage":      0.90,
    })


# ══════════════════════════════════════════════════════════
#  Damage Tracker (rolling window)
# ══════════════════════════════════════════════════════════

class _DamageWindow:
    """Track damage events within a sliding time window."""

    def __init__(self, window_sec: float = 2.0):
        self.window = window_sec
        self._events: list[tuple[float, int]] = []  # (timestamp, damage)

    def record(self, timestamp: float, damage: int):
        self._events.append((timestamp, damage))

    def total(self, now: float) -> int:
        cutoff = now - self.window
        self._events = [(t, d) for t, d in self._events if t >= cutoff]
        return sum(d for _, d in self._events)

    def clear(self):
        self._events.clear()


# ══════════════════════════════════════════════════════════
#  Combat Intent Evaluator
# ══════════════════════════════════════════════════════════

class CombatIntentSystem:
    """Evaluates frame-by-frame intent signals for enemy AI.

    Usage:
        intent = CombatIntentSystem(config, personality_name)
        intent.update(dt, now, distance, enemy_stamina_frac,
                      player_aggression, strategy_mode, enemy_hp_frac)
        if intent.attack_intent > 0.6:
            # enemy wants to attack
    """

    def __init__(self, config: IntentConfig | None = None,
                 personality_name: str = "Balanced"):
        self.cfg = config or IntentConfig()
        self.personality = personality_name

        # ── Live signals (0.0 – 1.0) ─────────────────────
        self.attack_intent: float = 0.0
        self.aggression_level: float = 0.5
        self.defensive_bias: float = 0.3
        self.risk_tolerance: float = 0.5

        # ── Damage tracking ───────────────────────────────
        self._dmg_dealt = _DamageWindow(self.cfg.damage_window)
        self._dmg_taken = _DamageWindow(self.cfg.damage_window)

        # ── Smoothing ─────────────────────────────────────
        self._smooth_attack: float = 0.0
        self._smooth_aggression: float = 0.5

    # ── Public API ────────────────────────────────────────

    def record_damage_dealt(self, now: float, amount: int):
        self._dmg_dealt.record(now, amount)

    def record_damage_taken(self, now: float, amount: int):
        self._dmg_taken.record(now, amount)

    def update(self, dt: float, now: float, distance: float,
               enemy_stamina_frac: float, player_aggression: float,
               strategy_mode: str, enemy_hp_frac: float):
        """Re-evaluate all intent signals. Call every frame."""

        cfg = self.cfg

        # ── 1. Distance-based attack intent ───────────────
        if distance <= cfg.optimal_range:
            dist_intent = 1.0
        elif distance < cfg.max_chase_range:
            dist_intent = 1.0 - ((distance - cfg.optimal_range)
                                  / (cfg.max_chase_range - cfg.optimal_range))
        else:
            dist_intent = 0.0

        # Close-range bonus: enemy *really* wants to swing when in face
        if distance < cfg.optimal_range * 0.6:
            dist_intent = min(1.0, dist_intent + cfg.close_range_bonus)

        # ── 2. Stamina influence ──────────────────────────
        stam_mult = 1.0
        if enemy_stamina_frac < cfg.stamina_penalty_threshold:
            stam_mult = cfg.stamina_penalty_mult + (
                (1.0 - cfg.stamina_penalty_mult)
                * (enemy_stamina_frac / cfg.stamina_penalty_threshold)
            )

        # ── 3. Player aggression reaction ─────────────────
        #   High player aggression → enemy defends more or counter-attacks
        aggr_reaction = 0.0
        if player_aggression > 0.6:
            aggr_reaction = (player_aggression - 0.6) * 0.5  # 0..0.2

        # ── 4. Strategy mode modifiers ────────────────────
        strat_attack_mod = 0.0
        strat_defense_mod = 0.0
        if strategy_mode == "aggressive":
            strat_attack_mod = 0.25
            strat_defense_mod = -0.15
        elif strategy_mode == "defensive":
            strat_attack_mod = -0.15
            strat_defense_mod = 0.25
        elif strategy_mode == "comeback":
            strat_attack_mod = 0.30
            strat_defense_mod = -0.10

        # ── 5. Personality multipliers ────────────────────
        atk_mult = cfg.personality_attack_mult.get(self.personality, 1.0)
        def_mult = cfg.personality_defense_mult.get(self.personality, 1.0)

        # ── 6. Damage exchange influence ──────────────────
        dealt = self._dmg_dealt.total(now)
        taken = self._dmg_taken.total(now)
        exchange_ratio = 0.0
        if dealt + taken > 0:
            exchange_ratio = (dealt - taken) / max(1, dealt + taken)
        # If enemy is winning the exchange → slightly more aggressive
        exchange_bonus = exchange_ratio * 0.15

        # ── 7. HP desperation boost ───────────────────────
        desperation_boost = 0.0
        if enemy_hp_frac < 0.35:
            desperation_boost = (0.35 - enemy_hp_frac) * 0.8  # up to ~0.28

        # ── COMPOSE SIGNALS ───────────────────────────────
        raw_attack = (
            cfg.base_intent
            + dist_intent * 0.50
            + exchange_bonus
            + desperation_boost
            + strat_attack_mod
        ) * atk_mult * stam_mult

        raw_aggression = (
            0.5
            + strat_attack_mod
            + desperation_boost * 0.6
            + exchange_bonus * 0.5
            - aggr_reaction * 0.3
        ) * atk_mult

        raw_defensive = (
            0.3
            + aggr_reaction
            + strat_defense_mod
        ) * def_mult

        # Risk tolerance: high HP + high stamina = more willing to trade
        raw_risk = (
            enemy_hp_frac * 0.4
            + enemy_stamina_frac * 0.3
            + desperation_boost * 0.5
            + strat_attack_mod * 0.3
        )

        # ── Clamp & smooth ────────────────────────────────
        target_attack = _clamp01(raw_attack)
        target_aggression = _clamp01(raw_aggression)

        smooth_rate = 5.0 * dt  # converge quickly (~5 frames)
        self._smooth_attack += (target_attack - self._smooth_attack) * smooth_rate
        self._smooth_aggression += (target_aggression - self._smooth_aggression) * smooth_rate

        self.attack_intent = _clamp01(self._smooth_attack)
        self.aggression_level = _clamp01(self._smooth_aggression)
        self.defensive_bias = _clamp01(raw_defensive)
        self.risk_tolerance = _clamp01(raw_risk)

    def reset(self):
        self.attack_intent = 0.0
        self.aggression_level = 0.5
        self.defensive_bias = 0.3
        self.risk_tolerance = 0.5
        self._dmg_dealt.clear()
        self._dmg_taken.clear()
        self._smooth_attack = 0.0
        self._smooth_aggression = 0.5


# ── Utility ───────────────────────────────────────────────

def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))
