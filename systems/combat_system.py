"""
combat_system.py – Enhanced combat with parry, block, execution, stamina,
and combat feel (hit lunge, hit stop, block sparks).

Responsibilities:
- Resolve player attacks (with stamina cost)
- Resolve enemy attacks (via AI controller)
- Perfect parry detection
- Block damage reduction + stamina chip
- Execution / finisher trigger
- Buff-modified damage
- Combat feel: forward lunge on hit, stamina chip on block
"""

from __future__ import annotations

import logging
import math
import time

logger = logging.getLogger(__name__)

import pygame
from settings import (
    ATTACK_RANGE, PLAYER_ATTACK_DAMAGE,
    BLOCK_DAMAGE_REDUCTION,
    PARRY_WINDOW, PARRY_STUN_DURATION, PARRY_BONUS_DAMAGE_MULT,
    EXECUTION_HP_THRESHOLD, EXECUTION_DAMAGE_MULT,
)

# ── Combat feel constants ─────────────────────────────────
HIT_LUNGE_IMPULSE = 3.0          # forward push on successful hit
BLOCK_STAMINA_CHIP = 8.0         # stamina drained from blocker per block
BLOCK_KNOCKBACK = 2.5            # pushback on blocked hit


class CombatResult:
    """Encapsulates the result of a combat action for the game loop to react."""

    __slots__ = (
        "hit", "damage", "blocked", "parried", "execution",
        "attack_type", "critical",
        "hit_lunge_vx", "block_stamina_chip", "block_knockback_vx",
    )

    def __init__(self):
        self.hit = False
        self.damage = 0
        self.blocked = False
        self.parried = False
        self.execution = False
        self.attack_type = "quick"
        self.critical = False
        # Combat feel outputs
        self.hit_lunge_vx = 0.0       # forward lunge for attacker
        self.block_stamina_chip = 0.0  # stamina drained from blocker
        self.block_knockback_vx = 0.0  # pushback on blocked hit


