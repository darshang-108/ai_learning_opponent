"""
vfx_system.py – Procedural visual effects system.

All effects are physics-based particles – no sprite animations.

Implements:
- Blood particle system
- Weapon trail effect
- Aura effects for buffs
- Impact flash particles
- Stagger knockback impulse visuals

Particles use velocity + gravity + fade for realism.
"""

from __future__ import annotations

import math
import random
import pygame
from settings import (
    PARTICLE_GRAVITY, PARTICLE_MAX_COUNT,
    BLOOD_PARTICLE_COUNT, BLOOD_PARTICLE_SPEED,
    TRAIL_SEGMENT_LIFETIME, AURA_PARTICLE_COUNT,
    SCREEN_WIDTH, SCREEN_HEIGHT,
)


# ══════════════════════════════════════════════════════════
#  Base Particle
# ══════════════════════════════════════════════════════════

class Particle:
    """Physics-based particle with velocity, gravity, and fade."""

    __slots__ = (
        "x", "y", "vx", "vy", "color", "size",
        "lifetime", "timer", "gravity", "fade",
        "shrink", "drag",
    )

    def __init__(self, x: float, y: float, vx: float, vy: float,
                 color: tuple, size: float = 3.0,
                 lifetime: float = 0.8, gravity: float = PARTICLE_GRAVITY,
                 fade: bool = True, shrink: bool = True,
                 drag: float = 0.98):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
        self.size = size
        self.lifetime = lifetime
        self.timer = lifetime
        self.gravity = gravity
        self.fade = fade
        self.shrink = shrink
        self.drag = drag

    @property
    def alive(self) -> bool:
        return self.timer > 0 and self.size > 0.2

    @property
    def progress(self) -> float:
        return 1.0 - max(0.0, self.timer / self.lifetime)

    def update(self, dt: float):
        self.timer -= dt
        # Physics
        self.vy += self.gravity * dt
        self.vx *= self.drag
        self.vy *= self.drag
        self.x += self.vx * dt
        self.y += self.vy * dt
        # Shrink
        if self.shrink:
            self.size = max(0.0, self.size * (1.0 - dt * 2.5))

    def draw(self, surface: pygame.Surface):
        if not self.alive:
            return
        alpha = 255
        if self.fade:
            alpha = int(255 * max(0.0, self.timer / self.lifetime))
        sz = max(1, int(self.size))
        # Use a small surface for alpha support
        ps = pygame.Surface((sz * 2, sz * 2), pygame.SRCALPHA)
        c = (*self.color[:3], min(255, alpha))
        pygame.draw.circle(ps, c, (sz, sz), sz)
        surface.blit(ps, (int(self.x) - sz, int(self.y) - sz))


# ══════════════════════════════════════════════════════════
#  Trail Segment (for weapon trails)
# ══════════════════════════════════════════════════════════

