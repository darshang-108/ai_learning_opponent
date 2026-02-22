"""
vfx.py  –  Procedural visual-effects helper functions.

All effects are drawn programmatically (no sprites / PNGs).
This module is rendering-only — it never touches game logic.
"""

import pygame
import random
import math
from settings import SCREEN_WIDTH, SCREEN_HEIGHT

# ==============================================================
#  Gradient Background
# ==============================================================

# Pre-rendered gradient surface (built once on first call)
_gradient_cache: pygame.Surface | None = None


def draw_gradient(surface, top_color=(25, 30, 40), bottom_color=(10, 10, 15)):
    """Draw a vertical gradient background.  Cached after first build."""
    global _gradient_cache
    w, h = surface.get_width(), surface.get_height()

    if _gradient_cache is None or _gradient_cache.get_size() != (w, h):
        _gradient_cache = pygame.Surface((w, h))
        for y in range(h):
            ratio = y / h
            r = int(top_color[0] * (1 - ratio) + bottom_color[0] * ratio)
            g = int(top_color[1] * (1 - ratio) + bottom_color[1] * ratio)
            b = int(top_color[2] * (1 - ratio) + bottom_color[2] * ratio)
            pygame.draw.line(_gradient_cache, (r, g, b), (0, y), (w, y))

    surface.blit(_gradient_cache, (0, 0))


# ==============================================================
#  Glow Effect
# ==============================================================

def draw_glow(surface, pos, radius, color):
    """Draw a soft radial glow centred on *pos*.

    Parameters
    ----------
    pos    : (x, y) centre of the glow
    radius : outer radius in pixels
    color  : (r, g, b) base glow colour
    """
    glow_surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    for i in range(radius, 0, -5):
        alpha = int(255 * (i / radius) * 0.2)
        pygame.draw.circle(glow_surface, (*color, alpha), (radius, radius), i)
    surface.blit(glow_surface, (pos[0] - radius, pos[1] - radius))


# ==============================================================
#  Screen Shake
# ==============================================================

class ScreenShake:
    """Lightweight screen-shake manager.

    Usage:
        shake = ScreenShake()
        shake.trigger(intensity=6, duration=0.15)   # on impact
        offset = shake.get_offset(dt)               # each frame
    """

    def __init__(self):
        self._timer = 0.0
        self._intensity = 0

    def trigger(self, intensity: int = 5, duration: float = 0.15):
        """Start a new shake (overwrites any current one)."""
        self._intensity = intensity
        self._timer = duration

    def get_offset(self, dt: float) -> tuple[int, int]:
        """Return (dx, dy) offset for this frame and tick down."""
        if self._timer <= 0:
            return (0, 0)
        self._timer -= dt
        return (
            random.randint(-self._intensity, self._intensity),
            random.randint(-self._intensity, self._intensity),
        )


# ==============================================================
#  Floating Damage Numbers
# ==============================================================

class FloatingText:
    """A single floating damage / info number."""

    def __init__(self, text: str, x: int, y: int, color=(255, 80, 80),
                 duration: float = 1.0, size: int = 22):
        self.text = text
        self.x = float(x)
        self.y = float(y)
        self.color = color
        self.timer = duration
        self.duration = duration
        self.size = size

    def update(self, dt: float):
        """Move upward and tick timer."""
        self.y -= 40 * dt          # float up
        self.timer -= dt

    @property
    def alive(self):
        return self.timer > 0

    def draw(self, surface):
        """Render with fade-out alpha."""
        if self.timer <= 0:
            return
        alpha = max(0, min(255, int(255 * (self.timer / self.duration))))
        font = pygame.font.SysFont(None, self.size)
        txt = font.render(self.text, True, self.color)
        alpha_surf = pygame.Surface(txt.get_size(), pygame.SRCALPHA)
        alpha_surf.blit(txt, (0, 0))
        alpha_surf.set_alpha(alpha)
        surface.blit(alpha_surf, (int(self.x), int(self.y)))


