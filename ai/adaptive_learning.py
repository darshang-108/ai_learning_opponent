"""
adaptive_learning.py – Real-time per-match player pattern learning.

Tracks the player's combat habits *within* the current match and builds
a confidence model the AI uses to predict and counter player behaviour.

Tracked patterns:
  - Attack frequency & rhythm (attacks per second, interval variance)
  - Combo repetition (repeated identical sequences)
  - Distance preference (close / mid / far engagement bias)
  - Block / dodge frequency after being hit
  - Stamina management habits (reckless vs conservative)
  - Post-hit behaviour (retreat vs follow-up)

Output:
  - PlayerProfile dataclass with normalised scores (0.0–1.0)
  - confidence: how sure the AI is about its model (0.0–1.0)
  - CounterAdvice: per-frame suggestions consumed by ai_core

The system NEVER persists across matches — it resets each fight so
the player can change style and the AI must re-learn.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field


# ══════════════════════════════════════════════════════════
#  Configuration
# ══════════════════════════════════════════════════════════

@dataclass
class LearningConfig:
    """Tunables for the adaptive learning system."""

    # Rolling window for events (seconds)
    event_window: float = 8.0

    # Confidence growth rate per meaningful observation
    confidence_per_event: float = 0.012
    confidence_decay_rate: float = 0.002     # per second of inactivity
    confidence_max: float = 1.0

    # Attack rhythm
    rhythm_spike_threshold: float = 0.15     # interval variance below this = rhythmic

    # Combo tracking
    combo_memory_size: int = 12              # last N attacks to track sequences
    combo_repeat_weight: float = 0.25        # confidence boost per repeated combo

    # Distance preference bins (pixels)
    close_range: float = 80.0
    mid_range: float = 160.0
    # anything beyond mid_range is "far"

    # Minimum events before producing advice
    min_events_for_advice: int = 4


# ══════════════════════════════════════════════════════════
#  Player Profile (output)
# ══════════════════════════════════════════════════════════

@dataclass
class PlayerProfile:
    """Learned model of the player's combat tendencies (0.0–1.0 each)."""

    # Attack patterns
    attack_frequency: float = 0.5       # 0 = passive, 1 = spam
    attack_rhythm: float = 0.0          # 0 = erratic, 1 = metronomic
    combo_repetition: float = 0.0       # how often they repeat combos
    heavy_attack_ratio: float = 0.5     # 0 = all quick, 1 = all heavy

    # Positioning
    preferred_range: str = "mid"        # "close" | "mid" | "far"
    range_close_bias: float = 0.33
    range_mid_bias: float = 0.34
    range_far_bias: float = 0.33

    # Defensive habits
    block_after_hit: float = 0.0        # probability of blocking after taking a hit
    dodge_frequency: float = 0.0        # dodges per engagement
    retreat_after_attack: float = 0.0   # does player retreat after attacking?

    # Stamina
    stamina_reckless: float = 0.5       # 0 = conservative, 1 = drains to zero


# ══════════════════════════════════════════════════════════
#  Counter Advice (output consumed by ai_core)
# ══════════════════════════════════════════════════════════

@dataclass
class CounterAdvice:
    """Per-frame tactical suggestions derived from the player profile."""

    # Timing
    reaction_delay_adj: float = 0.0     # negative = respond faster, positive = wait
    punish_probability: float = 0.3     # how likely AI should punish openings
    feint_rate: float = 0.0             # how often AI should feint to lure reactions

    # Attack behaviour
    aggression_adj: float = 0.0         # additive adjustment to aggression
    combo_complexity: float = 0.5       # 0 = simple, 1 = complex / varied
    heavy_bias: float = 0.0             # bias toward heavy attacks

    # Spacing
    preferred_engage_dist: float = 70.0 # optimal distance to engage from
    approach_speed_mult: float = 1.0    # adjust chase speed

    # Defence
    block_readiness: float = 0.3        # how ready AI should be to block
    dodge_readiness: float = 0.1        # how ready AI should be to dodge


# ══════════════════════════════════════════════════════════
#  Internal Event Types
# ══════════════════════════════════════════════════════════

@dataclass
class _AttackEvent:
    """Timestamped record of a single player attack."""

    time: float
    attack_type: str      # "quick" | "heavy"
    distance: float
    hit: bool             # did it connect?

@dataclass
class _DefenseEvent:
    """Timestamped record of a player defensive action."""

    time: float
    action: str           # "block" | "dodge" | "nothing"
    after_hit: bool       # was this after the player took damage?

