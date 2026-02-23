"""
keybinds.py – Fully rebindable keybinding system with JSON persistence.

Provides three independent binding sets:
- SOLO_KEYS:   Player controls in Solo vs AI mode
- PVP_P1_KEYS: Player 1 controls in local PVP mode
- PVP_P2_KEYS: Player 2 controls in local PVP mode

Each set maps action names → pygame key constants. Actions:
    move_left, move_right, move_up, move_down,
    quick_attack, heavy_attack, block, dodge

Usage:
    from keybinds import SOLO_KEYS, PVP_P1_KEYS, PVP_P2_KEYS
    if keys[SOLO_KEYS["move_left"]]:
        ...

Persistence:
    save_keybinds()   – write current bindings to controls.json
    load_keybinds()   – load from controls.json (called on import)
    reset_keybinds()  – restore factory defaults
"""

from __future__ import annotations

import json
import logging
import os

import pygame

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════
#  Path to persistence file
# ══════════════════════════════════════════════════════════

_CONTROLS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "controls.json",
)

# ══════════════════════════════════════════════════════════
#  Canonical action list (shared by all binding sets)
# ══════════════════════════════════════════════════════════

ACTIONS: list[str] = [
    "move_left",
    "move_right",
    "move_up",
    "move_down",
    "quick_attack",
    "heavy_attack",
    "block",
    "dodge",
]

# Human-friendly labels for the controls menu
ACTION_LABELS: dict[str, str] = {
    "move_left":    "Move Left",
    "move_right":   "Move Right",
    "move_up":      "Move Up",
    "move_down":    "Move Down",
    "quick_attack": "Quick Attack",
    "heavy_attack": "Heavy Attack",
    "block":        "Block",
    "dodge":        "Dodge",
}

# ══════════════════════════════════════════════════════════
#  Default bindings (factory settings)
# ══════════════════════════════════════════════════════════

_DEFAULT_SOLO: dict[str, int] = {
    "move_left":    pygame.K_LEFT,
    "move_right":   pygame.K_RIGHT,
    "move_up":      pygame.K_UP,
    "move_down":    pygame.K_DOWN,
    "quick_attack": pygame.K_SPACE,
    "heavy_attack": pygame.K_x,
    "block":        pygame.K_LSHIFT,
    "dodge":        pygame.K_z,
}

_DEFAULT_PVP_P1: dict[str, int] = {
    "move_left":    pygame.K_a,
    "move_right":   pygame.K_d,
    "move_up":      pygame.K_w,
    "move_down":    pygame.K_s,
    "quick_attack": pygame.K_f,
    "heavy_attack": pygame.K_r,
    "block":        pygame.K_g,
    "dodge":        pygame.K_h,
}

_DEFAULT_PVP_P2: dict[str, int] = {
    "move_left":    pygame.K_LEFT,
    "move_right":   pygame.K_RIGHT,
    "move_up":      pygame.K_UP,
    "move_down":    pygame.K_DOWN,
    "quick_attack": pygame.K_KP1,
    "heavy_attack": pygame.K_KP4,
    "block":        pygame.K_KP2,
    "dodge":        pygame.K_KP3,
}

# ══════════════════════════════════════════════════════════
#  Live binding dictionaries (mutated at runtime)
# ══════════════════════════════════════════════════════════

SOLO_KEYS: dict[str, int] = dict(_DEFAULT_SOLO)
PVP_P1_KEYS: dict[str, int] = dict(_DEFAULT_PVP_P1)
PVP_P2_KEYS: dict[str, int] = dict(_DEFAULT_PVP_P2)


# ══════════════════════════════════════════════════════════
#  Persistence helpers
# ══════════════════════════════════════════════════════════

def save_keybinds() -> None:
    """Persist current bindings to controls.json."""
    payload = {
        "solo": {action: key for action, key in SOLO_KEYS.items()},
        "pvp_p1": {action: key for action, key in PVP_P1_KEYS.items()},
        "pvp_p2": {action: key for action, key in PVP_P2_KEYS.items()},
    }
    try:
        with open(_CONTROLS_PATH, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2)
        logger.info("Keybinds saved to %s", _CONTROLS_PATH)
    except OSError as exc:
        logger.error("Failed to save keybinds: %s", exc)