class FloatingTextManager:
    """Manages a list of floating text objects."""

    def __init__(self):
        self._texts: list[FloatingText] = []

    def spawn(self, text: str, x: int, y: int, color=(255, 80, 80),
              duration: float = 1.0, size: int = 24):
        self._texts.append(FloatingText(text, x, y, color, duration, size))

    def update(self, dt: float):
        for t in self._texts:
            t.update(dt)
        self._texts = [t for t in self._texts if t.alive]

    def draw(self, surface):
        for t in self._texts:
            t.draw(surface)


# ==============================================================
#  Procedural Spell / Impact Ring Effects
# ==============================================================

class RingEffect:
    """Expanding ring animation (used for regen pulse, impact, etc.)."""

    def __init__(self, x, y, color, max_radius=40, duration=0.5, width=3):
        self.x = x
        self.y = y
        self.color = color
        self.max_radius = max_radius
        self.duration = duration
        self.width = width
        self.timer = duration

    @property
    def alive(self):
        return self.timer > 0

    def update(self, dt):
        self.timer -= dt

    def draw(self, surface):
        if self.timer <= 0:
            return
        progress = 1.0 - (self.timer / self.duration)
        radius = int(self.max_radius * progress)
        alpha = max(0, int(200 * (self.timer / self.duration)))
        ring_surf = pygame.Surface((self.max_radius * 2, self.max_radius * 2),
                                   pygame.SRCALPHA)
        if radius > 0:
            pygame.draw.circle(ring_surf, (*self.color, alpha),
                               (self.max_radius, self.max_radius),
                               radius, self.width)
        surface.blit(ring_surf, (self.x - self.max_radius,
                                  self.y - self.max_radius))


class EffectsManager:
    """Manages ring / pulse effects."""

    def __init__(self):
        self._effects: list[RingEffect] = []

    def spawn_ring(self, x, y, color, max_radius=40, duration=0.5, width=3):
        self._effects.append(RingEffect(x, y, color, max_radius, duration, width))

    def update(self, dt):
        for e in self._effects:
            e.update(dt)
        self._effects = [e for e in self._effects if e.alive]

    def draw(self, surface):
        for e in self._effects:
            e.draw(surface)


# ==============================================================
#  Slow-Motion / Time-Scale Manager
# ==============================================================

class TimeScaleManager:
    """Applies temporary slow-motion to delta time.

    Usage::

        tsm = TimeScaleManager()
        tsm.trigger(scale=0.3, duration=0.15)
        dt = tsm.apply(raw_dt)
    """

    def __init__(self):
        self.scale = 1.0
        self._timer = 0.0
        self._target_scale = 1.0

    def trigger(self, scale: float = 0.3, duration: float = 0.15):
        """Begin a slow-motion window."""
        self._target_scale = scale
        self.scale = scale
        self._timer = duration

    def apply(self, raw_dt: float) -> float:
        """Tick timer and return scaled dt."""
        if self._timer > 0:
            self._timer -= raw_dt  # tick with real time
            if self._timer <= 0:
                self.scale = 1.0
            return raw_dt * self.scale
        self.scale = 1.0
        return raw_dt

    @property
    def active(self) -> bool:
        return self._timer > 0


# ==============================================================
#  Hit-Stop (Micro Freeze Frame)
# ==============================================================

class HitStop:
    """Pauses movement updates briefly on impact.

    Usage::

        hs = HitStop()
        hs.trigger(0.05)
        if not hs.frozen(raw_dt):
            # do movement updates
    """

    def __init__(self):
        self._timer = 0.0

    def trigger(self, duration: float = 0.05):
        self._timer = duration

    def frozen(self, raw_dt: float) -> bool:
        """Tick and return True while frozen."""
        if self._timer > 0:
            self._timer -= raw_dt
            return True
        return False


# ==============================================================
#  Dynamic Camera Zoom
# ==============================================================