@dataclass
class _PositionSample:
    """Timestamped distance sample for range-preference analysis."""

    time: float
    distance: float


# ══════════════════════════════════════════════════════════
#  Adaptive Learning System
# ══════════════════════════════════════════════════════════

class AdaptiveLearning:
    """Observes the player every frame and builds a real-time model.

    Usage:
        learner = AdaptiveLearning()
        # every frame:
        learner.observe(dt, now, player, enemy, distance)
        profile = learner.profile
        advice  = learner.advice
        conf    = learner.confidence
    """

    def __init__(self, config: LearningConfig | None = None):
        self.cfg = config or LearningConfig()

        self._profile = PlayerProfile()
        self._advice = CounterAdvice()
        self._confidence: float = 0.0

        # ── Event logs ────────────────────────────────────
        self._attacks: deque[_AttackEvent] = deque(maxlen=200)
        self._defenses: deque[_DefenseEvent] = deque(maxlen=100)
        self._positions: deque[_PositionSample] = deque(maxlen=300)
        self._combo_history: deque[str] = deque(maxlen=self.cfg.combo_memory_size)

        # ── Observation state ─────────────────────────────
        self._player_was_attacking: bool = False
        self._player_was_blocking: bool = False
        self._player_was_dodging: bool = False
        self._player_just_took_hit: bool = False
        self._hit_cooldown: float = 0.0
        self._last_player_stamina: float = 1.0
        self._inactivity_timer: float = 0.0
        self._reanalyze_timer: float = 0.0

    # ── Properties ────────────────────────────────────────

    @property
    def profile(self) -> PlayerProfile:
        return self._profile

    @property
    def advice(self) -> CounterAdvice:
        return self._advice

    @property
    def confidence(self) -> float:
        return self._confidence

    # ══════════════════════════════════════════════════════
    #  Main Observation (call every frame)
    # ══════════════════════════════════════════════════════

    def observe(self, dt: float, now: float, player, enemy, distance: float):
        """Observe player actions and update the learned model."""

        cfg = self.cfg

        # ── Position sampling ─────────────────────────────
        self._positions.append(_PositionSample(time=now, distance=distance))

        # ── Detect player attack start ────────────────────
        player_attacking = getattr(player, 'is_attacking', False)
        if player_attacking and not self._player_was_attacking:
            # New attack started
            atk_type = getattr(player, 'current_attack_type', 'quick')
            if not isinstance(atk_type, str):
                atk_type = 'quick'
            hit = distance <= 90  # rough hit-check
            self._attacks.append(_AttackEvent(
                time=now, attack_type=atk_type, distance=distance, hit=hit
            ))
            self._combo_history.append(atk_type)
            self._confidence = min(cfg.confidence_max,
                                   self._confidence + cfg.confidence_per_event)
            self._inactivity_timer = 0.0
        self._player_was_attacking = player_attacking

        # ── Detect defence actions ────────────────────────
        player_blocking = getattr(player, 'is_blocking', False)
        player_dodging = getattr(player, 'is_dodging', False)

        if player_blocking and not self._player_was_blocking:
            self._defenses.append(_DefenseEvent(
                time=now, action="block",
                after_hit=self._player_just_took_hit
            ))
            self._confidence = min(cfg.confidence_max,
                                   self._confidence + cfg.confidence_per_event * 0.5)
        self._player_was_blocking = player_blocking

        if player_dodging and not self._player_was_dodging:
            self._defenses.append(_DefenseEvent(
                time=now, action="dodge",
                after_hit=self._player_just_took_hit
            ))
            self._confidence = min(cfg.confidence_max,
                                   self._confidence + cfg.confidence_per_event * 0.5)
        self._player_was_dodging = player_dodging

        # ── Track "just took hit" window ──────────────────
        if self._hit_cooldown > 0:
            self._hit_cooldown -= dt
            if self._hit_cooldown <= 0:
                self._player_just_took_hit = False

        # ── Stamina tracking ──────────────────────────────
        stam_frac = 1.0
        if hasattr(player, 'stamina_component'):
            stam_frac = player.stamina_component.fraction
        self._last_player_stamina = stam_frac

        # ── Inactivity decay ─────────────────────────────
        self._inactivity_timer += dt
        if self._inactivity_timer > 2.0:
            self._confidence = max(0.0,
                                   self._confidence - cfg.confidence_decay_rate * dt)

        # ── Periodic re-analysis ──────────────────────────
        self._reanalyze_timer -= dt
        if self._reanalyze_timer <= 0:
            self._reanalyze_timer = 0.5  # re-analyze twice per second
            self._analyze(now)

    def notify_player_hit(self):
        """Call when the player takes damage — triggers 'after_hit' tracking."""
        self._player_just_took_hit = True
        self._hit_cooldown = 1.0

    # ══════════════════════════════════════════════════════
    #  Analysis (periodic)
    # ══════════════════════════════════════════════════════

    def _analyze(self, now: float):
        """Rebuild profile and advice from collected events."""
        cfg = self.cfg
        p = self._profile
        cutoff = now - cfg.event_window

        # ── Filter recent events ──────────────────────────
        recent_attacks = [a for a in self._attacks if a.time >= cutoff]
        recent_defenses = [d for d in self._defenses if d.time >= cutoff]
        recent_positions = [s for s in self._positions if s.time >= cutoff]

        # ── Attack frequency ──────────────────────────────
        n_attacks = len(recent_attacks)
        if n_attacks >= 2:
            span = recent_attacks[-1].time - recent_attacks[0].time
            if span > 0:
                apm = n_attacks / span  # attacks per second
                p.attack_frequency = min(1.0, apm / 3.0)  # 3 atk/s = max

                # Rhythm: compute interval variance
                intervals = [
                    recent_attacks[i].time - recent_attacks[i - 1].time
                    for i in range(1, len(recent_attacks))
                ]
                if intervals:
                    mean_int = sum(intervals) / len(intervals)
                    variance = sum((iv - mean_int) ** 2 for iv in intervals) / len(intervals)
                    std_dev = math.sqrt(variance)
                    # Low std_dev = rhythmic
                    p.attack_rhythm = max(0.0, 1.0 - std_dev / max(0.01, mean_int))
            else:
                p.attack_frequency = 0.5
                p.attack_rhythm = 0.0
        else:
            p.attack_frequency = 0.3
            p.attack_rhythm = 0.0

        # ── Heavy ratio ───────────────────────────────────
        if recent_attacks:
            heavies = sum(1 for a in recent_attacks if a.attack_type == "heavy")
            p.heavy_attack_ratio = heavies / len(recent_attacks)

        # ── Combo repetition ──────────────────────────────
        if len(self._combo_history) >= 4:
            # Check for repeated 2-hit and 3-hit patterns
            recent_seq = list(self._combo_history)
            repeats = 0
            total_checks = 0
            for length in (2, 3):
                for i in range(len(recent_seq) - length * 2 + 1):
                    pattern = tuple(recent_seq[i:i + length])
                    next_pattern = tuple(recent_seq[i + length:i + length * 2])
                    if pattern == next_pattern:
                        repeats += 1
                    total_checks += 1
            p.combo_repetition = repeats / max(1, total_checks)
        else:
            p.combo_repetition = 0.0

        # ── Distance preference ───────────────────────────
        if recent_positions:
            close_count = sum(1 for s in recent_positions if s.distance < cfg.close_range)
            mid_count = sum(1 for s in recent_positions
                           if cfg.close_range <= s.distance < cfg.mid_range)
            far_count = sum(1 for s in recent_positions if s.distance >= cfg.mid_range)
            total = close_count + mid_count + far_count
            if total > 0:
                p.range_close_bias = close_count / total
                p.range_mid_bias = mid_count / total
                p.range_far_bias = far_count / total
                if p.range_close_bias >= p.range_mid_bias and p.range_close_bias >= p.range_far_bias:
                    p.preferred_range = "close"
                elif p.range_far_bias >= p.range_mid_bias:
                    p.preferred_range = "far"
                else:
                    p.preferred_range = "mid"

        # ── Defensive habits ──────────────────────────────
        if recent_defenses:
            blocks = [d for d in recent_defenses if d.action == "block"]
            dodges = [d for d in recent_defenses if d.action == "dodge"]
            after_hit_blocks = [d for d in recent_defenses
                                if d.action == "block" and d.after_hit]

            n_def = len(recent_defenses)
            p.dodge_frequency = min(1.0, len(dodges) / max(1, n_def))
            p.block_after_hit = min(1.0, len(after_hit_blocks) / max(1, len(blocks) + 1))
        else:
            p.dodge_frequency = 0.0
            p.block_after_hit = 0.0

        # ── Post-attack retreat ───────────────────────────
        if len(recent_attacks) >= 2:
            retreat_count = 0
            for i in range(len(recent_attacks) - 1):
                # If distance increased after attack, player retreated
                next_dist = recent_attacks[i + 1].distance
                this_dist = recent_attacks[i].distance
                if next_dist > this_dist + 20:
                    retreat_count += 1
            p.retreat_after_attack = retreat_count / max(1, len(recent_attacks) - 1)

        # ── Stamina recklessness ──────────────────────────
        # If player attacks when stamina is low, they're reckless
        if recent_attacks:
            # Proxy: high attack frequency + any event at low distance = reckless
            p.stamina_reckless = min(1.0, p.attack_frequency * 1.2
                                     + (1.0 - self._last_player_stamina) * 0.5)

        # ══════════════════════════════════════════════════
        #  Generate Counter Advice
        # ══════════════════════════════════════════════════
        self._generate_advice(p, n_attacks)

    def _generate_advice(self, p: PlayerProfile, n_events: int):
        """Convert the player profile into actionable AI directives."""
        cfg = self.cfg
        a = self._advice

        if n_events < cfg.min_events_for_advice:
            # Not enough data → defaults
            a.reaction_delay_adj = 0.0
            a.punish_probability = 0.3
            a.feint_rate = 0.0
            a.aggression_adj = 0.0
            a.combo_complexity = 0.5
            a.heavy_bias = 0.0
            a.preferred_engage_dist = 70.0
            a.approach_speed_mult = 1.0
            a.block_readiness = 0.3
            a.dodge_readiness = 0.1
            return

        # ── Counter rhythmic players → vary timing ────────
        if p.attack_rhythm > 0.6:
            a.reaction_delay_adj = -0.05  # respond faster to exploit rhythm gaps
            a.feint_rate = min(0.35, p.attack_rhythm * 0.4)
        else:
            a.reaction_delay_adj = 0.0
            a.feint_rate = 0.05

        # ── Counter spam → punish more ────────────────────
        if p.attack_frequency > 0.7:
            a.punish_probability = min(0.8, 0.3 + (p.attack_frequency - 0.5) * 1.0)
            a.block_readiness = min(0.7, 0.3 + p.attack_frequency * 0.4)
            a.aggression_adj = -0.10  # wait for openings
        else:
            a.punish_probability = 0.3 + p.attack_frequency * 0.2
            a.block_readiness = 0.3

        # ── Counter combo repeaters → dodge / vary ────────
        if p.combo_repetition > 0.4:
            a.dodge_readiness = min(0.5, p.combo_repetition * 0.8)
            a.feint_rate = max(a.feint_rate, p.combo_repetition * 0.3)

        # ── Counter close-range players → keep distance ───
        if p.preferred_range == "close":
            a.preferred_engage_dist = 90.0
            a.approach_speed_mult = 0.90  # don't rush in
            a.aggression_adj = max(a.aggression_adj, 0.05)  # but still be active
        elif p.preferred_range == "far":
            a.preferred_engage_dist = 55.0
            a.approach_speed_mult = 1.25  # close the gap
            a.aggression_adj = max(a.aggression_adj, 0.10)

        # ── Counter heavy-attack users → faster response ──
        if p.heavy_attack_ratio > 0.5:
            a.reaction_delay_adj = min(a.reaction_delay_adj, -0.03)
            a.dodge_readiness = max(a.dodge_readiness, 0.3)
            a.heavy_bias = -0.20  # AI uses quick attacks to punish slow swings

        # ── Counter defensive players → aggression + guard-break ──
        if p.block_after_hit > 0.5:
            a.aggression_adj = max(a.aggression_adj, 0.15)
            a.heavy_bias = max(a.heavy_bias, 0.25)  # heavy to break guard
            a.feint_rate = max(a.feint_rate, 0.15)

        # ── Stamina reckless players → drain & punish ─────
        if p.stamina_reckless > 0.7:
            a.punish_probability = min(0.85, a.punish_probability + 0.15)
            a.aggression_adj = max(a.aggression_adj, 0.05)

        # ── Combo complexity: match or exceed player ──────
        a.combo_complexity = min(1.0, 0.3 + self._confidence * 0.5
                                 + (1.0 - p.combo_repetition) * 0.2)

    # ══════════════════════════════════════════════════════
    #  Reset
    # ══════════════════════════════════════════════════════

    def reset(self):
        """Clear all learned data (new fight)."""
        self._profile = PlayerProfile()
        self._advice = CounterAdvice()
        self._confidence = 0.0
        self._attacks.clear()
        self._defenses.clear()
        self._positions.clear()
        self._combo_history.clear()
        self._player_was_attacking = False
        self._player_was_blocking = False
        self._player_was_dodging = False
        self._player_just_took_hit = False
        self._hit_cooldown = 0.0
        self._last_player_stamina = 1.0
        self._inactivity_timer = 0.0
        self._reanalyze_timer = 0.0
