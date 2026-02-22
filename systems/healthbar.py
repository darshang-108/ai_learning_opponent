"""healthbar.py - Draws smoothly animated health bars for player and enemy."""

import pygame
import random
from settings import (
    WHITE, GREEN, DARK_GREEN, GRAY,
    HEALTHBAR_WIDTH, HEALTHBAR_HEIGHT, HEALTHBAR_Y,
    PLAYER_HB_X, ENEMY_HB_X, SMALL_FONT_SIZE,
)

# ── Smooth display HP state (persists between frames) ─────
# keyed by id(entity) → {displayed_hp, prev_hp, shake_timer}
_bar_state: dict[int, dict] = {}

_LERP_SPEED = 0.08  # interpolation factor per frame
_SHAKE_DURATION = 0.25  # seconds of bar shake on damage
_SHAKE_INTENSITY = 3     # pixels


def draw_health_bars(surface, player, enemy, dt: float = 0.016):
    """Render both smoothly-animated health bars at the top of the screen."""
    font = pygame.font.SysFont(None, SMALL_FONT_SIZE)

    # ── Player health bar (left side) ─────────────────────
    _draw_bar(
        surface, PLAYER_HB_X, HEALTHBAR_Y,
        player.hp, player.max_hp, GREEN, id(player), dt,
    )
    label = font.render("Player", True, WHITE)
    surface.blit(label, (PLAYER_HB_X, HEALTHBAR_Y - 18))

    # ── Enemy health bar (right side) ─────────────────────
    _draw_bar(
        surface, ENEMY_HB_X, HEALTHBAR_Y,
        enemy.hp, enemy.max_hp, DARK_GREEN, id(enemy), dt,
    )
    label = font.render("Enemy", True, WHITE)
    surface.blit(label, (ENEMY_HB_X, HEALTHBAR_Y - 18))


def _draw_bar(surface, x, y, current_hp, max_hp, fill_color, entity_id,
              dt: float):
    """Draw a single smoothly-animated health bar with glow + damage shake."""
    # Initialise state dict for this entity
    if entity_id not in _bar_state:
        _bar_state[entity_id] = {
            "displayed": float(current_hp),
            "prev_hp": current_hp,
            "shake_timer": 0.0,
        }
    st = _bar_state[entity_id]

    # Detect HP drop → trigger shake
    if current_hp < st["prev_hp"]:
        st["shake_timer"] = _SHAKE_DURATION
    st["prev_hp"] = current_hp

    # Tick shake timer
    if st["shake_timer"] > 0:
        st["shake_timer"] -= dt
        shake_x = random.randint(-_SHAKE_INTENSITY, _SHAKE_INTENSITY)
        shake_y = random.randint(-_SHAKE_INTENSITY, _SHAKE_INTENSITY)
    else:
        shake_x, shake_y = 0, 0

    bx = x + shake_x
    by = y + shake_y

    # Smoothly interpolate displayed HP toward actual HP
    st["displayed"] += (current_hp - st["displayed"]) * _LERP_SPEED
    displayed = st["displayed"]

    radius = 6  # corner radius

    # Subtle glow behind bar
    glow_surf = pygame.Surface(
        (HEALTHBAR_WIDTH + 16, HEALTHBAR_HEIGHT + 16), pygame.SRCALPHA,
    )
    glow_alpha = int(40 * max(0.0, displayed / max_hp))
    pygame.draw.rect(
        glow_surf, (*fill_color, glow_alpha),
        glow_surf.get_rect(), border_radius=radius + 4,
    )
    surface.blit(glow_surf, (bx - 8, by - 8))

    # Dark shadow (offset slightly down-right)
    shadow_rect = pygame.Rect(bx + 2, by + 2, HEALTHBAR_WIDTH, HEALTHBAR_HEIGHT)
    pygame.draw.rect(surface, (15, 15, 15), shadow_rect, border_radius=radius)

    # Background
    bg_rect = pygame.Rect(bx, by, HEALTHBAR_WIDTH, HEALTHBAR_HEIGHT)
    pygame.draw.rect(surface, GRAY, bg_rect, border_radius=radius)

    # Fill proportional to smoothed HP
    fill_frac = max(0.0, min(1.0, displayed / max_hp))
    fill_width = int(HEALTHBAR_WIDTH * fill_frac)
    if fill_width > 0:
        fill_rect = pygame.Rect(bx, by, fill_width, HEALTHBAR_HEIGHT)
        pygame.draw.rect(surface, fill_color, fill_rect, border_radius=radius)

    # Border
    pygame.draw.rect(surface, (180, 180, 180), bg_rect, 2, border_radius=radius)

    # HP text centred on bar
    hp_text = font_small().render(f"{current_hp}/{max_hp}", True, WHITE)
    tx = bx + (HEALTHBAR_WIDTH - hp_text.get_width()) // 2
    ty = by + (HEALTHBAR_HEIGHT - hp_text.get_height()) // 2
    surface.blit(hp_text, (tx, ty))


def _clear_cache():
    """Reset the displayed-HP cache (call on match reset)."""
    _bar_state.clear()


# Small font helper (cached after first call)
_font_cache = None

def font_small():
    global _font_cache
    if _font_cache is None:
        _font_cache = pygame.font.SysFont(None, SMALL_FONT_SIZE)
    return _font_cache
