"""
attack_style_system.py – Blendable combat archetype system.

Defines 7 distinct attack styles (archetypes) that can be blended together
to create unique, unpredictable AI behaviour every fight:

  Trickster   – Feints, cancels, unpredictable timing
  Analyzer    – Methodical, exploits patterns, punishes mistakes
  Predator    – Relentless close-range pressure
  Tactician   – Spacing control, optimal range, calculated strikes
  Berserker   – Raw aggression, high damage, ignores defence
  Mirror      – Copies the player's style with a delay
  Phantom     – Hit-and-run, appears / disappears, erratic movement

Each archetype defines a StyleModifiers set. The system blends up to 3
active archetypes with weighted interpolation, and rotates archetypes
mid-fight to prevent repetition.

Anti-repetition:
  - Recent action buffer prevents the same move twice in a row
  - Style weights shift every N seconds
  - Dominant archetype changes when one becomes stale
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from collections import deque
from typing import Callable


# ══════════════════════════════════════════════════════════
#  Style Modifiers (per-archetype output)
# ══════════════════════════════════════════════════════════

@dataclass
class StyleModifiers:
    """Behavioural knobs produced by the archetype blend."""

    aggression_mult: float = 1.0
    cooldown_mult: float = 1.0
    block_readiness: float = 0.3
    dodge_readiness: float = 0.1
    feint_chance: float = 0.0
    combo_complexity: float = 0.5       # 0 = simple, 1 = varied
    chase_speed_mult: float = 1.0
    retreat_tendency: float = 0.2
    spacing_offset: float = 0.0         # pixels – preferred distance change
    heavy_attack_bias: float = 0.0      # positive = prefer heavy
    punish_aggression: float = 0.3      # how hard to punish openings
    strafe_speed_mult: float = 1.0
    movement_erratic: float = 0.0       # 0 = straight lines, 1 = zigzag


# ══════════════════════════════════════════════════════════
#  Archetype Definitions
# ══════════════════════════════════════════════════════════

def _trickster() -> StyleModifiers:
    return StyleModifiers(
        aggression_mult=0.95,
        cooldown_mult=0.90,
        block_readiness=0.20,
        dodge_readiness=0.35,
        feint_chance=0.40,
        combo_complexity=0.80,
        chase_speed_mult=1.05,
        retreat_tendency=0.30,
        spacing_offset=-5.0,
        heavy_attack_bias=-0.15,
        punish_aggression=0.40,
        strafe_speed_mult=1.30,
        movement_erratic=0.50,
    )

def _analyzer() -> StyleModifiers:
    return StyleModifiers(
        aggression_mult=0.85,
        cooldown_mult=1.10,
        block_readiness=0.55,
        dodge_readiness=0.25,
        feint_chance=0.10,
        combo_complexity=0.70,
        chase_speed_mult=0.95,
        retreat_tendency=0.35,
        spacing_offset=10.0,
        heavy_attack_bias=0.10,
        punish_aggression=0.65,
        strafe_speed_mult=1.00,
        movement_erratic=0.10,
    )

def _predator() -> StyleModifiers:
    return StyleModifiers(
        aggression_mult=1.40,
        cooldown_mult=0.75,
        block_readiness=0.15,
        dodge_readiness=0.10,
        feint_chance=0.05,
        combo_complexity=0.45,
        chase_speed_mult=1.35,
        retreat_tendency=0.05,
        spacing_offset=-15.0,
        heavy_attack_bias=0.15,
        punish_aggression=0.50,
        strafe_speed_mult=0.80,
        movement_erratic=0.15,
    )

def _tactician() -> StyleModifiers:
    return StyleModifiers(
        aggression_mult=1.00,
        cooldown_mult=1.00,
        block_readiness=0.40,
        dodge_readiness=0.20,
        feint_chance=0.15,
        combo_complexity=0.65,
        chase_speed_mult=1.00,
        retreat_tendency=0.25,
        spacing_offset=5.0,
        heavy_attack_bias=0.05,
        punish_aggression=0.55,
        strafe_speed_mult=1.10,
        movement_erratic=0.20,
    )

def _berserker() -> StyleModifiers:
    return StyleModifiers(
        aggression_mult=1.55,
        cooldown_mult=0.60,
        block_readiness=0.05,
        dodge_readiness=0.05,
        feint_chance=0.00,
        combo_complexity=0.30,
        chase_speed_mult=1.30,
        retreat_tendency=0.00,
        spacing_offset=-20.0,
        heavy_attack_bias=0.35,
        punish_aggression=0.25,
        strafe_speed_mult=0.70,
        movement_erratic=0.10,
    )

def _mirror() -> StyleModifiers:
    """Base style for Mirror — dynamically adjusted by learning system."""
    return StyleModifiers(
        aggression_mult=1.00,
        cooldown_mult=1.00,
        block_readiness=0.30,
        dodge_readiness=0.15,
        feint_chance=0.10,
        combo_complexity=0.50,
        chase_speed_mult=1.00,
        retreat_tendency=0.20,
        spacing_offset=0.0,
        heavy_attack_bias=0.00,
        punish_aggression=0.35,
        strafe_speed_mult=1.00,
        movement_erratic=0.20,
    )

def _phantom() -> StyleModifiers:
    return StyleModifiers(
        aggression_mult=0.80,
        cooldown_mult=0.85,
        block_readiness=0.15,
        dodge_readiness=0.45,
        feint_chance=0.25,
        combo_complexity=0.60,
        chase_speed_mult=1.15,
        retreat_tendency=0.50,
        spacing_offset=15.0,
        heavy_attack_bias=-0.10,
        punish_aggression=0.45,
        strafe_speed_mult=1.40,
        movement_erratic=0.70,
    )

ARCHETYPE_FACTORY: dict[str, Callable[[], "StyleModifiers"]] = {
    "Trickster": _trickster,
    "Analyzer":  _analyzer,
    "Predator":  _predator,
    "Tactician": _tactician,
    "Berserker": _berserker,
    "Mirror":    _mirror,
    "Phantom":   _phantom,
}

ALL_ARCHETYPES = list(ARCHETYPE_FACTORY.keys())


# ══════════════════════════════════════════════════════════
#  Configuration
# ══════════════════════════════════════════════════════════

@dataclass
class StyleConfig:
    """Tunables for the attack style blending system."""

    # Number of archetypes blended simultaneously
    blend_count: int = 2

    # How often the dominant style shifts (seconds)
    style_shift_interval: float = 8.0
    style_shift_jitter: float = 3.0      # ± random variation

    # Anti-repetition buffer (last N actions tracked)
    action_buffer_size: int = 6

    # Mirror archetype: how much to copy player profile (0–1)
    mirror_copy_strength: float = 0.75

    # Minimum weight for any active archetype
    min_weight: float = 0.15

    # Style staleness threshold — if one style dominates too long, shift
    staleness_timer: float = 12.0


# ══════════════════════════════════════════════════════════
#  Attack Style System
# ══════════════════════════════════════════════════════════

class AttackStyleSystem:
    """Manages blendable combat archetypes for dynamic, varied AI.

    Usage:
        styles = AttackStyleSystem()
        styles.update(dt, player_profile=None)
        mods = styles.modifiers
        # use mods.aggression_mult, mods.feint_chance, etc.
    """

    def __init__(self, config: StyleConfig | None = None,
                 initial_archetypes: list[str] | None = None):
        self.cfg = config or StyleConfig()
        self._modifiers = StyleModifiers()

        # ── Active archetypes with weights ────────────────
        if initial_archetypes is None:
            initial_archetypes = random.sample(ALL_ARCHETYPES, k=self.cfg.blend_count)
        self._active: list[str] = list(initial_archetypes[:self.cfg.blend_count])
        self._weights: list[float] = self._init_weights()

        # ── Timers ────────────────────────────────────────
        self._shift_timer: float = (
            self.cfg.style_shift_interval
            + random.uniform(-self.cfg.style_shift_jitter, self.cfg.style_shift_jitter)
        )
        self._staleness: dict[str, float] = {a: 0.0 for a in self._active}

        # ── Anti-repetition ───────────────────────────────
        self._action_buffer: deque[str] = deque(maxlen=self.cfg.action_buffer_size)

        # ── Cached archetype modifiers ────────────────────
        self._archetype_mods: dict[str, StyleModifiers] = {
            name: ARCHETYPE_FACTORY[name]() for name in self._active
        }

    # ── Properties ────────────────────────────────────────

    @property
    def modifiers(self) -> StyleModifiers:
        return self._modifiers

    @property
    def active_archetypes(self) -> list[str]:
        return list(self._active)

    @property
    def dominant_archetype(self) -> str:
        if not self._active:
            return "Tactician"
        max_idx = 0
        max_w = self._weights[0]
        for i, w in enumerate(self._weights):
            if w > max_w:
                max_w = w
                max_idx = i
        return self._active[max_idx]

    # ══════════════════════════════════════════════════════
    #  Main Update
    # ══════════════════════════════════════════════════════

    def update(self, dt: float, player_profile=None):
        """Update style blend. Call every frame.

        Args:
            dt: delta time in seconds.
            player_profile: optional PlayerProfile from adaptive_learning
                            to feed the Mirror archetype.
        """
        cfg = self.cfg

        # ── Style shift timer ─────────────────────────────
        self._shift_timer -= dt
        if self._shift_timer <= 0:
            self._shift_styles()
            self._shift_timer = (
                cfg.style_shift_interval
                + random.uniform(-cfg.style_shift_jitter, cfg.style_shift_jitter)
            )

        # ── Staleness check ───────────────────────────────
        for name in self._active:
            self._staleness[name] = self._staleness.get(name, 0.0) + dt
        dominant = self.dominant_archetype
        if self._staleness.get(dominant, 0.0) > cfg.staleness_timer:
            self._replace_stale(dominant)

        # ── Mirror archetype adjustment ───────────────────
        if "Mirror" in self._active and player_profile is not None:
            self._update_mirror(player_profile)

        # ── Blend modifiers ───────────────────────────────
        self._blend()

    def record_action(self, action: str):
        """Record an action to the anti-repetition buffer."""
        self._action_buffer.append(action)

    def should_vary_action(self, proposed_action: str) -> bool:
        """Returns True if the proposed action was recently used and should be varied."""
        if len(self._action_buffer) < 2:
            return False
        # If last 2 actions were the same as proposed, suggest variation
        recent = list(self._action_buffer)[-2:]
        return all(a == proposed_action for a in recent)

    # ══════════════════════════════════════════════════════
    #  Internal
    # ══════════════════════════════════════════════════════

    def _init_weights(self) -> list[float]:
        """Generate random initial weights that sum to 1.0."""
        raw = [random.uniform(0.3, 1.0) for _ in self._active]
        total = sum(raw)
        return [w / total for w in raw]

    def _shift_styles(self):
        """Rotate one archetype out and bring a new one in."""
        if len(self._active) < 2:
            return

        # Remove the lowest-weight archetype
        min_idx = 0
        min_w = self._weights[0]
        for i, w in enumerate(self._weights):
            if w < min_w:
                min_w = w
                min_idx = i
        removed = self._active.pop(min_idx)
        self._weights.pop(min_idx)
        self._staleness.pop(removed, None)

        # Pick a new archetype not currently active
        available = [a for a in ALL_ARCHETYPES if a not in self._active]
        if available:
            new_arch = random.choice(available)
            self._active.append(new_arch)
            self._weights.append(self.cfg.min_weight)
            self._staleness[new_arch] = 0.0
            self._archetype_mods[new_arch] = ARCHETYPE_FACTORY[new_arch]()

        # Re-normalise weights
        self._normalise_weights()

    def _replace_stale(self, stale_name: str):
        """Replace a stale dominant archetype."""
        if stale_name not in self._active:
            return
        idx = self._active.index(stale_name)
        available = [a for a in ALL_ARCHETYPES if a not in self._active]
        if not available:
            return
        new_arch = random.choice(available)
        self._active[idx] = new_arch
        self._weights[idx] = self.cfg.min_weight
        self._staleness.pop(stale_name, None)
        self._staleness[new_arch] = 0.0
        self._archetype_mods[new_arch] = ARCHETYPE_FACTORY[new_arch]()
        self._normalise_weights()

    def _normalise_weights(self):
        total = sum(self._weights)
        if total > 0:
            self._weights = [w / total for w in self._weights]

    def _update_mirror(self, profile):
        """Adjust the Mirror archetype to copy the player's style."""
        s = self.cfg.mirror_copy_strength
        m = self._archetype_mods.get("Mirror")
        if m is None:
            return

        # Map player profile dimensions to style modifiers
        m.aggression_mult = 0.7 + profile.attack_frequency * s * 0.8
        m.cooldown_mult = 1.2 - profile.attack_frequency * s * 0.4
        m.block_readiness = profile.block_after_hit * s
        m.dodge_readiness = profile.dodge_frequency * s
        m.retreat_tendency = profile.retreat_after_attack * s
        m.heavy_attack_bias = (profile.heavy_attack_ratio - 0.5) * s
        m.combo_complexity = min(1.0, 0.3 + (1.0 - profile.combo_repetition) * s * 0.5)

    def _blend(self):
        """Weighted interpolation of active archetype modifiers."""
        result = StyleModifiers()  # zeroed / defaults

        if not self._active:
            self._modifiers = result
            return

        # Collect weighted sum
        for i, name in enumerate(self._active):
            w = self._weights[i]
            m = self._archetype_mods.get(name)
            if m is None:
                continue

            result.aggression_mult += m.aggression_mult * w
            result.cooldown_mult += m.cooldown_mult * w
            result.block_readiness += m.block_readiness * w
            result.dodge_readiness += m.dodge_readiness * w
            result.feint_chance += m.feint_chance * w
            result.combo_complexity += m.combo_complexity * w
            result.chase_speed_mult += m.chase_speed_mult * w
            result.retreat_tendency += m.retreat_tendency * w
            result.spacing_offset += m.spacing_offset * w
            result.heavy_attack_bias += m.heavy_attack_bias * w
            result.punish_aggression += m.punish_aggression * w
            result.strafe_speed_mult += m.strafe_speed_mult * w
            result.movement_erratic += m.movement_erratic * w

        # Because we started from defaults (1.0 for mults, 0.0 for adds)
        # and added weighted values, we need to subtract the default offset
        # that's baked into the initial StyleModifiers() for multipliers.
        # Actually, since defaults are 1.0 for mults and we started from
        # StyleModifiers() defaults + weighted sums, we should just overwrite:
        self._modifiers = result

    def reset(self):
        """Full reset for a new fight."""
        self._active = random.sample(ALL_ARCHETYPES, k=self.cfg.blend_count)
        self._weights = self._init_weights()
        self._shift_timer = (
            self.cfg.style_shift_interval
            + random.uniform(-self.cfg.style_shift_jitter, self.cfg.style_shift_jitter)
        )
        self._staleness = {a: 0.0 for a in self._active}
        self._action_buffer.clear()
        self._archetype_mods = {
            name: ARCHETYPE_FACTORY[name]() for name in self._active
        }
        self._blend()
