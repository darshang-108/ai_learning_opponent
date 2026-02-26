"""
systems/character_select.py - Grid-based character selection screen.

Displays a 2x3 grid of player roles with keyboard navigation.
Each role is data-driven from PLAYER_ROLES config.

Usage:
    screen = CharacterSelectScreen(surface, PLAYER_ROLES)
    # in game loop:
    for event in pygame.event.get():
        result = screen.handle_input(event)
        if result == "confirmed":
            role = screen.get_selected_role()
        elif result == "back":
            # return to menu
    screen.update(dt)
    screen.draw()
"""

import math
import pygame
from settings import SCREEN_WIDTH, SCREEN_HEIGHT, WHITE

# ── Role → BuildDifficultyAdapter mapping ─────────────────

_ROLE_TO_BUILD_TYPE: dict[str, str] = {
    "Mage":      "MAGE",
    "Berserker":  "DEXTERITY",
    "Tactician":  "BALANCED",
    "Guardian":   "TANK",
    "Assassin":   "DEXTERITY",
    "Adaptive":   "BALANCED",
}


def role_to_build_type(role_name: str) -> str:
    """Map a PLAYER_ROLES key to a BuildDifficultyAdapter build type."""
    return _ROLE_TO_BUILD_TYPE.get(role_name, "BALANCED")

# ── Role definitions ──────────────────────────────────────

PLAYER_ROLES = {
    "Mage": {
        "damage": 8,
        "speed": 3,
        "defense": 4,
        "description": "Ranged caster with powerful projectiles.",
    },
    "Berserker": {
        "damage": 14,
        "speed": 5,
        "defense": 3,
        "description": "Aggressive brawler with high damage output.",
    },
    "Tactician": {
        "damage": 9,
        "speed": 4,
        "defense": 7,
        "description": "Calculated fighter who exploits openings.",
    },
    "Guardian": {
        "damage": 6,
        "speed": 3,
        "defense": 10,
        "description": "Tanky defender with unmatched blocking.",
    },
    "Assassin": {
        "damage": 12,
        "speed": 7,
        "defense": 2,
        "description": "Swift striker who relies on evasion.",
    },
    "Adaptive": {
        "damage": 9,
        "speed": 5,
        "defense": 6,
        "description": "Balanced all-rounder that adjusts on the fly.",
    },
}

# ── Layout constants ──────────────────────────────────────

_COLS = 3
_ROWS = 2
_CARD_W = 180
_CARD_H = 160
_PAD_X = 24
_PAD_Y = 20

# ── Colors ────────────────────────────────────────────────

_BG = (20, 20, 28)
_CARD_BG = (40, 42, 54)
_CARD_SELECTED = (70, 80, 120)
_CARD_BORDER = (90, 90, 110)
_CARD_HIGHLIGHT = (130, 160, 255)
_TITLE_COLOR = WHITE
_NAME_COLOR = (220, 220, 240)
_STAT_COLOR = (170, 180, 200)
_DESC_COLOR = (140, 145, 160)
_HINT_COLOR = (110, 110, 120)

# ── Stat bar colors ───────────────────────────────────────

_BAR_DAMAGE = (220, 70, 70)
_BAR_SPEED = (70, 200, 120)
_BAR_DEFENSE = (80, 140, 255)
_BAR_BG = (50, 50, 60)
_DESC_LINE_SPACING = 2         # px between wrapped description lines


# ══════════════════════════════════════════════════════════
#  Text Wrapping Utility
# ══════════════════════════════════════════════════════════

def render_multiline_text(
    text: str,
    font: pygame.font.Font,
    color: tuple[int, int, int],
    max_width: int,
) -> list[pygame.Surface]:
    """Word-wrap *text* and return a list of rendered line surfaces.

    Each surface is guaranteed to be <= *max_width* pixels wide.
    Words that individually exceed *max_width* are force-placed on
    their own line (no infinite loop).
    """
    words = text.split()
    if not words:
        return []

    lines: list[pygame.Surface] = []
    current_words: list[str] = []

    for word in words:
        # Test width with the new word appended
        test_line = " ".join(current_words + [word])
        if font.size(test_line)[0] <= max_width:
            current_words.append(word)
        else:
            # Flush current line (if any)
            if current_words:
                lines.append(font.render(" ".join(current_words), True, color))
            current_words = [word]

    # Flush remaining words
    if current_words:
        lines.append(font.render(" ".join(current_words), True, color))

    return lines

# ── Animation tuning ─────────────────────────────────────

