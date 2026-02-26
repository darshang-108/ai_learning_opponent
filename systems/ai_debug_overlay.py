"""
ai_debug_overlay.py – Toggleable real-time AI debug overlay.

Renders a semi-transparent panel showing AI internal state,
player/enemy vitals, and softmax personality probabilities.
Activated via F1; does NOT modify any gameplay logic.
"""

from __future__ import annotations

import pygame


# ── Layout constants ──────────────────────────────────────

_PANEL_X = 8
_PANEL_Y = 30
_PANEL_W = 260
_PANEL_PAD = 10
_LINE_H = 18
_FONT_SIZE = 15
_BG_ALPHA = 180
_BG_COLOR = (15, 15, 20)
_TITLE_COLOR = (100, 220, 255)
_LABEL_COLOR = (180, 180, 180)
_VALUE_COLOR = (255, 255, 255)
_SECTION_COLOR = (80, 200, 160)
_BAR_H = 8
_BAR_W = 100


class AIDebugOverlay:
    """Non-intrusive debug HUD for AI internals.

    Usage
    -----
    overlay = AIDebugOverlay(screen)
    # in event loop:  if key == K_F1: overlay.toggle()
    # each frame:     overlay.update(dt)
    #                 overlay.draw(ai_brain, player, enemy)
    """

    def __init__(self, screen: pygame.Surface) -> None:
        self._screen = screen
        self._visible = False
        self._font: pygame.font.Font | None = None
        self._panel: pygame.Surface | None = None
        self._anim_t: float = 0.0  # for subtle pulsing accent

    # ── Public API ────────────────────────────────────────

    def toggle(self) -> None:
        """Toggle overlay visibility."""
        self._visible = not self._visible

    @property
    def visible(self) -> bool:
        return self._visible

    def update(self, dt: float) -> None:
        """Advance animation timer (lightweight)."""
        if self._visible:
            self._anim_t += dt

    def draw(self, ai_brain, player, enemy) -> None:
        """Render the debug panel.  Safe if any arg is None."""
        if not self._visible:
            return
        self._ensure_font()

        lines: list[tuple[str, tuple[int, int, int]]] = []

        # ── Title ─────────────────────────────────────────
        lines.append(("AI DEBUG PANEL", _TITLE_COLOR))
        lines.append(("─" * 30, _LABEL_COLOR))

        # ── AI state ──────────────────────────────────────
        if ai_brain is not None:
            personality = _safe(ai_brain, "personality.name", "—")
            phase = _safe_call(ai_brain, "phase.phase_name", "—")
            state = _safe(ai_brain, "state", "—")
            aggro_level = _safe(ai_brain, "intent.aggression_level", None)
            attack_intent = _safe(ai_brain, "intent.attack_intent", None)
            defensive_bias = _safe(ai_brain, "intent.defensive_bias", None)
            tempo = _safe(ai_brain, "aggression.tempo_mode", "—")

            lines.append((f"Personality:  {personality}", _VALUE_COLOR))
            lines.append((f"Phase:        {phase}", _VALUE_COLOR))
            lines.append((f"FSM State:    {state}", _VALUE_COLOR))
            lines.append((f"Tempo:        {tempo}", _VALUE_COLOR))

            if aggro_level is not None:
                lines.append((f"Aggression:   {aggro_level:.2f}", _VALUE_COLOR))
            if attack_intent is not None:
                lines.append((f"Atk Intent:   {attack_intent:.2f}", _VALUE_COLOR))
            if defensive_bias is not None:
                lines.append((f"Def Bias:     {defensive_bias:.2f}", _VALUE_COLOR))

            # Softmax probabilities
            softmax = _get_softmax_probs()
            if softmax:
                lines.append(("", _LABEL_COLOR))
                lines.append(("Softmax Probabilities:", _SECTION_COLOR))
                # Sort descending by probability
                for name, prob in sorted(softmax.items(),
                                         key=lambda kv: kv[1], reverse=True):
                    lines.append((f"  {name:<12s} {prob:.3f}", _VALUE_COLOR))
        else:
            lines.append(("AI brain: N/A", _LABEL_COLOR))

        # ── Player state ──────────────────────────────────
        lines.append(("", _LABEL_COLOR))
        lines.append(("Player:", _SECTION_COLOR))
        if player is not None:
            hp = getattr(player, "hp", 0)
            max_hp = getattr(player, "max_hp", 1)
            stam = _stam_current(player)
            max_stam = _stam_max(player)
            style = "—"
            if ai_brain is not None:
                style = _safe(ai_brain, "learner.profile.style", None)
                if style is None:
                    style = "—"
            lines.append((f"  Style:      {style}", _VALUE_COLOR))
            lines.append((f"  HP:         {hp} / {max_hp}", _VALUE_COLOR))
            lines.append((f"  Stamina:    {stam:.0f} / {max_stam:.0f}", _VALUE_COLOR))
        else:
            lines.append(("  N/A", _LABEL_COLOR))

        # ── Enemy state ───────────────────────────────────
        lines.append(("", _LABEL_COLOR))
        lines.append(("Enemy:", _SECTION_COLOR))
        if enemy is not None:
            hp = getattr(enemy, "hp", 0)
            max_hp = getattr(enemy, "max_hp", 1)
            stam = _stam_current(enemy)
            max_stam = _stam_max(enemy)
            lines.append((f"  HP:         {hp} / {max_hp}", _VALUE_COLOR))
            lines.append((f"  Stamina:    {stam:.0f} / {max_stam:.0f}", _VALUE_COLOR))
            # Extra: desperation / rage flags
            desp_active = _safe(enemy, "ai_controller.desperation.modifiers.active", False)
            rage_active = _safe(enemy, "ai_controller.desperation.modifiers.rage_active", False)
            if desp_active:
                lines.append(("  [DESPERATION]", (255, 180, 60)))
            if rage_active:
                lines.append(("  [RAGE MODE]", (255, 60, 60)))
        else:
            lines.append(("  N/A", _LABEL_COLOR))

        lines.append(("─" * 30, _LABEL_COLOR))

        # ── Render panel ──────────────────────────────────
        panel_h = _PANEL_PAD * 2 + len(lines) * _LINE_H
        panel = pygame.Surface((_PANEL_W, panel_h), pygame.SRCALPHA)
        panel.fill((*_BG_COLOR, _BG_ALPHA))

        # 1-px border
        pygame.draw.rect(panel, (60, 60, 80, 200),
                         (0, 0, _PANEL_W, panel_h), 1)

        y = _PANEL_PAD
        for text, color in lines:
            if text:
                surf = self._font.render(text, True, color)  # type: ignore[union-attr]
                panel.blit(surf, (_PANEL_PAD, y))
            y += _LINE_H

        self._screen.blit(panel, (_PANEL_X, _PANEL_Y))

    # ── Internals ─────────────────────────────────────────

    def _ensure_font(self) -> None:
        if self._font is None:
            self._font = pygame.font.SysFont("consolas", _FONT_SIZE)


# ══════════════════════════════════════════════════════════
#  Helpers (pure, no side-effects)
# ══════════════════════════════════════════════════════════

def _safe(obj, dotted_path: str, default=None):
    """Safely traverse a dotted attribute path."""
    parts = dotted_path.split(".")
    cur = obj
    for part in parts:
        cur = getattr(cur, part, None)
        if cur is None:
            return default
    return cur


def _safe_call(obj, dotted_path: str, default=None):
    """Like _safe but also works for properties that may raise."""
    try:
        return _safe(obj, dotted_path, default)
    except Exception:
        return default


def _stam_current(entity) -> float:
    sc = getattr(entity, "stamina_component", None)
    if sc is not None:
        return getattr(sc, "stamina", 0.0)
    return getattr(entity, "stamina", 0.0)


def _stam_max(entity) -> float:
    sc = getattr(entity, "stamina_component", None)
    if sc is not None:
        return getattr(sc, "max_stamina", 1.0)
    return getattr(entity, "max_stamina", 1.0)


def _get_softmax_probs() -> dict[str, float]:
    """Import cached softmax probs from ai_system (lazy, no crash)."""
    try:
        from ai.ai_system import last_softmax_probs
        return dict(last_softmax_probs)
    except Exception:
        return {}
