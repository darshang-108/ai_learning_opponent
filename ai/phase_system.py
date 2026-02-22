"""
phase_system.py – Combat Phase State Machine.

Drives the strategic arc of each fight through four escalating phases:

  Phase 1 – OBSERVE   : AI studies the player, gathers pattern data, plays safe.
  Phase 2 – COUNTER   : AI exploits learned patterns, increases precision.
  Phase 3 – DESPERATION: HP below 30%, high-risk combos, feints, all-in.
  Phase 4 – RAGE      : Final stand, maximum aggression, ignores stamina cost.

Phase transitions are driven by a combination of:
  - Time in fight
  - HP thresholds
  - Confidence score (how much the AI has "learned")
  - Damage exchange ratio

The system outputs PhaseModifiers that other systems consume to adjust behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


# ══════════════════════════════════════════════════════════
#  Phase Enum
# ══════════════════════════════════════════════════════════

class CombatPhase(IntEnum):
    """Discrete phases of AI combat behavior escalation."""

    OBSERVE = 0
    COUNTER = 1
    DESPERATION = 2
    RAGE = 3


# ══════════════════════════════════════════════════════════
#  Configuration
# ══════════════════════════════════════════════════════════

@dataclass
class PhaseConfig:
    """Tunable knobs for phase transitions and per-phase modifiers."""

    # ── Transition thresholds ─────────────────────────────
    observe_min_duration: float = 4.0        # minimum seconds in Observe
    observe_exit_confidence: float = 0.35    # confidence score to leave Observe
    counter_hp_enter: float = 1.0            # can enter Counter above this HP frac
    desperation_hp_threshold: float = 0.30   # enter Desperation below this
    rage_hp_threshold: float = 0.12          # enter Rage below this

    # ── Observe phase modifiers ───────────────────────────
    observe_aggression_mult: float = 0.65    # play safe
    observe_block_bonus: float = 0.15        # block more to study
    observe_cooldown_mult: float = 1.25      # slower attacks
    observe_combo_mult: float = 0.50         # fewer combos
    observe_chase_mult: float = 0.85         # don't rush

    # ── Counter phase modifiers ───────────────────────────
    counter_aggression_mult: float = 1.15
    counter_block_bonus: float = 0.05
    counter_cooldown_mult: float = 0.88
    counter_combo_mult: float = 1.20
    counter_punish_mult: float = 1.40
    counter_chase_mult: float = 1.10

    # ── Desperation phase modifiers ───────────────────────
    desp_aggression_mult: float = 1.35
    desp_block_bonus: float = -0.10          # blocks less, attacks more
    desp_cooldown_mult: float = 0.70
    desp_combo_mult: float = 1.50
    desp_chase_mult: float = 1.35
    desp_feint_chance: float = 0.20          # chance to feint before real attack
    desp_risk_boost: float = 0.30

    # ── Rage phase modifiers ──────────────────────────────
    rage_aggression_mult: float = 1.60
    rage_block_bonus: float = -0.25          # basically never blocks
    rage_cooldown_mult: float = 0.50
    rage_combo_mult: float = 1.80
    rage_chase_mult: float = 1.55
    rage_risk_boost: float = 0.50
    rage_feint_chance: float = 0.30
    rage_stamina_ignore_frac: float = 0.60   # attacks even at 60% stam cost


# ══════════════════════════════════════════════════════════
#  Phase Modifiers (output)
# ══════════════════════════════════════════════════════════

@dataclass
class PhaseModifiers:
    """Per-frame modifiers produced by the phase system."""
    phase: CombatPhase = CombatPhase.OBSERVE
    aggression_mult: float = 1.0
    block_bonus: float = 0.0
    cooldown_mult: float = 1.0
    combo_mult: float = 1.0
    punish_mult: float = 1.0
    chase_mult: float = 1.0
    feint_chance: float = 0.0
    risk_boost: float = 0.0
    stamina_ignore_frac: float = 0.0

    # Transition event flags (True for ONE frame on phase change)
    just_transitioned: bool = False
    previous_phase: CombatPhase = CombatPhase.OBSERVE


# ══════════════════════════════════════════════════════════
#  Phase System Controller
# ══════════════════════════════════════════════════════════

class PhaseSystem:
    """Manages combat phase transitions and produces per-frame modifiers.

    Usage:
        ps = PhaseSystem()
        ps.update(dt, enemy_hp_frac, confidence, flow_ratio)
        mods = ps.modifiers
        if mods.just_transitioned:
            # trigger VFX / cinematic
    """

    def __init__(self, config: PhaseConfig | None = None):
        self.cfg = config or PhaseConfig()
        self._phase = CombatPhase.OBSERVE
        self._phase_timer: float = 0.0      # time spent in current phase
        self._fight_timer: float = 0.0       # total fight duration
        self._modifiers = PhaseModifiers()
        self._transition_flag: bool = False

    @property
    def phase(self) -> CombatPhase:
        return self._phase

    @property
    def modifiers(self) -> PhaseModifiers:
        return self._modifiers

    @property
    def phase_name(self) -> str:
        return self._phase.name

    def update(self, dt: float, enemy_hp_frac: float,
               confidence: float, flow_ratio: float):
        """Evaluate phase transitions and compute modifiers. Call every frame.

        Args:
            dt: frame delta time in seconds.
            enemy_hp_frac: enemy HP as fraction 0.0–1.0.
            confidence: adaptive learning confidence 0.0–1.0 (how well AI knows player).
            flow_ratio: -1.0 (losing) to +1.0 (winning) from match flow tracker.
        """
        self._fight_timer += dt
        self._phase_timer += dt
        cfg = self.cfg

        old_phase = self._phase

        # ── Phase transitions (priority: highest phase wins) ──
        if enemy_hp_frac <= cfg.rage_hp_threshold and self._phase != CombatPhase.RAGE:
            self._phase = CombatPhase.RAGE

        elif enemy_hp_frac <= cfg.desperation_hp_threshold and self._phase < CombatPhase.DESPERATION:
            self._phase = CombatPhase.DESPERATION

        elif (self._phase == CombatPhase.OBSERVE
              and self._phase_timer >= cfg.observe_min_duration
              and confidence >= cfg.observe_exit_confidence):
            self._phase = CombatPhase.COUNTER

        # Also allow forced Counter entry if fight has dragged on
        elif (self._phase == CombatPhase.OBSERVE
              and self._fight_timer > cfg.observe_min_duration * 2.5):
            self._phase = CombatPhase.COUNTER

        # ── Detect transition ─────────────────────────────
        transitioned = self._phase != old_phase
        if transitioned:
            self._phase_timer = 0.0

        # ── Compute modifiers based on current phase ──────
        m = self._modifiers
        m.phase = self._phase
        m.just_transitioned = transitioned
        m.previous_phase = old_phase

        if self._phase == CombatPhase.OBSERVE:
            m.aggression_mult = cfg.observe_aggression_mult
            m.block_bonus = cfg.observe_block_bonus
            m.cooldown_mult = cfg.observe_cooldown_mult
            m.combo_mult = cfg.observe_combo_mult
            m.punish_mult = 1.0
            m.chase_mult = cfg.observe_chase_mult
            m.feint_chance = 0.0
            m.risk_boost = 0.0
            m.stamina_ignore_frac = 0.0

        elif self._phase == CombatPhase.COUNTER:
            m.aggression_mult = cfg.counter_aggression_mult
            m.block_bonus = cfg.counter_block_bonus
            m.cooldown_mult = cfg.counter_cooldown_mult
            m.combo_mult = cfg.counter_combo_mult
            m.punish_mult = cfg.counter_punish_mult
            m.chase_mult = cfg.counter_chase_mult
            m.feint_chance = 0.0
            m.risk_boost = 0.0
            m.stamina_ignore_frac = 0.0

        elif self._phase == CombatPhase.DESPERATION:
            m.aggression_mult = cfg.desp_aggression_mult
            m.block_bonus = cfg.desp_block_bonus
            m.cooldown_mult = cfg.desp_cooldown_mult
            m.combo_mult = cfg.desp_combo_mult
            m.punish_mult = cfg.counter_punish_mult  # keep counter-level
            m.chase_mult = cfg.desp_chase_mult
            m.feint_chance = cfg.desp_feint_chance
            m.risk_boost = cfg.desp_risk_boost
            m.stamina_ignore_frac = 0.0

        elif self._phase == CombatPhase.RAGE:
            m.aggression_mult = cfg.rage_aggression_mult
            m.block_bonus = cfg.rage_block_bonus
            m.cooldown_mult = cfg.rage_cooldown_mult
            m.combo_mult = cfg.rage_combo_mult
            m.punish_mult = cfg.counter_punish_mult
            m.chase_mult = cfg.rage_chase_mult
            m.feint_chance = cfg.rage_feint_chance
            m.risk_boost = cfg.rage_risk_boost
            m.stamina_ignore_frac = cfg.rage_stamina_ignore_frac

    def reset(self):
        """Reset to Observe phase (new fight)."""
        self._phase = CombatPhase.OBSERVE
        self._phase_timer = 0.0
        self._fight_timer = 0.0
        self._modifiers = PhaseModifiers()