class TrailSegment:
    """A fading line segment for weapon trail effects."""

    __slots__ = ("x1", "y1", "x2", "y2", "color", "width",
                 "lifetime", "timer")

    def __init__(self, x1: float, y1: float, x2: float, y2: float,
                 color: tuple, width: int = 3,
                 lifetime: float = TRAIL_SEGMENT_LIFETIME):
        self.x1, self.y1 = x1, y1
        self.x2, self.y2 = x2, y2
        self.color = color
        self.width = width
        self.lifetime = lifetime
        self.timer = lifetime

    @property
    def alive(self) -> bool:
        return self.timer > 0

    def update(self, dt: float):
        self.timer -= dt

    def draw(self, surface: pygame.Surface):
        if not self.alive:
            return
        frac = max(0.0, self.timer / self.lifetime)
        alpha = int(200 * frac)
        w = max(1, int(self.width * frac))
        trail_surf = pygame.Surface(
            (SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA,
        )
        c = (*self.color[:3], alpha)
        pygame.draw.line(trail_surf, c,
                         (int(self.x1), int(self.y1)),
                         (int(self.x2), int(self.y2)), w)
        surface.blit(trail_surf, (0, 0))


# ══════════════════════════════════════════════════════════
#  VFX Manager
# ══════════════════════════════════════════════════════════

class VFXSystem:
    """Central manager for all procedural visual effects.

    Call ``update(dt)`` and ``draw(surface)`` each frame.
    """

    def __init__(self):
        self._particles: list[Particle] = []
        self._trails: list[TrailSegment] = []
        self._flashes: list[_ImpactFlashParticle] = []

    # ── Spawners ──────────────────────────────────────────

    def spawn_blood(self, x: float, y: float,
                    direction: int = 1, count: int = BLOOD_PARTICLE_COUNT):
        """Burst of blood particles on hit."""
        for _ in range(count):
            angle = random.uniform(-0.8, 0.8) + (0 if direction > 0 else math.pi)
            speed = random.uniform(80, BLOOD_PARTICLE_SPEED)
            vx = math.cos(angle) * speed * direction
            vy = math.sin(angle) * speed - random.uniform(40, 120)
            color = random.choice([
                (180, 20, 20), (200, 40, 30), (150, 10, 10), (220, 50, 40),
            ])
            size = random.uniform(1.5, 4.0)
            lifetime = random.uniform(0.3, 0.8)
            self._add_particle(Particle(
                x, y, vx, vy, color, size, lifetime,
                gravity=PARTICLE_GRAVITY * 0.8, drag=0.96,
            ))

    def spawn_impact_sparks(self, x: float, y: float,
                            color: tuple = (255, 220, 80),
                            count: int = 8):
        """Bright sparks on impact."""
        for _ in range(count):
            angle = random.uniform(0, math.pi * 2)
            speed = random.uniform(100, 250)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            size = random.uniform(1.0, 2.5)
            lifetime = random.uniform(0.15, 0.35)
            self._add_particle(Particle(
                x, y, vx, vy, color, size, lifetime,
                gravity=PARTICLE_GRAVITY * 0.3, drag=0.92,
            ))

    def spawn_parry_flash(self, x: float, y: float):
        """Large bright flash + ring + sparks for perfect parry."""
        # Central flash
        self._flashes.append(_ImpactFlashParticle(x, y, (255, 255, 200), 40, 0.25))
        # Ring of sparks
        for i in range(16):
            angle = (math.pi * 2 / 16) * i
            speed = random.uniform(150, 300)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            self._add_particle(Particle(
                x, y, vx, vy, (255, 255, 180), 2.5, 0.3,
                gravity=0, drag=0.90,
            ))

    def spawn_weapon_trail(self, x1: float, y1: float,
                           x2: float, y2: float,
                           color: tuple = (200, 210, 230)):
        """Add a weapon trail segment."""
        self._trails.append(TrailSegment(x1, y1, x2, y2, color, width=3))

    def spawn_aura_particles(self, cx: float, cy: float,
                             color: tuple, count: int = 3,
                             radius: float = 24):
        """Ambient aura particles rising around a character."""
        for _ in range(count):
            angle = random.uniform(0, math.pi * 2)
            dist = random.uniform(radius * 0.5, radius)
            px = cx + math.cos(angle) * dist
            py = cy + math.sin(angle) * dist
            vx = random.uniform(-10, 10)
            vy = random.uniform(-60, -20)
            size = random.uniform(1.0, 2.5)
            lifetime = random.uniform(0.4, 0.8)
            self._add_particle(Particle(
                px, py, vx, vy, color, size, lifetime,
                gravity=-20, drag=0.97,
            ))

    def spawn_execution_burst(self, x: float, y: float):
        """Dramatic burst for execution finisher."""
        # Large central flash
        self._flashes.append(_ImpactFlashParticle(x, y, (255, 80, 40), 60, 0.4))
        # Explosion of particles
        for _ in range(30):
            angle = random.uniform(0, math.pi * 2)
            speed = random.uniform(100, 400)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            color = random.choice([
                (255, 200, 60), (255, 120, 40), (255, 80, 20), (255, 255, 180),
            ])
            size = random.uniform(2.0, 5.0)
            lifetime = random.uniform(0.3, 0.7)
            self._add_particle(Particle(
                x, y, vx, vy, color, size, lifetime,
                gravity=PARTICLE_GRAVITY * 0.5, drag=0.94,
            ))

    def spawn_stagger_debris(self, x: float, y: float, direction: int = 1):
        """Small debris particles on stagger knockback."""
        for _ in range(6):
            vx = random.uniform(30, 100) * direction
            vy = random.uniform(-80, -20)
            color = random.choice([
                (160, 160, 160), (120, 120, 120), (100, 90, 80),
            ])
            self._add_particle(Particle(
                x, y, vx, vy, color, random.uniform(1.0, 2.5), 0.4,
                gravity=PARTICLE_GRAVITY, drag=0.95,
            ))

    def spawn_death_particles(self, x: float, y: float, color: tuple):
        """Dramatic death particle spray."""
        for _ in range(25):
            angle = random.uniform(0, math.pi * 2)
            speed = random.uniform(50, 200)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed - 50
            size = random.uniform(2.0, 4.5)
            lifetime = random.uniform(0.5, 1.2)
            brightness = random.uniform(0.5, 1.0)
            pc = tuple(int(c * brightness) for c in color[:3])
            self._add_particle(Particle(
                x, y, vx, vy, pc, size, lifetime,
                gravity=PARTICLE_GRAVITY * 0.6, drag=0.95,
            ))

    def spawn_heal_sparkle(self, x: float, y: float, count: int = 6):
        """Green sparkles for healing / regen."""
        for _ in range(count):
            vx = random.uniform(-30, 30)
            vy = random.uniform(-80, -30)
            color = random.choice([
                (80, 255, 80), (60, 220, 60), (100, 255, 120),
            ])
            self._add_particle(Particle(
                x + random.uniform(-12, 12), y,
                vx, vy, color, random.uniform(1.5, 3.0), 0.6,
                gravity=-40, drag=0.97,
            ))

    def spawn_magic_impact(self, x: float, y: float,
                           color: tuple = (180, 120, 255)):
        """Purple magic burst when a projectile hits."""
        # Central flash
        self._flashes.append(_ImpactFlashParticle(x, y, color, 30, 0.2))
        # Scattered sparks
        for _ in range(14):
            angle = random.uniform(0, math.pi * 2)
            speed = random.uniform(80, 220)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            c = (
                min(255, color[0] + random.randint(-30, 30)),
                min(255, color[1] + random.randint(-30, 30)),
                min(255, color[2] + random.randint(-30, 30)),
            )
            self._add_particle(Particle(
                x, y, vx, vy, c, random.uniform(1.5, 3.5), 0.35,
                gravity=PARTICLE_GRAVITY * 0.3, drag=0.92,
            ))

    def spawn_hit_flash(self, x: float, y: float,
                        color: tuple = (255, 60, 60)):
        """Short red flash on the character when hit (damage feedback)."""
        self._flashes.append(_ImpactFlashParticle(x, y, color, 20, 0.12))

    # ── Internal ──────────────────────────────────────────

    def _add_particle(self, p: Particle):
        self._particles.append(p)
        # Enforce max count
        if len(self._particles) > PARTICLE_MAX_COUNT:
            self._particles = self._particles[-PARTICLE_MAX_COUNT:]

    # ── Per-frame ─────────────────────────────────────────

    def update(self, dt: float):
        for p in self._particles:
            p.update(dt)
        self._particles = [p for p in self._particles if p.alive]

        for t in self._trails:
            t.update(dt)
        self._trails = [t for t in self._trails if t.alive]

        for f in self._flashes:
            f.update(dt)
        self._flashes = [f for f in self._flashes if f.alive]

    def draw(self, surface: pygame.Surface):
        for t in self._trails:
            t.draw(surface)
        for p in self._particles:
            p.draw(surface)
        for f in self._flashes:
            f.draw(surface)

    def clear(self):
        self._particles.clear()
        self._trails.clear()
        self._flashes.clear()


# ══════════════════════════════════════════════════════════
#  Impact Flash Particle (expanding circle)
# ══════════════════════════════════════════════════════════

class _ImpactFlashParticle:
    """Expanding + fading circle for impact flashes."""

    __slots__ = ("x", "y", "color", "max_radius", "lifetime", "timer")

    def __init__(self, x: float, y: float, color: tuple,
                 max_radius: float, lifetime: float):
        self.x = x
        self.y = y
        self.color = color
        self.max_radius = max_radius
        self.lifetime = lifetime
        self.timer = lifetime

    @property
    def alive(self) -> bool:
        return self.timer > 0

    def update(self, dt: float):
        self.timer -= dt

    def draw(self, surface: pygame.Surface):
        if not self.alive:
            return
        progress = 1.0 - (self.timer / self.lifetime)
        radius = int(self.max_radius * progress)
        alpha = int(200 * (self.timer / self.lifetime))
        if radius <= 0:
            return
        flash_surf = pygame.Surface(
            (self.max_radius * 2 + 4, self.max_radius * 2 + 4),
            pygame.SRCALPHA,
        )
        center = (int(self.max_radius + 2), int(self.max_radius + 2))
        # Filled center
        pygame.draw.circle(flash_surf, (*self.color[:3], alpha // 2),
                           center, max(1, radius // 2))
        # Ring
        pygame.draw.circle(flash_surf, (*self.color[:3], alpha),
                           center, radius, max(1, 3))
        surface.blit(flash_surf,
                     (int(self.x - self.max_radius - 2),
                      int(self.y - self.max_radius - 2)))
