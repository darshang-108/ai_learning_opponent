"""
ability_system.py – Modular role-based ability system.

Each player role has a unique ability activated via a single key (Q).
Abilities are self-contained objects with cooldown, duration, stamina
cost, and per-frame update logic.  The system is decoupled from both
the combat system and the drawing loop.

Architecture
────────────
Ability (abstract base)
 ├── MageAbility        – magic projectile
 ├── BerserkerAbility   – temporary damage boost
 ├── GuardianAbility    – temporary damage-reduction shield
 ├── AssassinAbility    – quick dash/blink with invulnerability
 ├── TacticianAbility   – minor all-stat boost
 └── AdaptiveAbility    – scaling stat bonus that grows over time

Factory:
    create_ability(role_name) → Ability | None
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

import pygame
from settings import (
    PROJECTILE_SPEED,
    PROJECTILE_DAMAGE,
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    DODGE_SPEED,
)

if TYPE_CHECKING:
    from systems.projectile_system import ProjectileSystem

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════
#  Abstract Base
# ══════════════════════════════════════════════════════════

class Ability:
    """Base class for all role abilities.

    Subclasses override ``_on_activate`` (and optionally ``_on_expire``
    / ``_on_tick``) to define behaviour.
    """

    name: str = "Ability"
    cooldown: float = 5.0          # seconds between uses
    duration: float = 0.0          # 0 = instant, >0 = sustained
    stamina_cost: float = 20.0     # stamina drained on activation
    description: str = ""

    def __init__(self) -> None:
        self._cooldown_timer: float = 0.0   # time remaining until ready
        self._active_timer: float = 0.0     # time remaining on active effect
        self._is_active: bool = False

    # ── Queries ───────────────────────────────────────────

    @property
    def is_ready(self) -> bool:
        """True when cooldown has elapsed."""
        return self._cooldown_timer <= 0.0

    @property
    def is_active(self) -> bool:
        """True while a sustained effect is running."""
        return self._is_active

    @property
    def cooldown_fraction(self) -> float:
        """0.0 = ready, 1.0 = just used.  For UI display."""
        if self.cooldown <= 0:
            return 0.0
        return max(0.0, min(1.0, self._cooldown_timer / self.cooldown))

    # ── Public API ────────────────────────────────────────

    def can_use(self, user) -> bool:
        """Check whether the ability can fire right now."""
        if not self.is_ready:
            return False
        if not getattr(user, "can_act", True):
            return False
        stam = getattr(user, "stamina_component", None)
        if stam is not None and not stam.has_enough(self.stamina_cost):
            return False
        return True

    def activate(self, user, **kwargs) -> bool:
        """Attempt to use the ability.  Returns True on success."""
        if not self.can_use(user):
            return False

        # Drain stamina
        stam = getattr(user, "stamina_component", None)
        if stam is not None:
            stam.drain(self.stamina_cost)

        # Start cooldown
        self._cooldown_timer = self.cooldown

        # Start duration (if sustained)
        if self.duration > 0:
            self._active_timer = self.duration
            self._is_active = True

        self._on_activate(user, **kwargs)
        logger.info("Ability '%s' activated by %s", self.name, type(user).__name__)
        return True

    def update(self, dt: float, user=None) -> None:
        """Tick cooldown and active-effect timers.  Call every frame."""
        # Cooldown countdown
        if self._cooldown_timer > 0:
            self._cooldown_timer = max(0.0, self._cooldown_timer - dt)

        # Sustained effect countdown
        if self._is_active:
            self._active_timer -= dt
            if user is not None:
                self._on_tick(dt, user)
            if self._active_timer <= 0:
                self._is_active = False
                if user is not None:
                    self._on_expire(user)

    # ── Hooks (override in subclasses) ────────────────────

    def _on_activate(self, user, **kwargs) -> None:
        """Called once when the ability fires."""

    def _on_tick(self, dt: float, user) -> None:
        """Called every frame while a sustained ability is active."""

    def _on_expire(self, user) -> None:
        """Called once when a sustained effect ends."""


# ══════════════════════════════════════════════════════════
#  Role-Specific Abilities
# ══════════════════════════════════════════════════════════

class MageAbility(Ability):
    """Fire an auto-aim magic projectile toward the enemy."""

    name = "Arcane Bolt"
    cooldown = 2.0
    duration = 0.0  # instant
    stamina_cost = 18.0
    description = "Fires a magic projectile."

    def __init__(self) -> None:
        super().__init__()
        self.pending_projectile: bool = False
        self.spawn_x: float = 0.0
        self.spawn_y: float = 0.0
        self.target_x: float = 0.0
        self.target_y: float = 0.0

    def _on_activate(self, user, **kwargs) -> None:
        self.spawn_x = float(user.rect.centerx)
        self.spawn_y = float(user.rect.centery)

        # Auto-aim: use the target entity passed via kwargs
        target = kwargs.get("target")
        if target is not None and hasattr(target, "rect"):
            self.target_x = float(target.rect.centerx)
            self.target_y = float(target.rect.centery)
        else:
            # Fallback: fire in facing direction (horizontal)
            facing = getattr(user, "facing", 1)
            self.target_x = self.spawn_x + facing * 400
            self.target_y = self.spawn_y

        self.pending_projectile = True

    def consume_projectile(self) -> tuple[float, float, float, float] | None:
        """Return (spawn_x, spawn_y, target_x, target_y) if pending, else None."""
        if self.pending_projectile:
            self.pending_projectile = False
            return (self.spawn_x, self.spawn_y, self.target_x, self.target_y)
        return None


class BerserkerAbility(Ability):
    """Temporary damage multiplier boost."""

    name = "Blood Rage"
    cooldown = 8.0
    duration = 4.0
    stamina_cost = 25.0
    description = "Boosts damage for a short time."

    _DAMAGE_MULT = 1.6

    def __init__(self) -> None:
        super().__init__()
        self._prev_mult: float = 1.0

    def _on_activate(self, user, **kwargs) -> None:
        self._prev_mult = getattr(user, "role_damage_mult", 1.0)
        user.role_damage_mult = self._prev_mult * self._DAMAGE_MULT

    def _on_expire(self, user) -> None:
        user.role_damage_mult = self._prev_mult


class GuardianAbility(Ability):
    """Temporary shield that reduces incoming damage."""

    name = "Iron Bastion"
    cooldown = 10.0
    duration = 5.0
    stamina_cost = 22.0
    description = "Reduces incoming damage briefly."

    _DEFENSE_REDUCTION = 0.50  # take only 50% damage while active

    def __init__(self) -> None:
        super().__init__()
        self._prev_mult: float = 1.0

    def _on_activate(self, user, **kwargs) -> None:
        self._prev_mult = getattr(user, "role_defense_mult", 1.0)
        user.role_defense_mult = self._prev_mult * self._DEFENSE_REDUCTION

    def _on_expire(self, user) -> None:
        user.role_defense_mult = self._prev_mult


class AssassinAbility(Ability):
    """Quick dash/blink with a brief invulnerability window."""

    name = "Shadow Step"
    cooldown = 4.0
    duration = 0.18  # invulnerability window (seconds)
    stamina_cost = 15.0
    description = "Blink forward with brief invulnerability."

    _BLINK_DISTANCE = 90  # pixels

    def _on_activate(self, user, **kwargs) -> None:
        direction = getattr(user, "facing", 1)
        user.rect.x += self._BLINK_DISTANCE * direction
        # Clamp to screen
        user.rect.clamp_ip(pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT))
        # Grant invulnerability for the duration
        user.is_invincible = True

    def _on_expire(self, user) -> None:
        user.is_invincible = False


class TacticianAbility(Ability):
    """Minor boost to speed and damage."""

    name = "Battle Plan"
    cooldown = 12.0
    duration = 6.0
    stamina_cost = 20.0
    description = "Boosts speed and damage slightly."

    _SPEED_BONUS = 2
    _DAMAGE_BONUS = 1.2

    def __init__(self) -> None:
        super().__init__()
        self._prev_speed: float = 0.0
        self._prev_mult: float = 1.0

    def _on_activate(self, user, **kwargs) -> None:
        self._prev_speed = user.speed
        self._prev_mult = getattr(user, "role_damage_mult", 1.0)
        user.speed = user.speed + self._SPEED_BONUS
        user.role_damage_mult = self._prev_mult * self._DAMAGE_BONUS

    def _on_expire(self, user) -> None:
        user.speed = self._prev_speed
        user.role_damage_mult = self._prev_mult


class AdaptiveAbility(Ability):
    """Scaling stat bonus that grows the longer the match goes."""

    name = "Evolve"
    cooldown = 14.0
    duration = 7.0
    stamina_cost = 20.0
    description = "Stat bonus that scales with elapsed time."

    _BASE_MULT = 1.10
    _SCALE_PER_SEC = 0.005  # extra multiplier per second of match time

    def __init__(self) -> None:
        super().__init__()
        self._match_time: float = 0.0
        self._prev_speed: float = 0.0
        self._prev_dmg_mult: float = 1.0
        self._prev_def_mult: float = 1.0

    def _on_activate(self, user, **kwargs) -> None:
        self._match_time += self.duration  # approximate
        scaling = self._BASE_MULT + self._SCALE_PER_SEC * self._match_time
        scaling = min(scaling, 1.5)  # cap

        self._prev_speed = user.speed
        self._prev_dmg_mult = getattr(user, "role_damage_mult", 1.0)
        self._prev_def_mult = getattr(user, "role_defense_mult", 1.0)

        user.speed = user.speed + 1
        user.role_damage_mult = self._prev_dmg_mult * scaling
        user.role_defense_mult = self._prev_def_mult * max(0.5, 1.0 / scaling)

    def _on_expire(self, user) -> None:
        user.speed = self._prev_speed
        user.role_damage_mult = self._prev_dmg_mult
        user.role_defense_mult = self._prev_def_mult


# ══════════════════════════════════════════════════════════
#  Factory
# ══════════════════════════════════════════════════════════

_ROLE_ABILITY_MAP: dict[str, type[Ability]] = {
    "Mage":       MageAbility,
    "Berserker":  BerserkerAbility,
    "Guardian":   GuardianAbility,
    "Assassin":   AssassinAbility,
    "Tactician":  TacticianAbility,
    "Adaptive":   AdaptiveAbility,
}


def create_ability(role_name: str) -> Ability | None:
    """Factory: return the correct Ability subclass for *role_name*, or None."""
    cls = _ROLE_ABILITY_MAP.get(role_name)
    if cls is None:
        return None
    return cls()
