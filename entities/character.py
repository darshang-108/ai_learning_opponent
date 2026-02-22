"""
character.py – Pixel-based character with modular body parts
and procedural animation via transforms.

Replaces rectangular entities with a composited pixel knight
sprite built from head, body, arm, weapon, shield parts.

States: idle, attack, block, hurt, death
Animation is fully procedural (rotation, scale, offsets) –
no external sprite sheet or animation software required.
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

import pygame
from settings import (
    CHAR_WIDTH, CHAR_HEIGHT, ARENA_FLOOR_Y, SCREEN_WIDTH, SCREEN_HEIGHT,
    HIT_INVULN_DURATION,
    MELEE_HITBOX_WIDTH, MELEE_HITBOX_HEIGHT, MELEE_HITBOX_OFFSET_X,
    ATTACK_ACTIVE_START, ATTACK_ACTIVE_END,
)


# ══════════════════════════════════════════════════════════
#  Body Part Definition
# ══════════════════════════════════════════════════════════

class BodyPart:
    """A single pixel-art body component with transform support."""

    __slots__ = (
        "name", "surface", "anchor_x", "anchor_y",
        "offset_x", "offset_y", "rotation", "scale",
        "base_offset_x", "base_offset_y", "visible",
    )

    def __init__(self, name: str, surface: pygame.Surface,
                 anchor_x: int = 0, anchor_y: int = 0):
        self.name = name
        self.surface = surface
        self.anchor_x = anchor_x       # pivot relative to part surface
        self.anchor_y = anchor_y
        self.base_offset_x = 0         # constant offset from character origin
        self.base_offset_y = 0
        self.offset_x = 0.0            # animation offset (additive)
        self.offset_y = 0.0
        self.rotation = 0.0            # degrees
        self.scale = 1.0
        self.visible = True

    def reset_transform(self):
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.rotation = 0.0
        self.scale = 1.0

    def get_rendered(self) -> tuple[pygame.Surface, tuple[int, int]]:
        """Return (transformed_surface, blit_position) relative to char origin."""
        if not self.visible:
            return pygame.Surface((0, 0), pygame.SRCALPHA), (0, 0)

        surf = self.surface
        # Apply scale
        if abs(self.scale - 1.0) > 0.01:
            w = max(1, int(surf.get_width() * self.scale))
            h = max(1, int(surf.get_height() * self.scale))
            surf = pygame.transform.scale(surf, (w, h))

        # Apply rotation
        if abs(self.rotation) > 0.5:
            surf = pygame.transform.rotate(surf, self.rotation)

        # Compute blit position
        bx = self.base_offset_x + int(self.offset_x) - surf.get_width() // 2
        by = self.base_offset_y + int(self.offset_y) - surf.get_height() // 2
        return surf, (bx, by)


# ══════════════════════════════════════════════════════════
#  Pixel Sprite Builder
# ══════════════════════════════════════════════════════════

def _make_surface(w: int, h: int) -> pygame.Surface:
    return pygame.Surface((w, h), pygame.SRCALPHA)


def _fill_pixels(surf: pygame.Surface, pixel_data: list[str],
                 palette: dict[str, tuple]) -> None:
    """Fill surface from a list of strings where each char maps to a color."""
    for y, row in enumerate(pixel_data):
        for x, ch in enumerate(row):
            if ch in palette:
                surf.set_at((x, y), palette[ch])


def build_knight_parts(base_color: tuple, accent_color: tuple,
                       skin_color: tuple = (230, 190, 155),
                       facing: int = 1) -> dict[str, BodyPart]:
    """Build a modular pixel knight sprite.

    Parameters
    ----------
    base_color   : primary armor color (r, g, b)
    accent_color : trim / accent color
    skin_color   : exposed skin
    facing       : 1 = right, -1 = left

    Returns dict of BodyPart keyed by name.
    """
    dark = tuple(max(0, c - 50) for c in base_color)
    light = tuple(min(255, c + 40) for c in base_color)
    metal = (180, 190, 200)
    metal_dark = (120, 130, 140)
    visor = (40, 50, 60)
    blade = (200, 210, 220)
    blade_edge = (240, 245, 250)
    hilt = (140, 100, 50)
    shield_face = accent_color
    shield_rim = tuple(max(0, c - 40) for c in accent_color)

    # ── HEAD (12×12) ──────────────────────────────────────
    head_data = [
        "....mmmm....",
        "...mMMMMm...",
        "..mMMMMMMm..",
        "..mMvvvvMm..",
        "..mMvSSSvm..",
        "..mmvSSSvm..",
        "...mSSSSm...",
        "...mSSSSm...",
        "...mmmmmmm..",
        "....mMMm....",
        "....mMMm....",
        "............",
    ]
    head_pal = {
        "m": metal, "M": metal_dark, "v": visor,
        "S": skin_color, ".": (0, 0, 0, 0),
    }
    head_surf = _make_surface(12, 12)
    _fill_pixels(head_surf, head_data, head_pal)
    head = BodyPart("head", pygame.transform.scale(head_surf, (20, 20)),
                    anchor_x=10, anchor_y=16)
    head.base_offset_x = CHAR_WIDTH // 2
    head.base_offset_y = 6

    # ── BODY (16×18) ─────────────────────────────────────
    body_data = [
        "....BBBBBBBB....",
        "...BBBBBBBBBB...",
        "..BBBBBBBBBBBB..",
        "..BBAAccAABBBB..",
        "..BBAAccAABBBB..",
        "..BBBBBBBBBBBB..",
        "..BBBBddBBBBBB..",
        "..BBBBddBBBBBB..",
        "..BBBBddBBBBBB..",
        "...BBBddBBBBB...",
        "...BBBddBBBBB...",
        "....BBddBBBB....",
        "....BBddBBBB....",
        "....BBddBBBB....",
        "...ddd..ddd.....",
        "..dBBd..dBBd....",
        "..dBBd..dBBd....",
        "..dddd..dddd....",
    ]
    body_pal = {
        "B": base_color, "A": accent_color, "d": dark,
        "c": light, ".": (0, 0, 0, 0),
    }
    body_surf = _make_surface(16, 18)
    _fill_pixels(body_surf, body_data, body_pal)
    body = BodyPart("body", pygame.transform.scale(body_surf, (28, 34)),
                    anchor_x=14, anchor_y=4)
    body.base_offset_x = CHAR_WIDTH // 2
    body.base_offset_y = 22

    # ── ARM (weapon side, 6×14) ──────────────────────────
    arm_data = [
        "..BB..",
        ".BBBB.",
        ".BBBB.",
        ".BBBB.",
        ".BBBB.",
        ".BSSB.",
        ".BSSB.",
        ".BSSB.",
        "..SS..",
        "..SS..",
        "..SS..",
        "..SS..",
        "......",
        "......",
    ]
    arm_pal = {
        "B": base_color, "S": skin_color, ".": (0, 0, 0, 0),
    }
    arm_surf = _make_surface(6, 14)
    _fill_pixels(arm_surf, arm_data, arm_pal)
    weapon_arm = BodyPart("weapon_arm",
                          pygame.transform.scale(arm_surf, (10, 22)),
                          anchor_x=5, anchor_y=4)
    weapon_arm.base_offset_x = CHAR_WIDTH // 2 + 16 * facing
    weapon_arm.base_offset_y = 20

    # ── WEAPON (sword, 4×20) ─────────────────────────────
    sword_data = [
        ".EE.",
        ".WW.",
        ".WW.",
        ".WW.",
        ".WW.",
        ".WW.",
        ".WW.",
        ".WW.",
        ".WW.",
        ".WW.",
        ".WW.",
        ".WW.",
        ".WW.",
        ".WW.",
        "HHHH",
        "HHHH",
        ".HH.",
        ".hh.",
        ".hh.",
        "....",
    ]
    sword_pal = {
        "W": blade, "E": blade_edge, "H": hilt,
        "h": (100, 70, 30), ".": (0, 0, 0, 0),
    }
    sword_surf = _make_surface(4, 20)
    _fill_pixels(sword_surf, sword_data, sword_pal)
    weapon = BodyPart("weapon",
                      pygame.transform.scale(sword_surf, (8, 36)),
                      anchor_x=4, anchor_y=28)
    weapon.base_offset_x = CHAR_WIDTH // 2 + 22 * facing
    weapon.base_offset_y = 16

    # ── SHIELD (off-hand, 8×12) ──────────────────────────
    shield_data = [
        ".rrrrrr.",
        "rFFFFFFr",
        "rFFAAFFr",
        "rFFAAFFr",
        "rFFAAFFr",
        "rFFFFFFr",
        "rFFFFFFr",
        "rFFFFFFr",
        ".rFFFFr.",
        "..rFFr..",
        "...rr...",
        "........",
    ]
    shield_pal = {
        "r": shield_rim, "F": shield_face, "A": accent_color,
        ".": (0, 0, 0, 0),
    }
    shield_surf = _make_surface(8, 12)
    _fill_pixels(shield_surf, shield_data, shield_pal)
    shield = BodyPart("shield",
                      pygame.transform.scale(shield_surf, (14, 22)),
                      anchor_x=7, anchor_y=4)
    shield.base_offset_x = CHAR_WIDTH // 2 - 18 * facing
    shield.base_offset_y = 22

    return {
        "head": head,
        "body": body,
        "weapon_arm": weapon_arm,
        "weapon": weapon,
        "shield": shield,
    }


# ══════════════════════════════════════════════════════════
#  Animation State Machine
# ══════════════════════════════════════════════════════════

class AnimState:
    """Procedural animation state – applies transforms each frame."""

    def __init__(self, name: str, duration: float = 0.0, looping: bool = True):
        self.name = name
        self.duration = duration
        self.looping = looping
        self.timer = 0.0

    @property
    def progress(self) -> float:
        if self.duration <= 0:
            return 0.0
        return min(1.0, self.timer / self.duration)

    @property
    def finished(self) -> bool:
        return not self.looping and self.timer >= self.duration

    def reset(self):
        self.timer = 0.0


def apply_idle_animation(parts: dict[str, BodyPart], t: float):
    """Gentle breathing + weapon sway."""
    breath = math.sin(t * 2.5) * 1.5
    sway = math.sin(t * 1.8) * 2.0
    parts["head"].offset_y = breath * 0.6
    parts["body"].offset_y = breath
    parts["weapon_arm"].offset_y = breath * 0.8
    parts["weapon_arm"].rotation = sway
    parts["weapon"].offset_y = breath * 0.5
    parts["weapon"].rotation = sway * 1.2
    parts["shield"].offset_y = breath * 0.7
    parts["shield"].rotation = -sway * 0.5


def apply_attack_animation(parts: dict[str, BodyPart], progress: float,
                           facing: int):
    """Swing weapon forward in an arc."""
    # Wind-up (0 – 0.3) then slash (0.3 – 0.7) then follow-through (0.7 – 1.0)
    if progress < 0.3:
        # wind-up: pull weapon back
        frac = progress / 0.3
        parts["weapon"].rotation = -30 * frac * facing
        parts["weapon"].offset_x = -6 * frac * facing
        parts["weapon_arm"].rotation = -15 * frac * facing
        parts["body"].rotation = -3 * frac * facing
    elif progress < 0.7:
        # slash: swing forward fast
        frac = (progress - 0.3) / 0.4
        parts["weapon"].rotation = (-30 + 100 * frac) * facing
        parts["weapon"].offset_x = (-6 + 20 * frac) * facing
        parts["weapon_arm"].rotation = (-15 + 45 * frac) * facing
        parts["body"].rotation = (-3 + 8 * frac) * facing
        parts["head"].offset_x = 2 * frac * facing
    else:
        # follow-through: ease back
        frac = (progress - 0.7) / 0.3
        parts["weapon"].rotation = (70 - 70 * frac) * facing
        parts["weapon"].offset_x = (14 - 14 * frac) * facing
        parts["weapon_arm"].rotation = (30 - 30 * frac) * facing
        parts["body"].rotation = (5 - 5 * frac) * facing
        parts["head"].offset_x = (2 - 2 * frac) * facing


def apply_block_animation(parts: dict[str, BodyPart], facing: int):
    """Raise shield and lean back."""
    parts["shield"].offset_y = -8
    parts["shield"].offset_x = 6 * facing
    parts["shield"].rotation = 10 * facing
    parts["shield"].scale = 1.15
    parts["body"].rotation = -4 * facing
    parts["weapon"].offset_x = -4 * facing
    parts["weapon"].rotation = -20 * facing


def apply_hurt_animation(parts: dict[str, BodyPart], progress: float,
                         facing: int):
    """Knock back and flash red."""
    # Quick jerk backward then recover
    if progress < 0.4:
        frac = progress / 0.4
        knockback = 6 * frac
        for part in parts.values():
            part.offset_x += -knockback * facing
        parts["body"].rotation = -8 * frac * facing
        parts["head"].offset_y = -3 * frac
    else:
        frac = (progress - 0.4) / 0.6
        knockback = 6 * (1.0 - frac)
        for part in parts.values():
            part.offset_x += -knockback * facing
        parts["body"].rotation = -8 * (1 - frac) * facing


def apply_death_animation(parts: dict[str, BodyPart], progress: float,
                          facing: int):
    """Collapse: tilt and sink."""
    tilt = min(1.0, progress * 1.5) * 80 * facing
    sink = min(1.0, progress) * 20
    alpha_mult = max(0.0, 1.0 - progress * 0.6)
    for part in parts.values():
        part.rotation = tilt * 0.3
        part.offset_y += sink
    parts["weapon"].offset_x = 10 * progress * facing
    parts["weapon"].rotation = tilt * 0.8


# ══════════════════════════════════════════════════════════
#  Character Base Class
# ══════════════════════════════════════════════════════════

class Character:
    """Pixel-based combat character with modular body parts,
    procedural animation, stamina, and state machine.

    Subclass for Player / Enemy specifics.
    """

    def __init__(self, x: int, y: int, base_color: tuple,
                 accent_color: tuple, facing: int = 1,
                 max_hp: int = 120):
        # Position / collision
        self.rect = pygame.Rect(x, y, CHAR_WIDTH, CHAR_HEIGHT)
        self.facing = facing           # 1 = right, -1 = left

        # Visual
        self.base_color = base_color
        self.accent_color = accent_color
        self.parts = build_knight_parts(base_color, accent_color, facing=facing)

        # Display position (smooth interpolation)
        self.display_x = float(x)
        self.display_y = float(y)

        # Health
        self.max_hp = max_hp
        self.hp = max_hp

        # Stamina (managed by StaminaSystem)
        self.stamina: float = 100.0
        self.max_stamina: float = 100.0
        self.stamina_component: Any = None  # StaminaComponent, set by subclass
        self.buff_manager: Any = None       # BuffManager, set by subclass

        # Combat state
        self.is_attacking = False
        self.is_blocking = False
        self.is_dodging = False
        self.is_stunned = False
        self.stun_timer = 0.0
        self.is_invincible = False

        # Dodge
        self.dodge_timer = 0.0
        self.dodge_dir = 0             # -1 left, 1 right
        self.dodge_cooldown_timer = 0.0

        # Animation
        self.anim_state = "idle"       # idle | attack | block | hurt | death
        self.anim_timer = 0.0
        self._global_timer = 0.0       # for idle animation
        self._last_attack_time = 0.0
        self.attack_duration = 0.35    # seconds per attack animation
        self.hurt_duration = 0.3
        self.death_duration = 1.0

        # Buffs (managed by BuffSystem)
        self.active_buffs: list = []

        # Damage multiplier (modified by buffs/parry)
        self.damage_mult = 1.0

        # Speed (base, can be modified by buffs)
        self.base_speed = 5
        self.speed = self.base_speed

        # Avatar surface override
        self.avatar_surface: pygame.Surface | None = None

        # Knockback impulse
        self._knockback_vx = 0.0
        self._knockback_vy = 0.0

        # Invulnerability frames (after taking damage)
        self._invuln_timer = 0.0
        self._invuln_duration = HIT_INVULN_DURATION

        # Melee hitbox (active only during attack active frames)
        self._attack_hitbox: pygame.Rect | None = None
        self._hitbox_hit_targets: set[int] = set()  # prevent multi-hit per swing

    # ── Properties ────────────────────────────────────────

    @property
    def alive(self) -> bool:
        return self.hp > 0

    @property
    def center(self) -> tuple[int, int]:
        return self.rect.center

    @property
    def can_act(self) -> bool:
        return (self.alive
                and not self.is_stunned
                and not self.is_dodging
                and self.anim_state not in ("hurt", "death"))

    @property
    def is_invulnerable(self) -> bool:
        """True during dodge i-frames OR post-hit i-frames."""
        return self.is_invincible or self._invuln_timer > 0

    @property
    def attack_hitbox(self) -> pygame.Rect | None:
        """Active melee hitbox rect, or None if not currently in active frames."""
        return self._attack_hitbox

    # ── Core update (call each frame) ─────────────────────

    def update_animation(self, dt: float):
        """Advance animation timers and apply procedural transforms."""
        self._global_timer += dt
        self.anim_timer += dt

        # Smooth display position
        lerp = 0.18
        self.display_x += (self.rect.x - self.display_x) * lerp
        self.display_y += (self.rect.y - self.display_y) * lerp

        # Knockback decay
        if abs(self._knockback_vx) > 0.1 or abs(self._knockback_vy) > 0.1:
            self.rect.x += int(self._knockback_vx * dt * 60)
            self.rect.y += int(self._knockback_vy * dt * 60)
            self._knockback_vx *= 0.85
            self._knockback_vy *= 0.85
        else:
            self._knockback_vx = 0.0
            self._knockback_vy = 0.0

        # Invulnerability frame timer
        if self._invuln_timer > 0:
            self._invuln_timer -= dt
            if self._invuln_timer <= 0:
                self._invuln_timer = 0.0

        # Stun timer
        if self.is_stunned:
            self.stun_timer -= dt
            if self.stun_timer <= 0:
                self.is_stunned = False
                self.stun_timer = 0.0

        # Dodge timer
        if self.is_dodging:
            self.dodge_timer -= dt
            if self.dodge_timer <= 0:
                self.is_dodging = False
                self.is_invincible = False
        if self.dodge_cooldown_timer > 0:
            self.dodge_cooldown_timer -= dt

        # Reset all transforms
        for part in self.parts.values():
            part.reset_transform()

        # Apply state-specific animation
        if self.anim_state == "death":
            progress = min(1.0, self.anim_timer / self.death_duration)
            apply_death_animation(self.parts, progress, self.facing)
        elif self.anim_state == "hurt":
            progress = min(1.0, self.anim_timer / self.hurt_duration)
            apply_hurt_animation(self.parts, progress, self.facing)
            if self.anim_timer >= self.hurt_duration:
                self.anim_state = "idle"
                self.anim_timer = 0.0
        elif self.anim_state == "block":
            apply_block_animation(self.parts, self.facing)
        elif self.anim_state == "attack":
            progress = min(1.0, self.anim_timer / self.attack_duration)
            apply_attack_animation(self.parts, progress, self.facing)
            # Update melee hitbox during active frames
            if ATTACK_ACTIVE_START <= progress <= ATTACK_ACTIVE_END:
                hx = self.rect.centerx + (MELEE_HITBOX_OFFSET_X * self.facing)
                hy = self.rect.centery - MELEE_HITBOX_HEIGHT // 2
                self._attack_hitbox = pygame.Rect(
                    hx - MELEE_HITBOX_WIDTH // 2, hy,
                    MELEE_HITBOX_WIDTH, MELEE_HITBOX_HEIGHT,
                )
            else:
                self._attack_hitbox = None
            if self.anim_timer >= self.attack_duration:
                self.anim_state = "idle"
                self.anim_timer = 0.0
                self.is_attacking = False
                self._attack_hitbox = None
                self._hitbox_hit_targets.clear()
        else:
            # idle
            apply_idle_animation(self.parts, self._global_timer)

        # Clamp to screen
        self.rect.clamp_ip(pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT))

    # ── Actions ───────────────────────────────────────────

    def start_attack(self):
        if self.anim_state in ("attack", "death"):
            return
        self.anim_state = "attack"
        self.anim_timer = 0.0
        self.is_attacking = True

    def start_block(self):
        if self.anim_state == "death":
            return
        self.is_blocking = True
        self.anim_state = "block"

    def stop_block(self):
        self.is_blocking = False
        if self.anim_state == "block":
            self.anim_state = "idle"
            self.anim_timer = 0.0

    def start_dodge(self, direction: int):
        if self.anim_state == "death" or self.dodge_cooldown_timer > 0:
            return False
        from settings import DODGE_DURATION, DODGE_COOLDOWN, DODGE_IFRAMES
        self.is_dodging = True
        self.dodge_timer = DODGE_DURATION
        self.dodge_dir = direction
        self.dodge_cooldown_timer = DODGE_COOLDOWN
        if DODGE_IFRAMES:
            self.is_invincible = True
        # Stop blocking
        self.is_blocking = False
        if self.anim_state == "block":
            self.anim_state = "idle"
        return True

    def take_damage(self, amount: int):
        """Reduce HP. Triggers hurt state and i-frames if alive."""
        if self.is_invulnerable:
            return 0
        actual = max(1, int(amount))  # damage is never zero
        if self.is_blocking:
            from settings import BLOCK_DAMAGE_REDUCTION
            actual = max(1, int(actual * (1.0 - BLOCK_DAMAGE_REDUCTION)))
        self.hp = max(0, self.hp - actual)
        # Grant i-frames to prevent damage stacking
        self._invuln_timer = self._invuln_duration
        logger.debug("%s health reduced to %d (took %d)", self.__class__.__name__, self.hp, actual)
        if self.hp <= 0:
            self.anim_state = "death"
            self.anim_timer = 0.0
        elif self.anim_state != "death":
            self.anim_state = "hurt"
            self.anim_timer = 0.0
        return actual

    def apply_knockback(self, vx: float, vy: float = 0.0):
        self._knockback_vx += vx
        self._knockback_vy += vy

    def heal(self, amount: int):
        self.hp = min(self.max_hp, self.hp + amount)

    # ── Facing logic ──────────────────────────────────────

    def face_toward(self, target_x: int):
        new_facing = 1 if target_x > self.rect.centerx else -1
        if new_facing != self.facing:
            self.facing = new_facing
            self._rebuild_parts()

    def _rebuild_parts(self):
        self.parts = build_knight_parts(
            self.base_color, self.accent_color, facing=self.facing,
        )

    # ── Drawing ───────────────────────────────────────────

    def draw(self, surface: pygame.Surface, dt: float = 0.016):
        """Render the composited pixel character onto *surface*."""
        ox = int(self.display_x)
        oy = int(self.display_y)

        # Shadow ellipse
        shadow_w, shadow_h = CHAR_WIDTH + 6, 8
        shadow_surf = pygame.Surface((shadow_w, shadow_h), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow_surf, (0, 0, 0, 60), shadow_surf.get_rect())
        surface.blit(shadow_surf, (ox - 3, oy + CHAR_HEIGHT - 3))

        # Stun visual: yellow tint overlay
        tint = None
        if self.is_stunned:
            tint = (255, 255, 80, 50)
        # Dodge visual: ghost alpha
        dodge_alpha = 120 if self.is_dodging else 255

        # Composite body parts (order: shadow, body, head, arms, weapon, shield)
        draw_order = ["body", "shield", "weapon_arm", "weapon", "head"]
        for part_name in draw_order:
            part = self.parts.get(part_name)
            if part is None or not part.visible:
                continue
            rendered, (bx, by) = part.get_rendered()
            if rendered.get_width() == 0:
                continue

            if dodge_alpha < 255:
                rendered = rendered.copy()
                rendered.set_alpha(dodge_alpha)

            surface.blit(rendered, (ox + bx, oy + by))

        # Stun sparkle
        if self.is_stunned and self._global_timer % 0.3 < 0.15:
            star_surf = pygame.Surface((CHAR_WIDTH, 6), pygame.SRCALPHA)
            for i in range(3):
                sx = 8 + i * 14 + int(math.sin(self._global_timer * 5 + i) * 3)
                pygame.draw.circle(star_surf, (255, 255, 100, 200), (sx, 3), 2)
            surface.blit(star_surf, (ox, oy - 8))

    # ── Serialization helpers ─────────────────────────────

    def get_state_snapshot(self) -> dict:
        return {
            "hp": self.hp,
            "stamina": self.stamina,
            "anim_state": self.anim_state,
            "is_blocking": self.is_blocking,
            "is_stunned": self.is_stunned,
            "is_dodging": self.is_dodging,
            "x": self.rect.x,
            "y": self.rect.y,
        }
