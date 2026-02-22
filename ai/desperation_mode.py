"""
desperation_mode.py – Low-HP intelligence, comeback mechanics, and rage mode.

When enemy HP drops below a threshold, Desperation Mode activates:
- Aggression spikes
- Attack cooldowns shrink
- Combo probability increases
- Chase speed increases
- Defensive behavior decreases
- Enemy attempts comeback strategies
- Feints and attack cancels become available
- High-risk combo chains unlock

At critically low HP, Rage Mode triggers:
- Maximum aggression override
- Stamina costs partially ignored
- Relentless pressure with no retreat

The transition is gradual, not a binary switch – so it feels organic
rather than sudden difficulty spike.

Integrates with phase_system.py: Desperation phase starts at 30% HP,
Rage phase starts at 12% HP.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


# ══════════════════════════════════════════════════════════
#  Configuration
# ══════════════════════════════════════════════════════════

@dataclass
class DesperationConfig:
    """Tunable parameters for desperation mode."""

    # HP threshold to begin desperation scaling (fraction 0–1)
    activation_threshold: float = 0.30    # aligned with phase_system DESPERATION

    # Maximum modifiers at 0 HP (linear interpolation from threshold → 0)
    max_aggression_boost: float = 0.45
    max_cooldown_reduction: float = 0.45      # 45% faster attacks at 0 HP
    max_combo_chance_boost: float = 0.35
    max_chase_speed_boost: float = 0.40
    max_defense_reduction: float = 0.35       # reduce defensive bias
    max_risk_tolerance_boost: float = 0.40

    # Comeback burst: brief super-aggression when first entering desperation
    burst_duration: float = 1.5               # seconds of burst
    burst_aggression_extra: float = 0.20
    burst_cooldown_extra: float = 0.15

    # ── Feint system (desperation exclusive) ──────────────
    feint_chance_base: float = 0.10           # base feint chance in desperation
    feint_chance_max: float = 0.35            # at max intensity
    feint_cancel_window: float = 0.15         # seconds – window to cancel into real attack

    # ── Attack cancel ─────────────────────────────────────
    attack_cancel_chance: float = 0.12        # chance to cancel a committed attack into block
    attack_cancel_max: float = 0.30

    # ── High-risk combos ──────────────────────────────────
    risk_combo_chance: float = 0.15           # chance to attempt 3+ hit chain
    risk_combo_max: float = 0.40
    risk_combo_hits: int = 3                  # hits in a risk combo

    # ── Rage Mode ─────────────────────────────────────────
    rage_hp_threshold: float = 0.12           # aligned with phase_system RAGE
    rage_aggression_override: float = 0.70    # flat override (additive)
    rage_cooldown_floor: float = 0.20         # minimum cooldown in rage (seconds)
    rage_stamina_ignore: float = 0.60         # can attack at 60% of normal cost
    rage_retreat_override: float = 0.0        # never retreat in rage
    rage_block_override: float = 0.0          # never block in rage
    rage_chase_speed_override: float = 1.60


# ══════════════════════════════════════════════════════════
#  Desperation Modifiers (output)
# ══════════════════════════════════════════════════════════

@dataclass
class DesperationModifiers:
    """Applied per-frame when desperation is active."""
    active: bool = False
    intensity: float = 0.0            # 0.0 = just entered, 1.0 = near death

    aggression_boost: float = 0.0
    cooldown_mult: float = 1.0        # <1.0 = faster attacks
    combo_chance_boost: float = 0.0
    chase_speed_mult: float = 1.0
    defense_reduction: float = 0.0
    risk_tolerance_boost: float = 0.0

    # True during the initial burst window
    burst_active: bool = False

    # ── New: Feint / cancel / risk combo ──────────────────
    feint_chance: float = 0.0         # probability of feinting before attack
    attack_cancel_chance: float = 0.0 # probability of cancelling attack into block
    risk_combo_chance: float = 0.0    # probability of attempting a risk combo
    risk_combo_hits: int = 3          # how many hits in the risk combo

    # ── Rage mode ─────────────────────────────────────────
    rage_active: bool = False
    rage_stamina_ignore: float = 0.0  # fraction of stamina cost ignored
    rage_retreat_override: float = -1.0   # if >= 0, overrides retreat tendency
    rage_block_override: float = -1.0     # if >= 0, overrides block chance


# ══════════════════════════════════════════════════════════
#  Desperation Mode Controller
# ══════════════════════════════════════════════════════════

class DesperationMode:
    """Tracks enemy HP and produces gradual desperation modifiers.

    Usage:
        desp = DesperationMode()
        desp.update(dt, enemy_hp_frac)
        mods = desp.modifiers
        if mods.active:
            # apply mods.aggression_boost, mods.cooldown_mult, etc.
        if mods.rage_active:
            # rage mode overrides
    """

    def __init__(self, config: DesperationConfig | None = None):
        self.cfg = config or DesperationConfig()
        self._modifiers = DesperationModifiers()

        # Burst tracking
        self._burst_timer: float = 0.0
        self._was_active: bool = False
        self._was_rage: bool = False
        self._rage_burst_timer: float = 0.0

    @property
    def modifiers(self) -> DesperationModifiers:
        return self._modifiers

    @property
    def active(self) -> bool:
        return self._modifiers.active

    @property
    def rage_active(self) -> bool:
        return self._modifiers.rage_active

    def should_feint(self) -> bool:
        """Roll feint chance. Call once per attack decision."""
        if not self._modifiers.active:
            return False
        return random.random() < self._modifiers.feint_chance

    def should_cancel_attack(self) -> bool:
        """Roll attack cancel chance. Call during attack wind-up."""
        if not self._modifiers.active:
            return False
        return random.random() < self._modifiers.attack_cancel_chance

    def should_risk_combo(self) -> bool:
        """Roll risk combo chance. Call on hit confirm."""
        if not self._modifiers.active:
            return False
        return random.random() < self._modifiers.risk_combo_chance

    def update(self, dt: float, enemy_hp_frac: float):
        """Recalculate desperation modifiers. Call every frame."""
        cfg = self.cfg
        m = self._modifiers

        if enemy_hp_frac >= cfg.activation_threshold:
            # Not in desperation
            m.active = False
            m.intensity = 0.0
            m.aggression_boost = 0.0
            m.cooldown_mult = 1.0
            m.combo_chance_boost = 0.0
            m.chase_speed_mult = 1.0
            m.defense_reduction = 0.0
            m.risk_tolerance_boost = 0.0
            m.burst_active = False
            m.feint_chance = 0.0
            m.attack_cancel_chance = 0.0
            m.risk_combo_chance = 0.0
            m.rage_active = False
            m.rage_stamina_ignore = 0.0
            m.rage_retreat_override = -1.0
            m.rage_block_override = -1.0
            self._was_active = False
            self._was_rage = False
            return

        # ── Desperation is active ─────────────────────────
        m.active = True

        # Intensity: 0 at threshold, 1 at 0 HP
        m.intensity = 1.0 - (enemy_hp_frac / cfg.activation_threshold)
        m.intensity = max(0.0, min(1.0, m.intensity))

        # ── Burst on first activation ─────────────────────
        if not self._was_active:
            self._burst_timer = cfg.burst_duration
            self._was_active = True

        if self._burst_timer > 0:
            self._burst_timer -= dt
            m.burst_active = True
        else:
            m.burst_active = False

        # ── Scale modifiers linearly with intensity ───────
        t = m.intensity  # 0..1

        burst_aggr = cfg.burst_aggression_extra if m.burst_active else 0.0
        burst_cd = cfg.burst_cooldown_extra if m.burst_active else 0.0

        m.aggression_boost = t * cfg.max_aggression_boost + burst_aggr
        m.cooldown_mult = 1.0 - (t * cfg.max_cooldown_reduction + burst_cd)
        m.cooldown_mult = max(0.3, m.cooldown_mult)  # floor
        m.combo_chance_boost = t * cfg.max_combo_chance_boost
        m.chase_speed_mult = 1.0 + (t * cfg.max_chase_speed_boost)
        m.defense_reduction = t * cfg.max_defense_reduction
        m.risk_tolerance_boost = t * cfg.max_risk_tolerance_boost

        # ── Feint / cancel / risk combo scaling ───────────
        m.feint_chance = cfg.feint_chance_base + t * (cfg.feint_chance_max - cfg.feint_chance_base)
        m.attack_cancel_chance = cfg.attack_cancel_chance + t * (cfg.attack_cancel_max - cfg.attack_cancel_chance)
        m.risk_combo_chance = cfg.risk_combo_chance + t * (cfg.risk_combo_max - cfg.risk_combo_chance)
        m.risk_combo_hits = cfg.risk_combo_hits

        # ── Rage Mode ─────────────────────────────────────
        if enemy_hp_frac <= cfg.rage_hp_threshold:
            m.rage_active = True

            # Rage burst on first entry
            if not self._was_rage:
                self._rage_burst_timer = cfg.burst_duration * 0.8
                self._was_rage = True

            if self._rage_burst_timer > 0:
                self._rage_burst_timer -= dt

            # Rage overrides
            m.aggression_boost = max(m.aggression_boost, cfg.rage_aggression_override)
            m.cooldown_mult = min(m.cooldown_mult, cfg.rage_cooldown_floor / 0.6)  # ensure fast
            m.chase_speed_mult = max(m.chase_speed_mult, cfg.rage_chase_speed_override)
            m.rage_stamina_ignore = cfg.rage_stamina_ignore
            m.rage_retreat_override = cfg.rage_retreat_override
            m.rage_block_override = cfg.rage_block_override
        else:
            m.rage_active = False
            m.rage_stamina_ignore = 0.0
            m.rage_retreat_override = -1.0
            m.rage_block_override = -1.0

    def reset(self):
        self._modifiers = DesperationModifiers()
        self._burst_timer = 0.0
        self._was_active = False
        self._was_rage = False
        self._rage_burst_timer = 0.0
