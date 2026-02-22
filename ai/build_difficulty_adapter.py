"""
build_difficulty_adapter.py – Adjust enemy behavior based on player build type.

Instead of inflating HP or flat stat boosts, this module reshapes the
enemy's *behavior and tempo* to counter specific player archetypes.

Supported build types:
- MAGE       : ranged/caster  → enemy closes distance, dodges projectiles
- DEXTERITY  : fast melee     → enemy blocks more, punishes whiffs tightly
- TANK       : heavy/slow     → enemy uses guard-breaks, drains stamina
- BALANCED   : default        → no special adjustments

The adapter produces a set of behavioral modifiers that are consumed
by ai_core.py every frame.
"""

from __future__ import annotations

from dataclasses import dataclass


# ══════════════════════════════════════════════════════════
#  Build Modifier Output
# ══════════════════════════════════════════════════════════

@dataclass
class BuildModifiers:
    """Behavioral modifiers applied per-frame based on player build.
    All values are multipliers or additive offsets."""

    chase_speed_mult: float = 1.0
    dodge_probability_add: float = 0.0
    block_probability_add: float = 0.0
    attack_cooldown_mult: float = 1.0
    spacing_offset: float = 0.0       # pixels – adjust preferred range
    guard_break_chance: float = 0.0   # probability of heavy attack to break guard
    stamina_drain_mult: float = 1.0   # multiplier on enemy stamina drain from attacks
    combo_punish_mult: float = 1.0    # multiplier on counter-attack after player whiff
    parry_rate_add: float = 0.0
    aggression_offset: float = 0.0    # additive to aggression_level


# ══════════════════════════════════════════════════════════
#  Build Difficulty Adapter
# ══════════════════════════════════════════════════════════

class BuildDifficultyAdapter:
    """Produces per-frame BuildModifiers based on detected player build.

    Usage:
        adapter = BuildDifficultyAdapter("MAGE")
        mods = adapter.get_modifiers(enemy_hp_frac, player_blocking)
    """

    def __init__(self, build_type: str = "BALANCED"):
        self.build_type = build_type.upper()

    def get_modifiers(self, enemy_hp_frac: float = 1.0,
                      player_is_blocking: bool = False) -> BuildModifiers:
        """Return build-specific behavioral modifiers."""

        if self.build_type == "MAGE":
            return self._mage_modifiers(enemy_hp_frac)
        elif self.build_type == "DEXTERITY":
            return self._dexterity_modifiers(enemy_hp_frac)
        elif self.build_type == "TANK":
            return self._tank_modifiers(enemy_hp_frac, player_is_blocking)
        else:
            return BuildModifiers()  # balanced = no modifiers

    # ── Build-specific profiles ───────────────────────────

    def _mage_modifiers(self, enemy_hp_frac: float) -> BuildModifiers:
        """vs MAGE: close distance fast, dodge projectiles, punish ranged spam."""
        return BuildModifiers(
            chase_speed_mult=1.45,
            dodge_probability_add=0.25,    # dodge projectiles
            block_probability_add=0.0,
            attack_cooldown_mult=0.85,     # attack faster to interrupt casts
            spacing_offset=-20.0,          # get closer than usual
            guard_break_chance=0.0,
            stamina_drain_mult=1.0,
            combo_punish_mult=1.3,         # punish ranged spam hard
            parry_rate_add=0.0,
            aggression_offset=0.15,        # stay aggressive
        )

    def _dexterity_modifiers(self, enemy_hp_frac: float) -> BuildModifiers:
        """vs DEXTERITY: tight reactions, block/parry focus, punish missed combos."""
        return BuildModifiers(
            chase_speed_mult=1.10,
            dodge_probability_add=0.10,
            block_probability_add=0.20,    # block more
            attack_cooldown_mult=1.05,     # slightly careful
            spacing_offset=0.0,
            guard_break_chance=0.0,
            stamina_drain_mult=1.0,
            combo_punish_mult=1.50,        # punish whiffs aggressively
            parry_rate_add=0.15,           # more parry attempts
            aggression_offset=-0.05,       # slightly measured
        )

    def _tank_modifiers(self, enemy_hp_frac: float,
                        player_is_blocking: bool) -> BuildModifiers:
        """vs TANK: guard-break focus, stamina drain, avoid reckless trades."""
        gb_chance = 0.35 if player_is_blocking else 0.10
        return BuildModifiers(
            chase_speed_mult=1.05,
            dodge_probability_add=0.05,
            block_probability_add=0.05,
            attack_cooldown_mult=1.10,     # don't rush blindly
            spacing_offset=5.0,            # slight extra space
            guard_break_chance=gb_chance,
            stamina_drain_mult=1.30,       # drain their stamina faster
            combo_punish_mult=1.10,
            parry_rate_add=0.05,
            aggression_offset=-0.10,       # avoid reckless aggression
        )
