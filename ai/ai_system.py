"""
ai_system.py – Personality-based AI with adaptive behavior.

Personality types:
- Berserker:  aggressive, rarely dodges, never retreats
- Duelist:    balanced, precise, reads opponent
- Coward:     evasive, runs, uses buffs defensively
- Trickster:  unpredictable, feints, abuses buffs
- Mage:       ranged caster, projectile-focused
- Tactician:  spacing and zoning, baits before punishing
- Aggressor:  high combo chaining, forward pressure
- Defender:   high block, counter-attack focused
- Predator:   aggressive when player HP is low, finisher mentality
- Adaptive:   shifts personality mid-match based on player behavior

Each personality influences:
- Attack frequency / aggression
- Dodge probability
- Retreat logic
- Buff usage
- Combo extension / risk tolerance

Integrates with the existing adaptive archetype system
(BehaviorAnalyzer, persistence, stats).
"""

from __future__ import annotations

import logging
import math
import random

logger = logging.getLogger(__name__)

import pygame
from settings import (
    SCREEN_WIDTH, SCREEN_HEIGHT, ATTACK_RANGE,
    ENEMY_QUICK_DAMAGE, ENEMY_QUICK_RANGE, ENEMY_QUICK_COOLDOWN,
    ENEMY_HEAVY_DAMAGE, ENEMY_HEAVY_RANGE, ENEMY_HEAVY_COOLDOWN,
    ENEMY_RETREAT_DURATION, ENEMY_RETREAT_SPEED,
    STAMINA_ATTACK_COST, STAMINA_HEAVY_ATTACK_COST,
    STAMINA_LOW_THRESHOLD,
    PERSONALITY_BERSERKER, PERSONALITY_DUELIST,
    PERSONALITY_COWARD, PERSONALITY_TRICKSTER,
    PERSONALITY_MAGE,
    PERSONALITY_TACTICIAN, PERSONALITY_AGGRESSOR,
    PERSONALITY_DEFENDER, PERSONALITY_PREDATOR, PERSONALITY_ADAPTIVE,
    DODGE_SPEED, DODGE_DURATION,
    PROJECTILE_COOLDOWN, PROJECTILE_DAMAGE, PROJECTILE_SPEED,
    DUELIST_DAMAGE_MULT, DUELIST_QUICK_COOLDOWN, DUELIST_HEAVY_COOLDOWN,
    DUELIST_ATTACK_DURATION, DUELIST_THINK_INTERVAL,
    DUELIST_COUNTER_WINDOW, DUELIST_COUNTER_DAMAGE,
    DUELIST_COMBO_WINDOW, DUELIST_COMBO_DAMAGE,
    DUELIST_LUNGE_IMPULSE, DUELIST_CHASE_SPEED_MULT,
    SELECTION_TEMPERATURE, SELECTION_MIN_PLAYS,
    SELECTION_RECENCY_PENALTY, SELECTION_EPSILON,
)
from ai.persistence import load_archetype_stats, get_win_rate


# ══════════════════════════════════════════════════════════
#  Personality Definition
# ══════════════════════════════════════════════════════════

class Personality:
    """Encapsulates AI personality parameters."""

    def __init__(self, name: str, params: dict):
        self.name = name
        self.attack_frequency: float = params.get("attack_frequency", 1.0)
        self.dodge_probability: float = params.get("dodge_probability", 0.2)
        self.retreat_tendency: float = params.get("retreat_tendency", 0.3)
        self.aggression: float = params.get("aggression", 0.5)
        self.buff_use_chance: float = params.get("buff_use_chance", 0.3)
        self.uses_projectiles: bool = params.get("uses_projectiles", False)
        # Extended attributes for new archetypes
        self.combo_extension: float = params.get("combo_extension", 0.30)
        self.risk_tolerance: float = params.get("risk_tolerance", 0.50)