def load_keybinds() -> None:
    """Load bindings from controls.json into the live dictionaries.

    Missing actions are filled from defaults.  Unknown actions are
    silently ignored so a hand-edited JSON won't crash the game.
    """
    if not os.path.exists(_CONTROLS_PATH):
        logger.info("No controls.json found – using defaults.")
        return

    try:
        with open(_CONTROLS_PATH, "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read controls.json (%s) – using defaults.", exc)
        return

    def _apply(target: dict[str, int], section: str, defaults: dict[str, int]):
        raw = data.get(section, {})
        for action in ACTIONS:
            if action in raw:
                target[action] = int(raw[action])
            else:
                target[action] = defaults[action]

    _apply(SOLO_KEYS, "solo", _DEFAULT_SOLO)
    _apply(PVP_P1_KEYS, "pvp_p1", _DEFAULT_PVP_P1)
    _apply(PVP_P2_KEYS, "pvp_p2", _DEFAULT_PVP_P2)
    logger.info("Keybinds loaded from %s", _CONTROLS_PATH)


def reset_keybinds() -> None:
    """Restore factory defaults and save."""
    SOLO_KEYS.update(_DEFAULT_SOLO)
    PVP_P1_KEYS.update(_DEFAULT_PVP_P1)
    PVP_P2_KEYS.update(_DEFAULT_PVP_P2)
    save_keybinds()
    logger.info("Keybinds reset to defaults.")


# ══════════════════════════════════════════════════════════
#  Conflict detection
# ══════════════════════════════════════════════════════════

def find_conflicts(bindings: dict[str, int]) -> list[tuple[str, str, int]]:
    """Return a list of (action_a, action_b, key) tuples for duplicate keys
    within *one* binding set."""
    seen: dict[int, str] = {}
    conflicts: list[tuple[str, str, int]] = []
    for action, key in bindings.items():
        if key in seen:
            conflicts.append((seen[key], action, key))
        else:
            seen[key] = action
    return conflicts


def has_conflict(bindings: dict[str, int], action: str, new_key: int) -> str | None:
    """If *new_key* is already used by another action in *bindings*,
    return that action's name.  Otherwise return None."""
    for act, key in bindings.items():
        if act != action and key == new_key:
            return act
    return None


# ══════════════════════════════════════════════════════════
#  Key name helper (for display)
# ══════════════════════════════════════════════════════════

def key_name(key_code: int) -> str:
    """Return a human-readable name for a pygame key constant."""
    return pygame.key.name(key_code).upper()


# ══════════════════════════════════════════════════════════
#  Controls menu screen (self-contained Pygame loop)
# ══════════════════════════════════════════════════════════

# Color palette for the controls menu
_BG          = (20, 20, 30)
_HEADER_CLR  = (255, 255, 255)
_ACTION_CLR  = (200, 210, 230)
_KEY_CLR     = (100, 220, 160)
_SELECTED_BG = (50, 60, 90)
_WAITING_CLR = (255, 200, 80)
_CONFLICT_CLR = (255, 80, 80)
_HINT_CLR    = (140, 140, 140)
_TAB_ACTIVE  = (100, 180, 255)
_TAB_INACTIVE = (100, 100, 120)