class CameraZoom:
    """Smooth camera scale for dramatic zoom on impacts.

    Usage::

        cam = CameraZoom()
        cam.punch(1.08, decay=0.06)    # on heavy hit
        scaled_surf = cam.apply(world_surface, screen)
    """

    def __init__(self):
        self.scale = 1.0
        self._target = 1.0
        self._decay = 0.06  # lerp speed back to 1.0

    def punch(self, target_scale: float = 1.08, decay: float = 0.06):
        """Set a zoom target (> 1 = zoom in)."""
        self._target = target_scale
        self._decay = decay

    def update(self, dt: float):
        """Interpolate toward target, then ease target back to 1.0."""
        self.scale += (self._target - self.scale) * 0.15
        self._target += (1.0 - self._target) * self._decay

    def apply(self, world_surface: pygame.Surface,
              screen: pygame.Surface) -> None:
        """Scale *world_surface* and blit centred onto *screen*."""
        if abs(self.scale - 1.0) < 0.002:
            screen.blit(world_surface, (0, 0))
            return
        w = int(SCREEN_WIDTH * self.scale)
        h = int(SCREEN_HEIGHT * self.scale)
        scaled = pygame.transform.smoothscale(world_surface, (w, h))
        ox = (w - SCREEN_WIDTH) // 2
        oy = (h - SCREEN_HEIGHT) // 2
        screen.blit(scaled, (-ox, -oy))


# ==============================================================
#  Impact Flash Overlay
# ==============================================================

class ImpactFlash:
    """Full-screen white/colour flash that fades out.

    Usage::

        flash = ImpactFlash()
        flash.trigger(color=(255,255,255), alpha=120, duration=0.1)
        flash.draw(screen, dt)
    """

    def __init__(self):
        self._timer = 0.0
        self._duration = 0.1
        self._max_alpha = 120
        self._color = (255, 255, 255)

    def trigger(self, color=(255, 255, 255), alpha: int = 120,
                duration: float = 0.1):
        self._color = color
        self._max_alpha = alpha
        self._duration = duration
        self._timer = duration

    def draw(self, surface: pygame.Surface, dt: float):
        """Draw and tick.  Safe to call every frame."""
        if self._timer <= 0:
            return
        self._timer -= dt
        frac = max(0.0, self._timer / self._duration)
        alpha = int(self._max_alpha * frac)
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((*self._color, alpha))
        surface.blit(overlay, (0, 0))


# ==============================================================
#  Combo Counter
# ==============================================================

class ComboCounter:
    """Track consecutive player hits and render a combo banner.

    Usage::

        combo = ComboCounter()
        combo.register_hit()          # on each landed hit
        combo.update(dt)
        combo.draw(surface)
    """

    _TIMEOUT = 1.5      # seconds without a hit before reset
    _DISPLAY_DUR = 1.0   # how long the banner stays visible

    def __init__(self):
        self.count = 0
        self._since_last_hit = 0.0
        self._display_timer = 0.0
        self._display_count = 0  # count shown on banner
        self._pulse = 0.0        # scale pulse timer

    def register_hit(self):
        self.count += 1
        self._since_last_hit = 0.0
        if self.count >= 2:
            self._display_count = self.count
            self._display_timer = self._DISPLAY_DUR
            self._pulse = 1.0

    def update(self, dt: float):
        self._since_last_hit += dt
        if self._since_last_hit >= self._TIMEOUT and self.count > 0:
            self.count = 0
        if self._display_timer > 0:
            self._display_timer -= dt
        if self._pulse > 0:
            self._pulse -= dt * 4.0  # decay quickly

    def draw(self, surface: pygame.Surface):
        if self._display_timer <= 0 or self._display_count < 2:
            return
        frac = max(0.0, self._display_timer / self._DISPLAY_DUR)
        alpha = int(255 * frac)
        scale_pulse = 1.0 + max(0.0, self._pulse) * 0.25

        base_size = 42
        size = int(base_size * scale_pulse)
        font = pygame.font.SysFont(None, size, bold=True)
        text = f"{self._display_count} HIT COMBO!"
        txt_surf = font.render(text, True, (255, 220, 60))

        alpha_surf = pygame.Surface(txt_surf.get_size(), pygame.SRCALPHA)
        alpha_surf.blit(txt_surf, (0, 0))
        alpha_surf.set_alpha(alpha)

        cx = surface.get_width() // 2 - alpha_surf.get_width() // 2
        cy = surface.get_height() // 2 - 80
        surface.blit(alpha_surf, (cx, cy))


# ==============================================================
#  Vignette Overlay (subtle dark edges)
# ==============================================================

_vignette_cache: pygame.Surface | None = None


