"""
buff_system.py – Roguelike buff system.

After defeating an enemy, a random buff drops from the pool.
Each buff has a duration, visual indicator, and gameplay effect.

Buff pool:
- Rage       – increase attack speed
- Shield     – damage reduction
- Lifesteal  – heal on hit
- Frost      – slow opponent
- Shadow     – increased dodge chance

Architecture:
- Buff (base class)
- Concrete buff subclasses
- BuffManager (per character, manages active buffs)
- buff_drop() function (call on enemy defeat)
"""

from __future__ import annotations

import random
import math
import pygame
from settings import (
    BUFF_RAGE_ATTACK_SPEED_MULT, BUFF_RAGE_DURATION,
    BUFF_SHIELD_DAMAGE_REDUCTION, BUFF_SHIELD_DURATION,
    BUFF_LIFESTEAL_FRACTION, BUFF_LIFESTEAL_DURATION,
    BUFF_FROST_SLOW_MULT, BUFF_FROST_DURATION,
    BUFF_SHADOW_DODGE_BONUS, BUFF_SHADOW_DURATION,
    BUFF_DROP_CHANCE,
)


# ══════════════════════════════════════════════════════════
#  Buff Base Class
# ══════════════════════════════════════════════════════════

class Buff:
    """Abstract buff with duration, visual, and effect hooks."""

    name: str = "Buff"
    description: str = ""
    color: tuple = (255, 255, 255)
    icon_char: str = "?"

    def __init__(self, duration: float):
        self.duration = duration
        self.remaining = duration
        self.active = True
        self._stacks = 1

    @property
    def progress(self) -> float:
        """0.0 → 1.0 over lifetime."""
        return 1.0 - max(0.0, self.remaining / self.duration)

    @property
    def expired(self) -> bool:
        return self.remaining <= 0.0

    def update(self, dt: float):
        self.remaining -= dt
        if self.remaining <= 0:
            self.active = False

    # Override in subclasses:
    def on_apply(self, character):
        """Called when buff is first applied."""
        pass

    def on_remove(self, character):
        """Called when buff expires or is removed."""
        pass

    def modify_damage_dealt(self, damage: float) -> float:
        """Modify outgoing damage."""
        return damage

    def modify_damage_taken(self, damage: float) -> float:
        """Modify incoming damage."""
        return damage

    def on_hit_landed(self, attacker, damage: float):
        """Called when the buffed character lands a hit."""
        pass

    def modify_attack_cooldown(self, cooldown: float) -> float:
        """Modify attack cooldown."""
        return cooldown

    def modify_speed(self, speed: float) -> float:
        """Modify character speed (applied to target if debuff)."""
        return speed

    def get_dodge_bonus(self) -> float:
        """Extra dodge chance (0.0–1.0)."""
        return 0.0


# ══════════════════════════════════════════════════════════
#  Concrete Buffs
# ══════════════════════════════════════════════════════════

class RageBuff(Buff):
    """Increases attack speed for the duration."""

    name = "Rage"
    description = "Attack speed increased"
    color = (255, 60, 30)
    icon_char = "R"

    def __init__(self):
        super().__init__(BUFF_RAGE_DURATION)

    def modify_attack_cooldown(self, cooldown: float) -> float:
        return cooldown / BUFF_RAGE_ATTACK_SPEED_MULT


class ShieldBuff(Buff):
    """Reduces incoming damage for the duration."""

    name = "Shield"
    description = "Damage reduction"
    color = (80, 140, 255)
    icon_char = "S"

    def __init__(self):
        super().__init__(BUFF_SHIELD_DURATION)

    def modify_damage_taken(self, damage: float) -> float:
        return damage * (1.0 - BUFF_SHIELD_DAMAGE_REDUCTION)


class LifestealBuff(Buff):
    """Heals the owner for a fraction of damage dealt."""

    name = "Lifesteal"
    description = "Heal on hit"
    color = (180, 40, 220)
    icon_char = "L"

    def __init__(self):
        super().__init__(BUFF_LIFESTEAL_DURATION)

    def on_hit_landed(self, attacker, damage: float):
        heal = max(1, int(damage * BUFF_LIFESTEAL_FRACTION))
        attacker.heal(heal)


class FrostBuff(Buff):
    """Applied to the OWNER – slows the opponent when owner hits."""
    name = "Frost"
    description = "Slow opponent"
    color = (100, 200, 255)
    icon_char = "F"

    def __init__(self):
        super().__init__(BUFF_FROST_DURATION)
        self._slow_target = None

    def modify_speed(self, speed: float) -> float:
        return speed * BUFF_FROST_SLOW_MULT