_FADE_IN_DURATION = 0.35       # seconds for screen fade-in
_SELECT_LERP_SPEED = 8.0       # interpolation speed (higher = snappier)
_GLOW_BASE = 0.55              # base glow strength (0-1)
_GLOW_AMPLITUDE = 0.45         # pulse amplitude
_GLOW_SPEED = 4.0              # radians/sec for sin pulse
_SCALE_SELECTED = 1.05         # scale factor for selected card
_SCALE_NORMAL = 1.0
_SHADOW_OFFSET = 4             # pixels
_SHADOW_ALPHA = 50             # 0-255


# ══════════════════════════════════════════════════════════
#  Animation State (per-card, separated from layout)
# ══════════════════════════════════════════════════════════

class _CardAnim:
    """Holds time-interpolated animation state for one card."""

    __slots__ = ("select_t", "scale", "bg_r", "bg_g", "bg_b",
                 "border_r", "border_g", "border_b")

    def __init__(self) -> None:
        self.select_t: float = 0.0  # 0 = unselected, 1 = fully selected
        self.scale: float = _SCALE_NORMAL
        self.bg_r: float = float(_CARD_BG[0])
        self.bg_g: float = float(_CARD_BG[1])
        self.bg_b: float = float(_CARD_BG[2])
        self.border_r: float = float(_CARD_BORDER[0])
        self.border_g: float = float(_CARD_BORDER[1])
        self.border_b: float = float(_CARD_BORDER[2])

    def update(self, selected: bool, dt: float) -> None:
        """Advance interpolation towards target state."""
        target_t = 1.0 if selected else 0.0
        self.select_t += (target_t - self.select_t) * min(1.0, _SELECT_LERP_SPEED * dt)

        # Scale
        target_scale = _SCALE_SELECTED if selected else _SCALE_NORMAL
        self.scale += (target_scale - self.scale) * min(1.0, _SELECT_LERP_SPEED * dt)

        # Background color lerp
        tgt_bg = _CARD_SELECTED if selected else _CARD_BG
        self.bg_r += (tgt_bg[0] - self.bg_r) * min(1.0, _SELECT_LERP_SPEED * dt)
        self.bg_g += (tgt_bg[1] - self.bg_g) * min(1.0, _SELECT_LERP_SPEED * dt)
        self.bg_b += (tgt_bg[2] - self.bg_b) * min(1.0, _SELECT_LERP_SPEED * dt)

        # Border color lerp
        tgt_bd = _CARD_HIGHLIGHT if selected else _CARD_BORDER
        self.border_r += (tgt_bd[0] - self.border_r) * min(1.0, _SELECT_LERP_SPEED * dt)
        self.border_g += (tgt_bd[1] - self.border_g) * min(1.0, _SELECT_LERP_SPEED * dt)
        self.border_b += (tgt_bd[2] - self.border_b) * min(1.0, _SELECT_LERP_SPEED * dt)

    @property
    def bg_color(self) -> tuple[int, int, int]:
        return (int(self.bg_r), int(self.bg_g), int(self.bg_b))

    @property
    def border_color(self) -> tuple[int, int, int]:
        return (int(self.border_r), int(self.border_g), int(self.border_b))


# ══════════════════════════════════════════════════════════
#  Character Select Screen
# ══════════════════════════════════════════════════════════