def draw_vignette(surface: pygame.Surface, strength: int = 70):
    """Draw a radial vignette (dark edges) over the screen.  Cached."""
    global _vignette_cache
    w, h = surface.get_size()
    if _vignette_cache is None or _vignette_cache.get_size() != (w, h):
        _vignette_cache = pygame.Surface((w, h), pygame.SRCALPHA)
        cx, cy = w // 2, h // 2
        max_dist = math.hypot(cx, cy)
        # Build with concentric rectangles for speed
        for ring in range(0, int(max_dist), 4):
            frac = ring / max_dist
            # only darken outer 40%
            if frac < 0.55:
                continue
            alpha = int(strength * ((frac - 0.55) / 0.45) ** 1.5)
            alpha = min(alpha, strength)
            rect = pygame.Rect(cx - ring, cy - ring, ring * 2, ring * 2)
            pygame.draw.rect(_vignette_cache, (0, 0, 0, alpha), rect, 4)
    surface.blit(_vignette_cache, (0, 0))


# ==============================================================
#  Final-Hit Cinematic Sequence
# ==============================================================

class FinalHitCinematic:
    """Orchestrates slow-mo + flash + shake + zoom + text on the killing blow.

    The caller triggers it, then each frame calls ``update(dt)`` and
    ``draw(surface)``.  While ``active`` is True the game should skip
    normal game-over overlay.
    """

    def __init__(self):
        self.active = False
        self._timer = 0.0
        self._duration = 1.5
        self._phase = ""  # "flash" | "hold" | "fade"

    def trigger(self, screen_shake: ScreenShake,
                time_scale: 'TimeScaleManager',
                camera_zoom: 'CameraZoom',
                impact_flash: 'ImpactFlash'):
        """Kick off the sequence by poking all relevant systems."""
        self.active = True
        self._timer = self._duration
        self._phase = "flash"

        # Dramatic slow-mo
        time_scale.trigger(scale=0.25, duration=0.4)
        # Strong shake
        screen_shake.trigger(intensity=10, duration=0.3)
        # Zoom in
        camera_zoom.punch(target_scale=1.12, decay=0.02)
        # Red flash
        impact_flash.trigger(color=(200, 40, 40), alpha=160, duration=0.2)

    def update(self, dt: float):
        if not self.active:
            return
        self._timer -= dt
        if self._timer <= 0:
            self.active = False

    def draw(self, surface: pygame.Surface):
        if not self.active:
            return
        frac = max(0.0, self._timer / self._duration)
        alpha = int(255 * min(1.0, (1.0 - frac) * 3))  # fade in quickly

        font = pygame.font.SysFont(None, 72, bold=True)
        txt = font.render("F I N I S H !", True, (255, 60, 60))
        txt_alpha = pygame.Surface(txt.get_size(), pygame.SRCALPHA)
        txt_alpha.blit(txt, (0, 0))
        txt_alpha.set_alpha(alpha)

        cx = surface.get_width() // 2 - txt.get_width() // 2
        cy = surface.get_height() // 2 - 20
        surface.blit(txt_alpha, (cx, cy))


# ==============================================================
#  Archetype Fade-In Text
# ==============================================================

class ArchetypeBanner:
    """Show 'Enemy Archetype: X' that fades out over 2 seconds."""

    def __init__(self, text: str, duration: float = 2.5):
        self._text = text
        self._timer = duration
        self._duration = duration

    def update(self, dt: float):
        if self._timer > 0:
            self._timer -= dt

    @property
    def active(self) -> bool:
        return self._timer > 0

    def draw(self, surface: pygame.Surface):
        if self._timer <= 0:
            return
        frac = self._timer / self._duration
        alpha = int(255 * min(1.0, frac * 2))  # full alpha first half, fade second

        font = pygame.font.SysFont(None, 36, bold=True)
        txt = font.render(self._text, True, (200, 200, 255))
        alpha_surf = pygame.Surface(txt.get_size(), pygame.SRCALPHA)
        alpha_surf.blit(txt, (0, 0))
        alpha_surf.set_alpha(alpha)

        cx = surface.get_width() // 2 - txt.get_width() // 2
        surface.blit(alpha_surf, (cx, 70))