PERSONALITIES: dict[str, Personality] = {
    "Berserker":  Personality("Berserker",  PERSONALITY_BERSERKER),
    "Duelist":    Personality("Duelist",     PERSONALITY_DUELIST),
    "Coward":     Personality("Coward",      PERSONALITY_COWARD),
    "Trickster":  Personality("Trickster",   PERSONALITY_TRICKSTER),
    "Mage":       Personality("Mage",        PERSONALITY_MAGE),
    "Tactician":  Personality("Tactician",   PERSONALITY_TACTICIAN),
    "Aggressor":  Personality("Aggressor",   PERSONALITY_AGGRESSOR),
    "Defender":   Personality("Defender",    PERSONALITY_DEFENDER),
    "Predator":   Personality("Predator",    PERSONALITY_PREDATOR),
    "Adaptive":   Personality("Adaptive",    PERSONALITY_ADAPTIVE),
}

# Map player styles from BehaviorAnalyzer to personality pools.
# Every pool contains enough variety that no single personality
# can dominate through pool membership alone.
STYLE_TO_PERSONALITIES: dict[str, list[str]] = {
    "Aggressive": ["Duelist", "Coward", "Mage", "Defender", "Tactician"],
    "Defensive":  ["Berserker", "Trickster", "Mage", "Aggressor", "Predator"],
    "Balanced":   ["Duelist", "Trickster", "Tactician", "Adaptive", "Predator"],
    "Evasive":    ["Aggressor", "Predator", "Berserker", "Tactician", "Mage"],
    "Unknown":    list(PERSONALITIES.keys()),
}

# Last personality used (for recency penalty)
_last_selected: str | None = None

# Cached softmax probabilities from the most recent selection.
# Dict mapping personality name → probability.  Read-only for debug/overlay.
last_softmax_probs: dict[str, float] = {}

# ══════════════════════════════════════════════════════════
#  Duelist Behavior Module
# ══════════════════════════════════════════════════════════

class DuelistBehavior:
    """Encapsulates Duelist-specific reactive combat mechanics.

    Features:
    - **Counter system**: After successfully blocking a player attack,
      the Duelist has a short window to fire a guaranteed counter-strike.
    - **Combo system**: When the first hit lands, a fast follow-up
      second strike is queued automatically.
    - **Reactive punish**: If the player whiffs an attack nearby,
      the Duelist immediately punishes.
    - **Forward lunge**: Attacks include a forward impulse for
      aggressive gap-closing.
    """

    def __init__(self):
        # Counter system
        self._counter_window_timer: float = 0.0   # counts down after block
        self._counter_ready: bool = False

        # Combo system
        self._combo_timer: float = 0.0    # counts down between combo hits
        self._combo_queued: bool = False   # True when 2nd hit is pending
        self._combo_damage: int = 0       # damage for the queued 2nd hit

        # Reactive punish tracking
        self._player_was_attacking: bool = False
        self._punish_ready: bool = False

    def update(self, dt: float, enemy, player, dist: float):
        """Tick timers and detect reactive triggers. Call every frame."""
        # ── Counter window ────────────────────────────────
        if self._counter_window_timer > 0:
            self._counter_window_timer -= dt
            if self._counter_window_timer <= 0:
                self._counter_ready = False

        # ── Combo follow-up timer ─────────────────────────
        if self._combo_timer > 0:
            self._combo_timer -= dt

        # ── Reactive punish detection ─────────────────────
        # Player was attacking last frame but no longer → whiffed
        if self._player_was_attacking and not player.is_attacking:
            # Player's attack animation ended; if we're close, punish
            if dist < ATTACK_RANGE * 1.6:
                self._punish_ready = True
        else:
            self._punish_ready = False
        self._player_was_attacking = player.is_attacking

    def on_block_success(self):
        """Called when the Duelist blocks a player attack."""
        self._counter_window_timer = DUELIST_COUNTER_WINDOW
        self._counter_ready = True
        logger.info("Duelist counter window opened")

    def consume_counter(self) -> int:
        """If a counter-strike is ready, consume and return counter damage."""
        if self._counter_ready:
            self._counter_ready = False
            self._counter_window_timer = 0.0
            logger.info("Duelist counter-strike!")
            return DUELIST_COUNTER_DAMAGE
        return 0

    def on_hit_landed(self):
        """Called when the Duelist's first hit connects."""
        self._combo_timer = DUELIST_COMBO_WINDOW
        self._combo_queued = True
        self._combo_damage = DUELIST_COMBO_DAMAGE
        logger.info("Duelist combo follow-up queued")

    def consume_combo(self) -> int:
        """If a combo follow-up is ready, consume and return damage."""
        if self._combo_queued and self._combo_timer <= 0:
            self._combo_queued = False
            dmg = self._combo_damage
            self._combo_damage = 0
            logger.info("Duelist combo hit! dmg=%d", dmg)
            return dmg
        return 0

    @property
    def wants_punish(self) -> bool:
        """True if the Duelist detected a player whiff and wants to punish."""
        return self._punish_ready

    @property
    def has_combo_pending(self) -> bool:
        return self._combo_queued

    def reset(self):
        """Reset all combat state (e.g. on new match)."""
        self._counter_window_timer = 0.0
        self._counter_ready = False
        self._combo_timer = 0.0
        self._combo_queued = False
        self._combo_damage = 0
        self._player_was_attacking = False
        self._punish_ready = False


