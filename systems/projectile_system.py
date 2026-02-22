"""
projectile_system.py – Projectile / magic attack system.

Handles:
- Projectile creation, movement, collision, and destruction
- Glowing magic orb rendering
- Self-destruct on hit or out-of-bounds
- Integration with VFXSystem for impact effects

Used by the Mage AI personality and potentially future player abilities.
"""

from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

import pygame
from settings import (
    SCREEN_WIDTH, SCREEN_HEIGHT,
    PROJECTILE_SPEED, PROJECTILE_DAMAGE, PROJECTILE_RADIUS,
    PROJECTILE_LIFETIME, PROJECTILE_GLOW_RADIUS,
    PROJECTILE_COLOR, PROJECTILE_GLOW_COLOR,
)


class Projectile:
    """A single magic projectile with physics, collision, and VFX.

    Attributes
    ----------
    x, y        : float  – center position
    vx, vy      : float  – velocity in pixels/sec
    damage      : int    – damage applied on hit
    radius      : int    – collision radius
    active      : bool   – False after hit or lifetime expires
    owner_id    : int    – id() of the entity that spawned this (to avoid self-hit)
    """

    __slots__ = (
        "x", "y", "vx", "vy", "damage", "radius",
        "lifetime", "timer", "active", "owner_id",
        "_glow_radius", "_color", "_glow_color", "_pulse_timer",
    )

    def __init__(self, x: float, y: float, vx: float, vy: float,
                 damage: int = PROJECTILE_DAMAGE,
                 radius: int = PROJECTILE_RADIUS,
                 lifetime: float = PROJECTILE_LIFETIME,
                 owner_id: int = 0):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.damage = max(1, damage)  # damage is never zero
        self.radius = radius
        self.lifetime = lifetime
        self.timer = lifetime
        self.active = True
        self.owner_id = owner_id
        self._glow_radius = PROJECTILE_GLOW_RADIUS
        self._color = PROJECTILE_COLOR
        self._glow_color = PROJECTILE_GLOW_COLOR
        self._pulse_timer = 0.0

    @property
    def rect(self) -> pygame.Rect:
        """Bounding rect for collision detection."""
        return pygame.Rect(
            int(self.x - self.radius),
            int(self.y - self.radius),
            self.radius * 2,
            self.radius * 2,
        )

    def update(self, dt: float):
        """Move and age the projectile."""
        if not self.active:
            return
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.timer -= dt
        self._pulse_timer += dt

        # Self-destroy on lifetime expiry
        if self.timer <= 0:
            self.active = False

        # Self-destroy if out of bounds
        margin = 50
        if (self.x < -margin or self.x > SCREEN_WIDTH + margin
                or self.y < -margin or self.y > SCREEN_HEIGHT + margin):
            self.active = False

    def check_collision(self, target) -> bool:
        """Check collision with a target entity (must have .rect).
        Returns True if hit (and deactivates projectile)."""
        if not self.active:
            return False
        if id(target) == self.owner_id:
            return False
        # Skip invulnerable targets
        if getattr(target, 'is_invulnerable', False):
            return False
        if getattr(target, 'is_dodging', False):
            return False

        if self.rect.colliderect(target.rect):
            self.active = False
            return True
        return False

    def draw(self, surface: pygame.Surface):
        """Draw glowing magic orb."""
        if not self.active:
            return

        ix, iy = int(self.x), int(self.y)

        # Pulsing glow
        pulse = 1.0 + 0.2 * math.sin(self._pulse_timer * 8.0)
        glow_r = int(self._glow_radius * pulse)

        # Outer glow (transparent)
        glow_surf = pygame.Surface(
            (glow_r * 2 + 4, glow_r * 2 + 4), pygame.SRCALPHA,
        )
        center = (glow_r + 2, glow_r + 2)
        alpha_outer = 60
        pygame.draw.circle(
            glow_surf, (*self._glow_color[:3], alpha_outer),
            center, glow_r,
        )
        # Middle glow
        alpha_mid = 120
        mid_r = max(1, int(glow_r * 0.6))
        pygame.draw.circle(
            glow_surf, (*self._glow_color[:3], alpha_mid),
            center, mid_r,
        )
        surface.blit(glow_surf, (ix - glow_r - 2, iy - glow_r - 2))

        # Core solid circle
        pygame.draw.circle(surface, self._color, (ix, iy), self.radius)
        # Bright center
        inner_r = max(1, self.radius // 2)
        bright_color = (
            min(255, self._color[0] + 80),
            min(255, self._color[1] + 80),
            min(255, self._color[2] + 80),
        )
        pygame.draw.circle(surface, bright_color, (ix, iy), inner_r)


class ProjectileSystem:
    """Manages all active projectiles.

    Call ``update(dt)`` and ``draw(surface)`` each frame.
    Use ``spawn_*`` methods to create projectiles.
    """

    def __init__(self):
        self._projectiles: list[Projectile] = []

    @property
    def projectiles(self) -> list[Projectile]:
        return self._projectiles

    # ── Spawners ──────────────────────────────────────────

    def spawn_at(self, x: float, y: float,
                 target_x: float, target_y: float,
                 damage: int = PROJECTILE_DAMAGE,
                 speed: float = PROJECTILE_SPEED,
                 owner_id: int = 0) -> Projectile:
        """Spawn a projectile aimed at (target_x, target_y).

        Parameters
        ----------
        x, y             : spawn position
        target_x, target_y : target position (for direction)
        damage           : damage on hit
        speed            : projectile speed in px/sec
        owner_id         : id() of spawning entity (to avoid self-hit)

        Returns the created Projectile.
        """
        dx = target_x - x
        dy = target_y - y
        dist = math.hypot(dx, dy)
        if dist < 1:
            dx, dy, dist = 1, 0, 1
        vx = (dx / dist) * speed
        vy = (dy / dist) * speed
        proj = Projectile(x, y, vx, vy, damage=damage, owner_id=owner_id)
        self._projectiles.append(proj)
        logger.debug("Projectile spawned at (%.0f,%.0f) → (%.0f,%.0f)", x, y, target_x, target_y)
        return proj

    def spawn_directional(self, x: float, y: float,
                          direction: int, damage: int = PROJECTILE_DAMAGE,
                          speed: float = PROJECTILE_SPEED,
                          owner_id: int = 0) -> Projectile:
        """Spawn a projectile moving in a horizontal direction.

        Parameters
        ----------
        direction : 1 = right, -1 = left
        """
        vx = speed * direction
        proj = Projectile(x, y, vx, 0.0, damage=damage, owner_id=owner_id)
        self._projectiles.append(proj)
        logger.debug("Projectile spawned at (%.0f,%.0f) dir=%d", x, y, direction)
        return proj

    # ── Collision ─────────────────────────────────────────

    def check_collisions(self, target) -> list[Projectile]:
        """Check all projectiles against a target.
        Returns list of projectiles that hit (already deactivated).
        """
        hits: list[Projectile] = []
        for proj in self._projectiles:
            if proj.check_collision(target):
                hits.append(proj)
                logger.debug("Projectile hit %s! dmg=%d", target.__class__.__name__, proj.damage)
        return hits

    # ── Per-frame ─────────────────────────────────────────

    def update(self, dt: float):
        """Update all projectiles and remove dead ones."""
        for p in self._projectiles:
            p.update(dt)
        self._projectiles = [p for p in self._projectiles if p.active]

    def draw(self, surface: pygame.Surface):
        """Draw all active projectiles."""
        for p in self._projectiles:
            p.draw(surface)

    def clear(self):
        """Remove all projectiles."""
        self._projectiles.clear()
