"""
enemy.py – AI-controlled enemy built on the Character pixel sprite system.

Integrates with:
- AIBrain (intent-driven adaptive AI from ai/ai_core.py)
- StaminaComponent
- BuffManager
- Adaptive archetype system (BehaviorAnalyzer, persistence)

The enemy selects a personality based on the detected player style,
then the AIBrain drives all combat decisions via sub-systems:
  - CombatIntentSystem  (per-frame intent evaluation)
  - AggressionSystem    (pressure, tempo, punish)
  - BuildDifficultyAdapter (counter player builds)
  - DesperationMode     (low-HP comeback)
"""

from __future__ import annotations

import logging
import random

logger = logging.getLogger(__name__)

import pygame
from settings import (
    SCREEN_WIDTH, SCREEN_HEIGHT,
    RED, ENEMY_SPEED, ENEMY_MAX_HP,
    ENEMY_START_X, ENEMY_START_Y,
    GREEN, SMALL_FONT_SIZE,
    ENEMY_REGEN_INTERVAL, ENEMY_REGEN_MIN_PCT, ENEMY_REGEN_MAX_PCT,
    ENEMY_REGEN_CAP_PCT, ENEMY_REGEN_IDLE_MS,
    ENEMY_REGEN_FLASH_DUR, ENEMY_REGEN_TEXT_DUR,
    STAMINA_MAX,
    DUELIST_HP_MULT,
)
from entities.character import Character
from systems.stamina_system import StaminaComponent
from systems.buff_system import BuffManager
from ai.ai_system import select_personality
from ai.ai_core import AIBrain


class Enemy(Character):
    """AI-controlled enemy with personality and adaptive behavior."""

    def __init__(self, player_style: str = "Unknown",
                 build_type: str = "BALANCED"):
        super().__init__(
            x=ENEMY_START_X,
            y=ENEMY_START_Y,
            base_color=RED,
            accent_color=(255, 180, 180),
            facing=-1,
            max_hp=ENEMY_MAX_HP,
        )
        self.base_speed = ENEMY_SPEED
        self.speed = ENEMY_SPEED
        self.player_style = player_style
        self.build_type = build_type

        # Stamina
        self.stamina_component = StaminaComponent(STAMINA_MAX)
        self.stamina = STAMINA_MAX
        self.max_stamina = STAMINA_MAX

        # Buffs
        self.buff_manager = BuffManager()

        # Personality-based AI (new intent-driven brain)
        self.personality = select_personality(player_style)
        self.archetype = self.personality.name
        self.ai_controller = AIBrain(self.personality, build_type=build_type)

        # Per-personality HP scaling (Duelist is a glass cannon)
        if self.personality.name == "Duelist":
            scaled_hp = int(ENEMY_MAX_HP * DUELIST_HP_MULT)
            self.max_hp = scaled_hp
            self.hp = scaled_hp
            logger.info("Duelist HP scaled to %d", scaled_hp)

        # Delta time (seconds)
        self.clock_dt = 1.0 / 60.0

        # Legacy compat for match stats
        self.state = "chase"
        self.last_attack_type: str | None = None
        self._was_combo = False

        # Regeneration state
        self._last_regen_time = 0
        self._player_idle_since = 0
        self._is_regenerating = False
        self._regen_visual_timer = 0.0
        self._regen_text_timer = 0.0
        self._regen_text_y_offset = 0.0

    # ── AI Update ─────────────────────────────────────────

    def update(self, player_rect_or_char, player_is_active: bool = False,
               dt: float | None = None):
        """Run one frame of AI + animation.

        Parameters
        ----------
        player_rect_or_char : Player character or rect
        player_is_active    : True if player acted this frame
        dt                  : delta time override
        """
        if dt is None:
            dt = self.clock_dt

        now = pygame.time.get_ticks()

        # Track player activity for regen
        if player_is_active:
            self._player_idle_since = now

        # Regen
        self._try_regenerate(now)

        # Visual timers
        if self._regen_visual_timer > 0:
            self._regen_visual_timer -= dt
            if self._regen_visual_timer <= 0:
                self._is_regenerating = False
        if self._regen_text_timer > 0:
            self._regen_text_timer -= dt
            self._regen_text_y_offset += 20 * dt

        # AI brain drives movement + attack decisions
        if hasattr(player_rect_or_char, 'rect'):
            self.ai_controller.update(self, player_rect_or_char, dt)
        else:
            # Legacy: passed a rect directly
            class _FakePlayer:
                def __init__(self, rect):
                    self.rect = rect
                    self.is_attacking = False
                    self.is_blocking = False
                    self.can_act = True
                    self.stamina_component = None
            fake = _FakePlayer(player_rect_or_char)
            self.ai_controller.update(self, fake, dt)

        # Sync legacy state
        self.state = self.ai_controller.state
        self.last_attack_type = self.ai_controller.last_attack_type

        # Animation
        self.update_animation(dt)

        # Clamp
        self.rect.clamp_ip(pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT))

    def try_attack(self, player_rect) -> int:
        """Legacy API – returns damage dealt. Used by old CombatSystem."""
        # In the new system, damage is resolved via CombatSystem.enemy_attack()
        return 0

    # ── Regeneration ──────────────────────────────────────

    def _try_regenerate(self, now: int):
        if self.state == "attack":
            return
        if now - self._last_regen_time < ENEMY_REGEN_INTERVAL:
            return
        if now - self._player_idle_since < ENEMY_REGEN_IDLE_MS:
            return
        cap_hp = self.max_hp * ENEMY_REGEN_CAP_PCT
        if self.hp >= cap_hp:
            return
        heal_pct = random.uniform(ENEMY_REGEN_MIN_PCT, ENEMY_REGEN_MAX_PCT)
        heal_amount = int(self.max_hp * heal_pct)
        self.hp = min(int(cap_hp), self.hp + heal_amount)
        self._last_regen_time = now
        self._is_regenerating = True
        self._regen_visual_timer = ENEMY_REGEN_FLASH_DUR
        self._regen_text_timer = ENEMY_REGEN_TEXT_DUR
        self._regen_text_y_offset = 0.0

    # ── Draw override ─────────────────────────────────────

    def draw(self, surface: pygame.Surface, dt: float = 0.016):
        """Render with regen glow if active."""
        # Regen glow
        if self._is_regenerating:
            from utils.vfx import draw_glow
            glow_x = int(self.display_x) + self.rect.width // 2
            glow_y = int(self.display_y) + self.rect.height // 2
            draw_glow(surface, (glow_x, glow_y), 45, (50, 200, 50))

        super().draw(surface, dt)

        # Floating regen text
        if self._regen_text_timer > 0:
            alpha_frac = min(1.0, self._regen_text_timer / ENEMY_REGEN_TEXT_DUR)
            font = pygame.font.SysFont(None, SMALL_FONT_SIZE)
            txt = font.render("Regenerating\u2026", True, GREEN)
            alpha_surf = pygame.Surface(txt.get_size(), pygame.SRCALPHA)
            alpha_surf.blit(txt, (0, 0))
            alpha_surf.set_alpha(int(255 * alpha_frac))
            tx = int(self.display_x) + self.rect.width // 2 - txt.get_width() // 2
            ty = int(self.display_y) - 20 - int(self._regen_text_y_offset)
            surface.blit(alpha_surf, (tx, ty))