# ══════════════════════════════════════════════════════════
#  Personality Selection (integrates with BehaviorAnalyzer)
# ══════════════════════════════════════════════════════════

def _softmax_scores(scores: list[float], temperature: float) -> list[float]:
    """Convert raw scores into softmax probabilities.

    Uses temperature scaling – lower temperature → more greedy,
    higher temperature → more uniform.
    """
    if temperature <= 0:
        temperature = 0.01
    scaled = [s / temperature for s in scores]
    max_s = max(scaled)
    exps = [math.exp(s - max_s) for s in scaled]  # shift for numerical stability
    total = sum(exps)
    return [e / total for e in exps]


def select_personality(player_style: str) -> Personality:
    """Select enemy personality using softmax + UCB exploration.

    Algorithm:
    1. Hard epsilon exploration – with probability SELECTION_EPSILON,
       pick a uniformly random personality from the pool.
    2. Otherwise compute an *adjusted score* for each personality:
       - Base = win rate from persistence data
       - UCB bonus for under-played personalities (< SELECTION_MIN_PLAYS)
       - Recency penalty if this personality was just used
    3. Feed adjusted scores into a softmax with SELECTION_TEMPERATURE
       and sample probabilistically.

    This prevents any single personality from dominating while still
    favoring higher-performing ones.
    """
    global _last_selected

    pool_names = STYLE_TO_PERSONALITIES.get(player_style,
                                             list(PERSONALITIES.keys()))

    # Hard epsilon exploration
    if random.random() < SELECTION_EPSILON:
        name = random.choice(pool_names)
        logger.info("Personality EXPLORE (epsilon) → %s", name)
        _last_selected = name
        return PERSONALITIES[name]

    # Load persistent performance data
    data = load_archetype_stats()

    # Compute total matches across all personalities
    total_matches = sum(
        data.get(n, {}).get("matches", 0) for n in pool_names
    )

    # Build adjusted scores for each personality in the pool
    scores: list[float] = []
    for name in pool_names:
        entry = data.get(name, {})
        matches = entry.get("matches", 0)
        wr = get_win_rate(name, data)  # wins / max(1, matches)

        # UCB exploration bonus for under-played personalities
        if matches < SELECTION_MIN_PLAYS:
            # Give a generous bonus so it gets explored
            ucb_bonus = 0.5 * math.sqrt(
                math.log(max(total_matches, 1) + 1) / max(matches, 1)
            )
        else:
            ucb_bonus = 0.0

        # Recency penalty – discourage picking the same personality twice
        recency = SELECTION_RECENCY_PENALTY if name == _last_selected else 0.0

        score = wr + ucb_bonus - recency
        scores.append(score)

    # Softmax probabilistic selection
    probs = _softmax_scores(scores, SELECTION_TEMPERATURE)

    # Weighted random selection
    r = random.random()
    cumulative = 0.0
    chosen_name = pool_names[-1]
    for name, prob in zip(pool_names, probs):
        cumulative += prob
        if r <= cumulative:
            chosen_name = name
            break

    _last_selected = chosen_name

    # Persist softmax probs for debug overlay
    global last_softmax_probs
    last_softmax_probs = {n: p for n, p in zip(pool_names, probs)}

    logger.info(
        "Personality SOFTMAX → %s (scores=%s, probs=%s)",
        chosen_name,
        {n: f"{s:.3f}" for n, s in zip(pool_names, scores)},
        {n: f"{p:.3f}" for n, p in zip(pool_names, probs)},
    )
    return PERSONALITIES[chosen_name]