class CombatSystem:
    """Central combat resolver.

    Handles all damage application, parry detection,
    execution triggers, and stamina gating.
    """

    def __init__(self):
        # Track block timing for parry detection
        self._block_start_times: dict[int, float] = {}  # id(char) → timestamp
        self._parry_cooldown: dict[int, float] = {}

    # ══════════════════════════════════════════════════════
    #  Player → Enemy Attack
    # ══════════════════════════════════════════════════════

    def player_attack(self, player, enemy) -> CombatResult:
        """Resolve a player attack on the enemy.

        Uses hitbox collision if available, falls back to range check.
        Returns CombatResult.
        """
        result = CombatResult()

        # Hitbox collision check (preferred) or fallback range check
        hitbox = getattr(player, 'attack_hitbox', None)
        if hitbox is not None:
            if not hitbox.colliderect(enemy.rect):
                return result
            # Prevent multi-hit on same swing
            target_id = id(enemy)
            if target_id in player._hitbox_hit_targets:
                return result
            player._hitbox_hit_targets.add(target_id)
            logger.debug("Hitbox collision confirmed (player → enemy)")
        else:
            # Fallback: simple range check
            dist = self._distance(player, enemy)
            if dist > ATTACK_RANGE:
                return result

        # Dodge / invulnerability check
        if getattr(enemy, 'is_invulnerable', False) or enemy.is_dodging:
            return result

        result.hit = True

        # Base damage
        damage = float(PLAYER_ATTACK_DAMAGE)

        # Apply player buff modifiers
        if hasattr(player, 'buff_manager'):
            damage = player.buff_manager.modify_damage_dealt(damage)

        # Parry bonus window
        damage *= player.damage_mult

        # Execution check
        enemy_hp_frac = enemy.hp / max(1, enemy.max_hp)
        if enemy_hp_frac <= EXECUTION_HP_THRESHOLD and enemy_hp_frac > 0:
            damage *= EXECUTION_DAMAGE_MULT
            result.execution = True

        # Enemy blocking?
        if enemy.is_blocking:
            # Check for perfect parry (enemy parrying us – unlikely in PvE
            # but possible in PvP)
            damage = damage * (1.0 - BLOCK_DAMAGE_REDUCTION)
            result.blocked = True
            # Block stamina chip: drain blocker's stamina
            result.block_stamina_chip = BLOCK_STAMINA_CHIP
            if hasattr(enemy, 'stamina_component'):
                enemy.stamina_component.drain(BLOCK_STAMINA_CHIP)
            # Block knockback
            dir_sign = 1 if enemy.rect.centerx > player.rect.centerx else -1
            result.block_knockback_vx = BLOCK_KNOCKBACK * dir_sign

        # Apply damage
        actual = enemy.take_damage(int(max(1, damage)))
        result.damage = actual

        # Buff on-hit hooks
        if hasattr(player, 'buff_manager'):
            player.buff_manager.on_hit_landed(player, actual)

        # Knockback
        direction = 1 if enemy.rect.centerx > player.rect.centerx else -1
        knockback = 4 if not result.execution else 12
        enemy.apply_knockback(knockback * direction)

        # Combat feel: forward lunge for attacker on hit
        if result.hit and not result.blocked:
            lunge_dir = 1 if enemy.rect.centerx > player.rect.centerx else -1
            result.hit_lunge_vx = HIT_LUNGE_IMPULSE * lunge_dir
            player.apply_knockback(result.hit_lunge_vx * 0.5)

        return result

    # ══════════════════════════════════════════════════════
    #  Enemy → Player Attack (called by AI system)
    # ══════════════════════════════════════════════════════

    def enemy_attack(self, enemy, player, damage: int,
                     attack_type: str = "quick") -> CombatResult:
        """Resolve an enemy attack on the player.

        Parameters
        ----------
        damage      : raw damage from AI controller
        attack_type : "quick" or "heavy"
        """
        result = CombatResult()
        result.attack_type = attack_type

        if damage <= 0:
            damage = 1  # damage is never zero

        # Player dodging / invulnerable?
        if getattr(player, 'is_invulnerable', False) or player.is_dodging:
            return result

        result.hit = True
        dmg = float(damage)
        logger.debug("Enemy attack → player (raw dmg=%d, type=%s)", damage, attack_type)

        # Player blocking?
        if player.is_blocking:
            # Perfect parry check
            char_id = id(player)
            block_start = self._block_start_times.get(char_id, 0.0)
            time_blocking = time.time() - block_start
            parry_cd = self._parry_cooldown.get(char_id, 0.0)

            if (time_blocking <= PARRY_WINDOW
                    and time.time() > parry_cd):
                # PERFECT PARRY!
                result.parried = True
                result.blocked = True
                self._parry_cooldown[char_id] = time.time() + 1.0
                # Stun enemy
                enemy.is_stunned = True
                enemy.stun_timer = PARRY_STUN_DURATION
                # Grant bonus damage window
                player.damage_mult = PARRY_BONUS_DAMAGE_MULT
                # No damage taken on parry
                result.damage = 0
                return result

            # Normal block
            dmg = dmg * (1.0 - BLOCK_DAMAGE_REDUCTION)
            result.blocked = True
            # Block stamina chip on player
            result.block_stamina_chip = BLOCK_STAMINA_CHIP
            if hasattr(player, 'stamina_component'):
                player.stamina_component.drain(BLOCK_STAMINA_CHIP)
            # Block knockback
            dir_sign = 1 if player.rect.centerx > enemy.rect.centerx else -1
            result.block_knockback_vx = BLOCK_KNOCKBACK * dir_sign

        # Apply player buff damage reduction
        if hasattr(player, 'buff_manager'):
            dmg = player.buff_manager.modify_damage_taken(dmg)

        # Apply damage
        actual = player.take_damage(int(max(1, dmg)))
        result.damage = actual

        # Knockback
        direction = 1 if player.rect.centerx > enemy.rect.centerx else -1
        kb = 3 if attack_type == "quick" else 7
        player.apply_knockback(kb * direction)

        # Combat feel: forward lunge for attacker (enemy) on hit
        if result.hit and not result.blocked:
            lunge_dir = 1 if player.rect.centerx > enemy.rect.centerx else -1
            result.hit_lunge_vx = HIT_LUNGE_IMPULSE * lunge_dir
            enemy.apply_knockback(result.hit_lunge_vx * 0.4)

        return result

    # ══════════════════════════════════════════════════════
    #  Block Timing (for parry detection)
    # ══════════════════════════════════════════════════════

    def register_block_start(self, character):
        """Call when a character starts blocking."""
        self._block_start_times[id(character)] = time.time()

    def register_block_end(self, character):
        """Call when a character stops blocking."""
        self._block_start_times.pop(id(character), None)

    # ══════════════════════════════════════════════════════
    #  Execution Check
    # ══════════════════════════════════════════════════════

    @staticmethod
    def is_executable(character) -> bool:
        """Check if a character is in execution range."""
        if not character.alive:
            return False
        return (character.hp / max(1, character.max_hp)) <= EXECUTION_HP_THRESHOLD

    # ══════════════════════════════════════════════════════
    #  Parry Bonus Reset
    # ══════════════════════════════════════════════════════

    @staticmethod
    def reset_parry_bonus(character):
        """Reset bonus damage multiplier after parry window ends."""
        character.damage_mult = 1.0

    # ══════════════════════════════════════════════════════
    #  Helpers
    # ══════════════════════════════════════════════════════

    @staticmethod
    def _distance(a, b) -> float:
        return math.hypot(
            a.rect.centerx - b.rect.centerx,
            a.rect.centery - b.rect.centery,
        )

    def reset(self):
        self._block_start_times.clear()
        self._parry_cooldown.clear()
