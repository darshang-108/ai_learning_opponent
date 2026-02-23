"""
pvp_system.py – Local multiplayer PVP mode.

Requirements:
- Player 1: Rebindable via keybinds.py (default WASD + F/G/H)
- Player 2: Rebindable via keybinds.py (default Arrows + Numpad)
- Shared arena
- Independent stamina, buffs, personality
- Option to enable/disable AI for either player
"""

from __future__ import annotations

import pygame
from entities.character import Character
from systems.stamina_system import StaminaComponent
from systems.buff_system import BuffManager
from settings import (
    SCREEN_WIDTH, SCREEN_HEIGHT, CHAR_WIDTH, CHAR_HEIGHT,
    ARENA_FLOOR_Y, BLUE, RED, PLAYER_MAX_HP, PLAYER_SPEED,
    PLAYER_ATTACK_COOLDOWN, STAMINA_MAX,
)
from keybinds import PVP_P1_KEYS, PVP_P2_KEYS

import time


# ══════════════════════════════════════════════════════════
#  Key Binding Adapters
# ══════════════════════════════════════════════════════════

def _build_pvp_keys(src: dict[str, int]) -> dict[str, int]:
    """Map keybinds action names to PVP internal names.

    Called fresh each time a PVPManager is created so any
    rebinds made in the Controls menu are immediately active.
    """
    return {
        "up":     src["move_up"],
        "down":   src["move_down"],
        "left":   src["move_left"],
        "right":  src["move_right"],
        "attack": src["quick_attack"],
        "block":  src["block"],
        "dodge":  src["dodge"],
    }


# ══════════════════════════════════════════════════════════
#  PVP Fighter (wrapper around Character)
# ══════════════════════════════════════════════════════════

class PVPFighter:
    """A player-controlled fighter in PVP mode.

    Wraps a Character with input handling, stamina, and buffs.
    """

    def __init__(self, player_id: int, x: int, facing: int,
                 color: tuple, accent: tuple, keys: dict):
        self.player_id = player_id
        self.keys = keys
        self.character = Character(
            x=x,
            y=ARENA_FLOOR_Y - CHAR_HEIGHT,
            base_color=color,
            accent_color=accent,
            facing=facing,
            max_hp=PLAYER_MAX_HP,
        )
        self.character.base_speed = PLAYER_SPEED
        self.character.speed = PLAYER_SPEED

        # Stamina
        self.character.stamina_component = StaminaComponent(STAMINA_MAX)
        self.character.stamina = STAMINA_MAX
        self.character.max_stamina = STAMINA_MAX

        # Buffs
        self.character.buff_manager = BuffManager()

        # Combat state
        self.last_attack_time = 0.0
        self.attack_cooldown = PLAYER_ATTACK_COOLDOWN

        # AI toggle
        self.ai_enabled = False
        self.ai_controller = None    # Set externally if AI enabled

        # Score
        self.wins = 0

    def handle_input(self, keys_pressed, events: list, combat_system):
        """Process input for this fighter."""
        char = self.character
        if not char.can_act:
            return

        # Movement
        speed = char.speed
        if hasattr(char, 'buff_manager'):
            speed = char.buff_manager.modify_speed(speed)

        if keys_pressed[self.keys["left"]]:
            char.rect.x -= int(speed)
        if keys_pressed[self.keys["right"]]:
            char.rect.x += int(speed)
        if keys_pressed[self.keys["up"]]:
            char.rect.y -= int(speed)
        if keys_pressed[self.keys["down"]]:
            char.rect.y += int(speed)

        # Block (held)
        if keys_pressed[self.keys["block"]]:
            if not char.is_blocking:
                char.start_block()
                combat_system.register_block_start(char)
            if hasattr(char, 'stamina_component'):
                char.stamina_component.drain_block(1 / 60)
        else:
            if char.is_blocking:
                char.stop_block()
                combat_system.register_block_end(char)

        # Event-based actions (attack, dodge)
        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == self.keys["attack"]:
                    self._try_attack()
                elif event.key == self.keys["dodge"]:
                    self._try_dodge(keys_pressed)

    def _try_attack(self):
        now = time.time()
        if now - self.last_attack_time < self.attack_cooldown:
            return
        char = self.character
        if not char.can_act:
            return
        # Stamina check
        if hasattr(char, 'stamina_component'):
            if not char.stamina_component.drain_attack():
                return
        char.start_attack()
        self.last_attack_time = now
        # Apply buff modifier to cooldown
        cd = self.attack_cooldown
        if hasattr(char, 'buff_manager'):
            cd = char.buff_manager.modify_attack_cooldown(cd)
        self.attack_cooldown = max(0.15, cd)

    def _try_dodge(self, keys_pressed):
        char = self.character
        if not char.can_act:
            return
        # Determine direction
        if keys_pressed[self.keys["left"]]:
            direction = -1
        elif keys_pressed[self.keys["right"]]:
            direction = 1
        else:
            direction = -char.facing  # dodge backward by default

        if hasattr(char, 'stamina_component'):
            if not char.stamina_component.drain_dodge():
                return
        char.start_dodge(direction)


