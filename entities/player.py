"""
player.py – Player entity built on the Character pixel sprite system.

Controls: Arrow keys (move), Space (attack), LShift (block), Z (dodge)
"""

import time
import pygame
from settings import (
    SCREEN_WIDTH, SCREEN_HEIGHT, BLUE,
    PLAYER_SPEED, PLAYER_MAX_HP,
    PLAYER_START_X, PLAYER_START_Y,
    PLAYER_ATTACK_COOLDOWN, DODGE_SPEED,
    STAMINA_MAX,
)
from entities.character import Character
from systems.stamina_system import StaminaComponent
from systems.buff_system import BuffManager
from systems.ability_system import Ability, create_ability
from keybinds import SOLO_KEYS


class Player(Character):
    """Player-controlled pixel knight."""

    def __init__(self, role_config: dict | None = None):
        super().__init__(
            x=PLAYER_START_X,
            y=PLAYER_START_Y,
            base_color=BLUE,
            accent_color=(180, 200, 255),
            facing=1,
            max_hp=PLAYER_MAX_HP,
        )
        self.base_speed = PLAYER_SPEED
        self.speed = PLAYER_SPEED
        self.last_attack_time = 0.0
        self.attack_cooldown = PLAYER_ATTACK_COOLDOWN

        # Stamina component
        self.stamina_component = StaminaComponent(STAMINA_MAX)
        self.stamina = STAMINA_MAX
        self.max_stamina = STAMINA_MAX

        # Buff manager
        self.buff_manager = BuffManager()

        # Avatar head (None = use default pixel sprite)
        self.avatar_surface: pygame.Surface | None = None

        # Role config (from CharacterSelectScreen)
        self.role_config: dict | None = role_config
        self.role_name: str = "Default"
        self.role_damage_mult: float = 1.0
        self.role_defense_mult: float = 1.0
        self.ability: Ability | None = None
        if role_config:
            self._apply_role(role_config)

    def _apply_role(self, cfg: dict) -> None:
        """Override base stats from a role config dict."""
        self.role_name = cfg.get("name", "Default")

        # Speed: role value mapped onto a 1-10 range around PLAYER_SPEED
        if "speed" in cfg:
            self.base_speed = PLAYER_SPEED + (cfg["speed"] - 5)
            self.speed = self.base_speed

        # Damage: stored as a multiplier so combat can consume it
        self.role_damage_mult: float = cfg.get("damage", 10) / 10.0

        # Defense: stored as a damage-reduction fraction (0-1)
        self.role_defense_mult: float = 1.0 - (cfg.get("defense", 5) * 0.04)

        # Role ability (factory-created, no conditionals here)
        self.ability = create_ability(self.role_name)

    # ── Movement ──────────────────────────────────────────

    def handle_input(self, keys):
        """Move the player based on currently held keys."""
        if not self.can_act:
            return

        speed = self.speed
        if self.buff_manager:
            speed = self.buff_manager.modify_speed(speed)

        if keys[SOLO_KEYS["move_left"]]:
            self.rect.x -= int(speed)
        if keys[SOLO_KEYS["move_right"]]:
            self.rect.x += int(speed)
        if keys[SOLO_KEYS["move_up"]]:
            self.rect.y -= int(speed)
        if keys[SOLO_KEYS["move_down"]]:
            self.rect.y += int(speed)

        # Dodge movement
        if self.is_dodging:
            self.rect.x += self.dodge_dir * DODGE_SPEED

        # Clamp
        self.rect.clamp_ip(pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT))

    # ── Attack ────────────────────────────────────────────

    def try_attack(self) -> bool:
        """Attempt attack. Returns True if attack fires."""
        now = time.time()
        cd = self.attack_cooldown
        if self.buff_manager:
            cd = self.buff_manager.modify_attack_cooldown(cd)

        if now - self.last_attack_time < cd:
            return False
        if not self.can_act:
            return False

        # Stamina check
        if not self.stamina_component.drain_attack():
            return False

        self.start_attack()
        self.last_attack_time = now
        return True

    # ── Block (held key) ──────────────────────────────────

    def try_block(self, pressed: bool):
        """Start or stop blocking based on key state."""
        if pressed and self.can_act:
            if not self.is_blocking:
                self.start_block()
                return True
            # Drain stamina while blocking
            self.stamina_component.drain_block(1 / 60)
        else:
            if self.is_blocking:
                self.stop_block()
        return False

    # ── Dodge ─────────────────────────────────────────────

    def try_dodge(self, keys) -> bool:
        """Attempt dodge roll."""
        if not self.can_act:
            return False
        if not self.stamina_component.drain_dodge():
            return False
        # Direction based on movement keys
        if keys[SOLO_KEYS["move_left"]]:
            direction = -1
        elif keys[SOLO_KEYS["move_right"]]:
            direction = 1
        else:
            direction = -self.facing  # dodge backward
        return self.start_dodge(direction)

    # ── Ability ────────────────────────────────────────────

    def try_ability(self, **kwargs) -> bool:
        """Attempt to activate the role ability.  Returns True on success."""
        if self.ability is None:
            return False
        return self.ability.activate(self, **kwargs)

    # ── Draw override ─────────────────────────────────────

    def draw(self, surface: pygame.Surface, dt: float = 0.016):
        """Render player. Uses avatar_surface for head if available."""
        super().draw(surface, dt)

        # If avatar surface is set, overlay it as head
        if self.avatar_surface is not None and self.alive:
            head_size = min(20, self.avatar_surface.get_width())
            head = pygame.transform.smoothscale(
                self.avatar_surface, (head_size, head_size),
            )
            hx = int(self.display_x) + self.rect.width // 2 - head_size // 2
            hy = int(self.display_y) - 2
            surface.blit(head, (hx, hy))

