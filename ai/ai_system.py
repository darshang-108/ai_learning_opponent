"""
ai_system.py – Personality-based AI with adaptive behavior.

Personality types:
- Berserker: aggressive, rarely dodges, never retreats
- Duelist:   balanced, precise, reads opponent
- Coward:    evasive, runs, uses buffs defensively
- Trickster: unpredictable, feints, abuses buffs

Each personality influences:
- Attack frequency
- Dodge probability
- Retreat logic
- Buff usage

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
    DODGE_SPEED, DODGE_DURATION,
    PROJECTILE_COOLDOWN, PROJECTILE_DAMAGE, PROJECTILE_SPEED,
    DUELIST_DAMAGE_MULT, DUELIST_QUICK_COOLDOWN, DUELIST_HEAVY_COOLDOWN,
    DUELIST_ATTACK_DURATION, DUELIST_THINK_INTERVAL,
    DUELIST_COUNTER_WINDOW, DUELIST_COUNTER_DAMAGE,
    DUELIST_COMBO_WINDOW, DUELIST_COMBO_DAMAGE,
    DUELIST_LUNGE_IMPULSE, DUELIST_CHASE_SPEED_MULT,
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


PERSONALITIES: dict[str, Personality] = {
    "Berserker": Personality("Berserker", PERSONALITY_BERSERKER),
    "Duelist":   Personality("Duelist",   PERSONALITY_DUELIST),
    "Coward":    Personality("Coward",    PERSONALITY_COWARD),
    "Trickster": Personality("Trickster", PERSONALITY_TRICKSTER),
    "Mage":      Personality("Mage",      PERSONALITY_MAGE),
}

# Map player styles from BehaviorAnalyzer to personality pools
STYLE_TO_PERSONALITIES: dict[str, list[str]] = {
    "Aggressive": ["Duelist", "Coward", "Mage"],    # counter aggression
    "Defensive":  ["Berserker", "Trickster", "Mage"],  # break defense
    "Balanced":   ["Duelist", "Trickster", "Mage"],  # versatile
    "Unknown":    ["Berserker", "Duelist", "Coward", "Trickster", "Mage"],
}

_EPSILON = 0.2  # exploration rate for personality selection


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

def select_personality(player_style: str) -> Personality:
    """Select enemy personality based on detected player style.
    Uses epsilon-greedy with persistence data.
    """
    pool_names = STYLE_TO_PERSONALITIES.get(player_style,
                                             list(PERSONALITIES.keys()))

    # Explore
    if random.random() < _EPSILON:
        name = random.choice(pool_names)
        logger.info("Personality EXPLORE → %s", name)
        return PERSONALITIES[name]

    # Exploit: pick best win-rate personality from pool
    data = load_archetype_stats()
    best_name = pool_names[0]
    best_rate = -1.0
    for name in pool_names:
        rate = get_win_rate(name, data)
        if rate > best_rate:
            best_rate = rate
            best_name = name

    if best_rate <= 0:
        name = random.choice(pool_names)
        logger.info("Personality no-data fallback → %s", name)
        return PERSONALITIES[name]

    logger.info("Personality EXPLOIT → %s (wr=%.2f)", best_name, best_rate)
    return PERSONALITIES[best_name]