class ShadowBuff(Buff):
    """Grants bonus dodge chance for the duration."""

    name = "Shadow"
    description = "Dodge chance up"
    color = (60, 60, 80)
    icon_char = "D"

    def __init__(self):
        super().__init__(BUFF_SHADOW_DURATION)

    def get_dodge_bonus(self) -> float:
        return BUFF_SHADOW_DODGE_BONUS


# ── Buff pool ────────────────────────────────────────────
BUFF_POOL: list[type] = [RageBuff, ShieldBuff, LifestealBuff,
                          FrostBuff, ShadowBuff]


# ══════════════════════════════════════════════════════════
#  Buff Manager (per character)
# ══════════════════════════════════════════════════════════

class BuffManager:
    """Manages active buffs for a single character."""

    def __init__(self):
        self.active_buffs: list[Buff] = []

    def add_buff(self, buff: Buff, character):
        """Apply a buff. Stacks by resetting duration if same type exists."""
        for existing in self.active_buffs:
            if type(existing) is type(buff):
                existing.remaining = existing.duration
                existing._stacks += 1
                return
        buff.on_apply(character)
        self.active_buffs.append(buff)

    def remove_buff(self, buff: Buff, character):
        buff.on_remove(character)
        if buff in self.active_buffs:
            self.active_buffs.remove(buff)

    def update(self, dt: float, character):
        """Tick all buffs, remove expired."""
        expired = []
        for buff in self.active_buffs:
            buff.update(dt)
            if buff.expired:
                expired.append(buff)
        for buff in expired:
            self.remove_buff(buff, character)

    def clear(self, character):
        for buff in list(self.active_buffs):
            self.remove_buff(buff, character)

    # ── Aggregated queries ────────────────────────────────

    def modify_damage_dealt(self, damage: float) -> float:
        for b in self.active_buffs:
            damage = b.modify_damage_dealt(damage)
        return damage

    def modify_damage_taken(self, damage: float) -> float:
        for b in self.active_buffs:
            damage = b.modify_damage_taken(damage)
        return damage

    def modify_attack_cooldown(self, cooldown: float) -> float:
        for b in self.active_buffs:
            cooldown = b.modify_attack_cooldown(cooldown)
        return cooldown

    def modify_speed(self, speed: float) -> float:
        for b in self.active_buffs:
            speed = b.modify_speed(speed)
        return speed

    def get_dodge_bonus(self) -> float:
        bonus = 0.0
        for b in self.active_buffs:
            bonus += b.get_dodge_bonus()
        return min(0.9, bonus)

    def on_hit_landed(self, attacker, damage: float):
        for b in list(self.active_buffs):
            b.on_hit_landed(attacker, damage)

    @property
    def has_frost(self) -> bool:
        return any(isinstance(b, FrostBuff) for b in self.active_buffs)


# ══════════════════════════════════════════════════════════
#  Drop Logic
# ══════════════════════════════════════════════════════════

def roll_buff_drop() -> Buff | None:
    """Roll for a random buff drop. Returns None if no drop."""
    if random.random() > BUFF_DROP_CHANCE:
        return None
    buff_cls = random.choice(BUFF_POOL)
    return buff_cls()


# ══════════════════════════════════════════════════════════
#  Visual Indicator Drawing
# ══════════════════════════════════════════════════════════

def draw_buff_indicators(surface: pygame.Surface,
                         buff_mgr: BuffManager,
                         x: int, y: int):
    """Draw small colored circles + timer for active buffs."""
    if not buff_mgr.active_buffs:
        return
    font = pygame.font.SysFont(None, 16)
    bx = x
    for buff in buff_mgr.active_buffs:
        # Pulsing aura circle
        alpha = int(140 + 60 * math.sin(buff.progress * math.pi * 4))
        aura_surf = pygame.Surface((18, 18), pygame.SRCALPHA)
        pygame.draw.circle(aura_surf, (*buff.color, alpha), (9, 9), 8)
        pygame.draw.circle(aura_surf, (*buff.color, 200), (9, 9), 8, 1)
        surface.blit(aura_surf, (bx, y))

        # Icon letter
        icon = font.render(buff.icon_char, True, (255, 255, 255))
        surface.blit(icon, (bx + 4, y + 2))

        # Timer bar under icon
        bar_w = int(14 * (1.0 - buff.progress))
        if bar_w > 0:
            pygame.draw.rect(surface, buff.color,
                             (bx + 2, y + 18, bar_w, 2))
        bx += 22