class CharacterSelectScreen:
    """2x3 grid character select with keyboard navigation and animated polish."""

    def __init__(self, screen: pygame.Surface, roles_config: dict | None = None):
        self.screen = screen
        self.roles = roles_config or PLAYER_ROLES
        self._role_names: list[str] = list(self.roles.keys())
        self._index: int = 0
        self._confirmed: bool = False

        # Fonts (created once)
        self._font_title = pygame.font.SysFont(None, 48)
        self._font_name = pygame.font.SysFont(None, 28)
        self._font_stat = pygame.font.SysFont(None, 20)
        self._font_desc = pygame.font.SysFont(None, 18)
        self._font_hint = pygame.font.SysFont(None, 22)

        # Pre-compute grid origin so cards are centered
        grid_w = _COLS * _CARD_W + (_COLS - 1) * _PAD_X
        grid_h = _ROWS * _CARD_H + (_ROWS - 1) * _PAD_Y
        self._grid_x = (SCREEN_WIDTH - grid_w) // 2
        self._grid_y = (SCREEN_HEIGHT - grid_h) // 2 + 30  # offset for title

        # ── Animation state ───────────────────────────────
        self._time: float = 0.0
        self._fade_alpha: float = 255.0  # starts opaque black → fades to 0
        self._card_anims: list[_CardAnim] = [
            _CardAnim() for _ in self._role_names
        ]
        # Pre-create the fade overlay surface once
        self._fade_surf = pygame.Surface(
            (SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA,
        )
        # Pre-create a reusable shadow surface (card-sized, semi-transparent)
        self._shadow_surf = pygame.Surface(
            (_CARD_W + 8, _CARD_H + 8), pygame.SRCALPHA,
        )

        # Pre-cache wrapped description surfaces per role (avoids per-frame work)
        desc_max_w = _CARD_W - 16
        self._desc_cache: dict[str, list[pygame.Surface]] = {}
        for rname, rdata in self.roles.items():
            desc = rdata.get("description", "")
            self._desc_cache[rname] = render_multiline_text(
                desc, self._font_desc, _DESC_COLOR, desc_max_w,
            )

    # ── public API ────────────────────────────────────────

    def update(self, dt: float) -> None:
        """Advance all time-based animation state."""
        self._time += dt

        # Fade-in
        if self._fade_alpha > 0.0:
            self._fade_alpha = max(
                0.0, self._fade_alpha - (255.0 / _FADE_IN_DURATION) * dt,
            )

        # Per-card animation
        for i, anim in enumerate(self._card_anims):
            anim.update(i == self._index, dt)

    def draw(self) -> None:
        """Render the full character select screen."""
        self.screen.fill(_BG)
        self._draw_title()
        self._draw_grid()
        self._draw_hint()

        # Fade-in overlay
        if self._fade_alpha > 0.5:
            alpha = int(self._fade_alpha)
            self._fade_surf.fill((20, 20, 28, alpha))
            self.screen.blit(self._fade_surf, (0, 0))

        pygame.display.flip()

    def handle_input(self, event: pygame.event.Event) -> str | None:
        """Process a single pygame event.

        Returns
        -------
        "confirmed" – player pressed Enter on a role.
        "back"      – player pressed ESC.
        None        – event consumed or irrelevant.
        """
        if event.type != pygame.KEYDOWN:
            return None

        if event.key == pygame.K_LEFT:
            self._move(-1, 0)
        elif event.key == pygame.K_RIGHT:
            self._move(1, 0)
        elif event.key == pygame.K_UP:
            self._move(0, -1)
        elif event.key == pygame.K_DOWN:
            self._move(0, 1)
        elif event.key == pygame.K_RETURN:
            self._confirmed = True
            return "confirmed"
        elif event.key == pygame.K_ESCAPE:
            return "back"

        return None

    def get_selected_role(self) -> dict | None:
        """Return the confirmed role dict, or None if not yet confirmed.

        The returned dict contains the role name under ``"name"``
        along with all stat keys (damage, speed, defense, description).
        """
        if not self._confirmed:
            return None
        name = self._role_names[self._index]
        return {"name": name, **self.roles[name]}

    # ── navigation helpers ────────────────────────────────

    def _move(self, dx: int, dy: int) -> None:
        """Move selection cursor by *dx* columns and *dy* rows."""
        col = self._index % _COLS
        row = self._index // _COLS

        col = max(0, min(_COLS - 1, col + dx))
        row = max(0, min(_ROWS - 1, row + dy))

        new_index = row * _COLS + col
        if new_index < len(self._role_names):
            self._index = new_index

    # ── drawing helpers ───────────────────────────────────

    def _draw_title(self) -> None:
        title = self._font_title.render("Choose Your Fighter", True, _TITLE_COLOR)
        x = (SCREEN_WIDTH - title.get_width()) // 2
        self.screen.blit(title, (x, 24))

    def _draw_hint(self) -> None:
        hint = self._font_hint.render(
            "Arrow Keys: Navigate  |  Enter: Confirm  |  ESC: Back",
            True,
            _HINT_COLOR,
        )
        x = (SCREEN_WIDTH - hint.get_width()) // 2
        y = SCREEN_HEIGHT - 36
        self.screen.blit(hint, (x, y))

    def _draw_grid(self) -> None:
        for i, name in enumerate(self._role_names):
            row = i // _COLS
            col = i % _COLS
            x = self._grid_x + col * (_CARD_W + _PAD_X)
            y = self._grid_y + row * (_CARD_H + _PAD_Y)
            self._draw_card(x, y, name, self.roles[name], self._card_anims[i])

    # ── card rendering ────────────────────────────────────

    def _draw_card(
        self,
        cx: int,
        cy: int,
        name: str,
        stats: dict,
        anim: _CardAnim,
    ) -> None:
        """Draw a single role card centered on its grid cell, with animation."""
        scale = anim.scale
        sel_t = anim.select_t  # 0..1 blend factor

        # Scaled card dimensions
        sw = int(_CARD_W * scale)
        sh = int(_CARD_H * scale)

        # Offset so the card stays centred in its cell despite scaling
        x = cx - (sw - _CARD_W) // 2
        y = cy - (sh - _CARD_H) // 2

        # ── Drop shadow ──────────────────────────────────
        if sel_t > 0.01:
            shadow_alpha = int(_SHADOW_ALPHA * sel_t)
            self._shadow_surf.fill((0, 0, 0, 0))
            pygame.draw.rect(
                self._shadow_surf, (0, 0, 0, shadow_alpha),
                (0, 0, sw, sh), border_radius=8,
            )
            self.screen.blit(
                self._shadow_surf,
                (x + _SHADOW_OFFSET, y + _SHADOW_OFFSET),
            )

        # ── Pulsing glow (outer border bloom) ────────────
        if sel_t > 0.01:
            glow_strength = _GLOW_BASE + _GLOW_AMPLITUDE * math.sin(self._time * _GLOW_SPEED)
            glow_alpha = int(255 * glow_strength * sel_t)
            glow_alpha = max(0, min(255, glow_alpha))
            glow_pad = 4
            glow_rect = pygame.Rect(
                x - glow_pad, y - glow_pad,
                sw + glow_pad * 2, sh + glow_pad * 2,
            )
            glow_surf = pygame.Surface(
                (glow_rect.width, glow_rect.height), pygame.SRCALPHA,
            )
            glow_color = (*_CARD_HIGHLIGHT, glow_alpha)
            pygame.draw.rect(
                glow_surf, glow_color,
                (0, 0, glow_rect.width, glow_rect.height),
                width=3, border_radius=10,
            )
            self.screen.blit(glow_surf, glow_rect.topleft)

        # ── Card background (smooth color) ───────────────
        card_rect = pygame.Rect(x, y, sw, sh)
        pygame.draw.rect(self.screen, anim.bg_color, card_rect, border_radius=8)

        # ── Border (smooth color + width) ────────────────
        border_w = max(1, int(1 + 2 * sel_t))
        pygame.draw.rect(
            self.screen, anim.border_color, card_rect,
            border_w, border_radius=8,
        )

        # ── Card content (drawn inside scaled area) ──────
        # Compute uniform content offset
        inner_x = x + (sw - _CARD_W) // 2
        inner_y = y + (sh - _CARD_H) // 2

        # Role name
        name_surf = self._font_name.render(name, True, _NAME_COLOR)
        self.screen.blit(
            name_surf,
            (inner_x + (_CARD_W - name_surf.get_width()) // 2, inner_y + 10),
        )

        # Stat bars
        bar_y = inner_y + 42
        bar_x = inner_x + 14
        bar_w = _CARD_W - 28
        bar_h = 8
        max_stat = 15
        for label, key, color in (
            ("DMG", "damage", _BAR_DAMAGE),
            ("SPD", "speed", _BAR_SPEED),
            ("DEF", "defense", _BAR_DEFENSE),
        ):
            lbl = self._font_stat.render(label, True, _STAT_COLOR)
            self.screen.blit(lbl, (bar_x, bar_y - 1))
            bx = bar_x + 34
            bw = bar_w - 34
            pygame.draw.rect(self.screen, _BAR_BG, (bx, bar_y + 2, bw, bar_h), border_radius=3)
            frac = min(1.0, stats.get(key, 0) / max_stat)
            fill_w = max(1, int(bw * frac))
            pygame.draw.rect(self.screen, color, (bx, bar_y + 2, fill_w, bar_h), border_radius=3)
            bar_y += 18

        # Description (multiline, pre-cached)
        desc_lines = self._desc_cache.get(name, [])
        if desc_lines:
            line_h = desc_lines[0].get_height() + _DESC_LINE_SPACING
            total_desc_h = len(desc_lines) * line_h - _DESC_LINE_SPACING
            # Anchor description block to bottom of card with 8px padding
            desc_start_y = inner_y + _CARD_H - total_desc_h - 8
            for line_surf in desc_lines:
                self.screen.blit(line_surf, (inner_x + 8, desc_start_y))
                desc_start_y += line_h