class ControlsMenu:
    """Full-screen controls rebinding UI.

    Call ``run(screen)`` to enter the rebinding loop. Returns when
    the player presses ESC.

    Tabs: Solo | PVP P1 | PVP P2     (switch with Tab / 1-3)
    Navigate actions with UP/DOWN, press ENTER to rebind,
    press DELETE/BACKSPACE to clear, press R to reset defaults.
    """

    _TAB_NAMES = ["Solo", "PVP P1", "PVP P2"]

    def __init__(self):
        self._tab_index = 0
        self._selected_action = 0
        self._waiting_for_key = False
        self._conflict_msg: str = ""
        self._conflict_timer: float = 0.0

    # ── Public entry point ────────────────────────────────

    def run(self, screen: pygame.Surface, clock: pygame.time.Clock) -> None:
        """Run the controls-menu loop until the player presses ESC."""
        running = True
        while running:
            dt = clock.tick(30) / 1000.0
            self._conflict_timer = max(0.0, self._conflict_timer - dt)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    raise SystemExit

                if event.type == pygame.KEYDOWN:
                    if self._waiting_for_key:
                        running = self._handle_rebind(event.key)
                    else:
                        running = self._handle_nav(event.key)

            self._draw(screen)
            pygame.display.flip()

        # Persist on exit
        save_keybinds()

    # ── Helpers ───────────────────────────────────────────

    @property
    def _bindings(self) -> dict[str, int]:
        return [SOLO_KEYS, PVP_P1_KEYS, PVP_P2_KEYS][self._tab_index]

    def _handle_nav(self, key: int) -> bool:
        """Handle navigation keys. Returns False to exit menu."""
        if key == pygame.K_ESCAPE:
            return False  # exit menu

        if key == pygame.K_TAB:
            self._tab_index = (self._tab_index + 1) % 3
            self._selected_action = 0
        elif key == pygame.K_1:
            self._tab_index = 0
            self._selected_action = 0
        elif key == pygame.K_2:
            self._tab_index = 1
            self._selected_action = 0
        elif key == pygame.K_3:
            self._tab_index = 2
            self._selected_action = 0
        elif key in (pygame.K_UP, pygame.K_w):
            self._selected_action = (self._selected_action - 1) % len(ACTIONS)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self._selected_action = (self._selected_action + 1) % len(ACTIONS)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._waiting_for_key = True
        elif key in (pygame.K_DELETE, pygame.K_BACKSPACE):
            # Reset this single action to default
            action = ACTIONS[self._selected_action]
            defaults = [_DEFAULT_SOLO, _DEFAULT_PVP_P1, _DEFAULT_PVP_P2]
            self._bindings[action] = defaults[self._tab_index][action]
        elif key == pygame.K_r:
            reset_keybinds()
            self._conflict_msg = "All bindings reset to defaults"
            self._conflict_timer = 2.0

        return True

    def _handle_rebind(self, key: int) -> bool:
        """Assign a new key to the selected action. Returns True always."""
        # Cancel rebind on ESC
        if key == pygame.K_ESCAPE:
            self._waiting_for_key = False
            return True

        action = ACTIONS[self._selected_action]
        bindings = self._bindings

        # Conflict check
        conflicting = has_conflict(bindings, action, key)
        if conflicting is not None:
            self._conflict_msg = (
                f"'{key_name(key)}' already used by "
                f"'{ACTION_LABELS.get(conflicting, conflicting)}'"
            )
            self._conflict_timer = 2.5
            self._waiting_for_key = False
            return True

        # Assign
        bindings[action] = key
        self._waiting_for_key = False
        logger.info(
            "Rebound [%s] %s → %s",
            self._TAB_NAMES[self._tab_index], action, key_name(key),
        )
        return True

    # ── Rendering ─────────────────────────────────────────

    def _draw(self, surface: pygame.Surface) -> None:
        surface.fill(_BG)
        sw, sh = surface.get_size()
        cx = sw // 2

        title_font = pygame.font.SysFont(None, 48)
        tab_font = pygame.font.SysFont(None, 30)
        row_font = pygame.font.SysFont(None, 28)
        hint_font = pygame.font.SysFont(None, 22)

        # ── Title ─────────────────────────────────────────
        title = title_font.render("CONTROLS", True, _HEADER_CLR)
        surface.blit(title, (cx - title.get_width() // 2, 30))

        # ── Tabs ──────────────────────────────────────────
        tab_y = 85
        tab_x_start = cx - 180
        for i, name in enumerate(self._TAB_NAMES):
            color = _TAB_ACTIVE if i == self._tab_index else _TAB_INACTIVE
            label = f"[{i+1}] {name}"
            txt = tab_font.render(label, True, color)
            surface.blit(txt, (tab_x_start + i * 130, tab_y))

        # ── Action rows ──────────────────────────────────
        start_y = 140
        row_h = 40
        col_action_x = cx - 200
        col_key_x = cx + 60

        bindings = self._bindings
        for i, action in enumerate(ACTIONS):
            y = start_y + i * row_h

            # Highlight selected
            if i == self._selected_action:
                pygame.draw.rect(
                    surface, _SELECTED_BG,
                    (col_action_x - 10, y - 2, 430, row_h - 4),
                    border_radius=5,
                )

            # Action label
            label = ACTION_LABELS.get(action, action)
            action_surf = row_font.render(label, True, _ACTION_CLR)
            surface.blit(action_surf, (col_action_x, y + 4))

            # Current key
            if i == self._selected_action and self._waiting_for_key:
                key_surf = row_font.render(
                    "< press a key >", True, _WAITING_CLR,
                )
            else:
                key_text = key_name(bindings[action])
                key_surf = row_font.render(key_text, True, _KEY_CLR)
            surface.blit(key_surf, (col_key_x, y + 4))

        # ── Conflict message ──────────────────────────────
        if self._conflict_timer > 0 and self._conflict_msg:
            msg = hint_font.render(self._conflict_msg, True, _CONFLICT_CLR)
            surface.blit(msg, (cx - msg.get_width() // 2, start_y + len(ACTIONS) * row_h + 10))

        # ── Hints ─────────────────────────────────────────
        hints = [
            "UP/DOWN: Navigate   ENTER: Rebind   DEL: Reset action   R: Reset all",
            "TAB or 1-3: Switch tab   ESC: Back",
        ]
        for j, h in enumerate(hints):
            txt = hint_font.render(h, True, _HINT_CLR)
            surface.blit(txt, (cx - txt.get_width() // 2, sh - 60 + j * 24))


# ══════════════════════════════════════════════════════════
#  Auto-load on import
# ══════════════════════════════════════════════════════════

load_keybinds()