# ══════════════════════════════════════════════════════════
#  PVP Manager
# ══════════════════════════════════════════════════════════

class PVPManager:
    """Manages a local PVP session between two fighters.

    Usage:
        pvp = PVPManager()
        pvp.start_round()
        # In game loop:
        pvp.handle_input(keys, events, combat)
        pvp.update(dt, combat)
        pvp.draw(surface, dt)
    """

    def __init__(self):
        self.p1 = PVPFighter(
            player_id=1,
            x=150,
            facing=1,
            color=BLUE,
            accent=(180, 200, 255),
            keys=_build_pvp_keys(PVP_P1_KEYS),
        )
        self.p2 = PVPFighter(
            player_id=2,
            x=SCREEN_WIDTH - 150 - CHAR_WIDTH,
            facing=-1,
            color=RED,
            accent=(255, 180, 180),
            keys=_build_pvp_keys(PVP_P2_KEYS),
        )
        self.round_over = False
        self.winner: PVPFighter | None = None
        self.round_number = 1

    def start_round(self):
        """Reset fighters for a new round."""
        self.p1.character.hp = self.p1.character.max_hp
        self.p1.character.stamina = STAMINA_MAX
        self.p1.character.anim_state = "idle"
        self.p1.character.anim_timer = 0.0
        self.p1.character.is_stunned = False
        self.p1.character.is_blocking = False
        self.p1.character.is_dodging = False
        self.p1.character.rect.x = 150
        self.p1.character.rect.y = ARENA_FLOOR_Y - CHAR_HEIGHT
        self.p1.character.display_x = 150.0
        self.p1.character.display_y = float(ARENA_FLOOR_Y - CHAR_HEIGHT)
        self.p1.character.facing = 1
        self.p1.character._rebuild_parts()
        if hasattr(self.p1.character, 'stamina_component'):
            self.p1.character.stamina_component.reset()
        if hasattr(self.p1.character, 'buff_manager'):
            self.p1.character.buff_manager.clear(self.p1.character)

        self.p2.character.hp = self.p2.character.max_hp
        self.p2.character.stamina = STAMINA_MAX
        self.p2.character.anim_state = "idle"
        self.p2.character.anim_timer = 0.0
        self.p2.character.is_stunned = False
        self.p2.character.is_blocking = False
        self.p2.character.is_dodging = False
        self.p2.character.rect.x = SCREEN_WIDTH - 150 - CHAR_WIDTH
        self.p2.character.rect.y = ARENA_FLOOR_Y - CHAR_HEIGHT
        self.p2.character.display_x = float(SCREEN_WIDTH - 150 - CHAR_WIDTH)
        self.p2.character.display_y = float(ARENA_FLOOR_Y - CHAR_HEIGHT)
        self.p2.character.facing = -1
        self.p2.character._rebuild_parts()
        if hasattr(self.p2.character, 'stamina_component'):
            self.p2.character.stamina_component.reset()
        if hasattr(self.p2.character, 'buff_manager'):
            self.p2.character.buff_manager.clear(self.p2.character)

        self.round_over = False
        self.winner = None

    def handle_input(self, keys_pressed, events: list, combat_system):
        """Process input for both fighters."""
        if self.round_over:
            return
        if not self.p1.ai_enabled:
            self.p1.handle_input(keys_pressed, events, combat_system)
        if not self.p2.ai_enabled:
            self.p2.handle_input(keys_pressed, events, combat_system)

    def update(self, dt: float, combat_system) -> list:
        """Update both fighters. Returns list of CombatResults."""
        if self.round_over:
            return []

        results = []
        c1, c2 = self.p1.character, self.p2.character

        # Update animations
        c1.update_animation(dt)
        c2.update_animation(dt)

        # Dodge movement
        from settings import DODGE_SPEED
        if c1.is_dodging:
            c1.rect.x += c1.dodge_dir * DODGE_SPEED
        if c2.is_dodging:
            c2.rect.x += c2.dodge_dir * DODGE_SPEED

        # Clamp
        c1.rect.clamp_ip(pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT))
        c2.rect.clamp_ip(pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT))

        # Face each other
        c1.face_toward(c2.rect.centerx)
        c2.face_toward(c1.rect.centerx)

        # Resolve attacks: P1 → P2
        if c1.is_attacking and c1.anim_state == "attack":
            if c1.anim_timer < dt * 2:  # only on first frame of attack
                result = combat_system.player_attack(c1, c2)
                if result.hit:
                    results.append(("p1_hit", result))

        # Resolve attacks: P2 → P1
        if c2.is_attacking and c2.anim_state == "attack":
            if c2.anim_timer < dt * 2:
                result = combat_system.player_attack(c2, c1)
                if result.hit:
                    results.append(("p2_hit", result))

        # Stamina update
        from systems.stamina_system import StaminaSystem
        StaminaSystem.update(c1, dt)
        StaminaSystem.update(c2, dt)

        # Buff update
        if hasattr(c1, 'buff_manager'):
            c1.buff_manager.update(dt, c1)
        if hasattr(c2, 'buff_manager'):
            c2.buff_manager.update(dt, c2)

        # Win check
        if not c1.alive:
            self.round_over = True
            self.winner = self.p2
            self.p2.wins += 1
        elif not c2.alive:
            self.round_over = True
            self.winner = self.p1
            self.p1.wins += 1

        return results

    def draw(self, surface: pygame.Surface, dt: float):
        """Draw both fighters."""
        self.p1.character.draw(surface, dt)
        self.p2.character.draw(surface, dt)

    def draw_hud(self, surface: pygame.Surface):
        """Draw PVP HUD (health, stamina, score)."""
        font = pygame.font.SysFont(None, 20)
        c1, c2 = self.p1.character, self.p2.character

        # P1 info (left)
        self._draw_pvp_bar(surface, 20, 20, 180, 14, c1.hp, c1.max_hp,
                           (80, 180, 80), "P1")
        self._draw_pvp_bar(surface, 20, 38, 180, 6,
                           c1.stamina, c1.max_stamina,
                           (80, 160, 255), "")

        # P2 info (right)
        self._draw_pvp_bar(surface, SCREEN_WIDTH - 200, 20, 180, 14,
                           c2.hp, c2.max_hp, (80, 180, 80), "P2")
        self._draw_pvp_bar(surface, SCREEN_WIDTH - 200, 38, 180, 6,
                           c2.stamina, c2.max_stamina,
                           (80, 160, 255), "")

        # Score
        score_text = font.render(
            f"P1: {self.p1.wins}  |  Round {self.round_number}  |  P2: {self.p2.wins}",
            True, (255, 255, 255),
        )
        surface.blit(score_text,
                     (SCREEN_WIDTH // 2 - score_text.get_width() // 2, 8))

    @staticmethod
    def _draw_pvp_bar(surface, x, y, w, h, current, maximum,
                      color, label):
        # Background
        pygame.draw.rect(surface, (40, 40, 40), (x, y, w, h), border_radius=3)
        # Fill
        frac = max(0, min(1, current / max(1, maximum)))
        fw = int(w * frac)
        if fw > 0:
            pygame.draw.rect(surface, color, (x, y, fw, h), border_radius=3)
        # Border
        pygame.draw.rect(surface, (150, 150, 150), (x, y, w, h), 1,
                         border_radius=3)
        if label:
            font = pygame.font.SysFont(None, 16)
            txt = font.render(label, True, (255, 255, 255))
            surface.blit(txt, (x + 4, y + 1))
