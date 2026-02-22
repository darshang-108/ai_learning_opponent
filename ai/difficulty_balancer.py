"""
difficulty_balancer.py – Dynamic rubber-banding difficulty system.

Ensures fights stay engaging regardless of skill gap by adjusting AI
behaviour in real-time:

  Player struggling (getting dominated)  →  AI eases up:
    - Increase reaction delay
    - Reduce combo length / complexity
    - Lower aggression
    - Add telegraphing to attacks
    - Slightly reduce accuracy

  Player dominating (easy fight)  →  AI sharpens:
    - Increase punish precision
    - Reduce recovery windows
    - Increase attack variation
    - Tighten spacing control
    - Higher aggression

The system is invisible to the player — it feels like the AI is
naturally adaptive rather than artificially rubber-banding.

Input: ongoing match stats (damage ratio, hit ratio, combo success, etc.)
Output: DifficultyModifiers consumed by ai_core every frame.
"""

from __future__ import annotations

from dataclasses import dataclass


# ══════════════════════════════════════════════════════════
#  Configuration
# ══════════════════════════════════════════════════════════

@dataclass
class BalancerConfig:
    """Tunable knobs for the difficulty balancer."""

    # How aggressively the balancer adjusts (0.0 = off, 1.0 = maximum)
    strength: float = 0.65

    # Score thresholds for triggering adjustments
    ease_threshold: float = -0.25      # below this → player struggling
    sharpen_threshold: float = 0.25    # above this → player dominating

    # Smooth rate (per second) – prevents jarring instant shifts
    smooth_rate: float = 1.5

    # ── Ease-up modifiers (when player struggles) ─────────
    ease_reaction_delay_add: float = 0.08    # seconds slower
    ease_aggression_mult: float = 0.70
    ease_cooldown_mult: float = 1.35
    ease_combo_mult: float = 0.50
    ease_accuracy_mult: float = 0.80         # attack range check is looser
    ease_telegraph_add: float = 0.20         # chance to "telegraph" (slow wind-up)

    # ── Sharpen modifiers (when player dominates) ─────────
    sharp_reaction_delay_add: float = -0.04  # faster response
    sharp_aggression_mult: float = 1.30
    sharp_cooldown_mult: float = 0.80
    sharp_combo_mult: float = 1.40
    sharp_punish_mult: float = 1.50
    sharp_variation: float = 0.80            # how varied attacks become
    sharp_spacing_tightness: float = 1.25    # tighter spacing control


# ══════════════════════════════════════════════════════════
#  Difficulty Modifiers (output)
# ══════════════════════════════════════════════════════════

@dataclass
class DifficultyModifiers:
    """Per-frame modifiers produced by the difficulty balancer."""
    balance_score: float = 0.0           # -1 (enemy dominating) to +1 (player dominating)

    reaction_delay_adj: float = 0.0      # seconds: positive = slower AI
    aggression_mult: float = 1.0
    cooldown_mult: float = 1.0
    combo_mult: float = 1.0
    accuracy_mult: float = 1.0
    telegraph_chance: float = 0.0        # chance AI "telegraphs" attacks
    punish_mult: float = 1.0
    variation_boost: float = 0.0         # additive to combo complexity
    spacing_tightness: float = 1.0       # multiplier on spacing precision


# ══════════════════════════════════════════════════════════
#  Match Stats Tracker
# ══════════════════════════════════════════════════════════

class _MatchStats:
    """Accumulates combat statistics for balance scoring."""

    def __init__(self):
        self.player_damage_dealt: int = 0
        self.player_damage_taken: int = 0
        self.player_hits: int = 0
        self.player_misses: int = 0
        self.player_blocks_success: int = 0
        self.player_dodges: int = 0
        self.enemy_hits: int = 0
        self.enemy_misses: int = 0
        self.rounds_player_won: int = 0
        self.rounds_enemy_won: int = 0
        self.total_fight_time: float = 0.0

    def damage_ratio(self) -> float:
        """Positive = player doing more damage, negative = enemy doing more."""
        total = self.player_damage_dealt + self.player_damage_taken
        if total == 0:
            return 0.0
        return (self.player_damage_dealt - self.player_damage_taken) / total

    def hit_ratio(self) -> float:
        """Player hit accuracy advantage. Positive = player more accurate."""
        p_total = self.player_hits + self.player_misses
        e_total = self.enemy_hits + self.enemy_misses
        p_acc = self.player_hits / max(1, p_total)
        e_acc = self.enemy_hits / max(1, e_total)
        return p_acc - e_acc

    def defense_score(self) -> float:
        """How well the player is defending (0–1)."""
        total_attacks_on_player = self.enemy_hits + self.player_blocks_success + self.player_dodges
        if total_attacks_on_player == 0:
            return 0.5
        defended = self.player_blocks_success + self.player_dodges
        return defended / total_attacks_on_player

    def balance_score(self) -> float:
        """Overall balance score: -1 (enemy dominating) to +1 (player dominating)."""
        dmg = self.damage_ratio() * 0.50
        hit = self.hit_ratio() * 0.25
        defense = (self.defense_score() - 0.5) * 0.25
        return max(-1.0, min(1.0, dmg + hit + defense))


# ══════════════════════════════════════════════════════════
#  Difficulty Balancer
# ══════════════════════════════════════════════════════════

class DifficultyBalancer:
    """Dynamic difficulty adjustment via rubber-banding.

    Usage:
        balancer = DifficultyBalancer()
        # record events:
        balancer.record_player_hit(damage)
        balancer.record_enemy_hit(damage)
        # every frame:
        balancer.update(dt)
        mods = balancer.modifiers
    """

    def __init__(self, config: BalancerConfig | None = None):
        self.cfg = config or BalancerConfig()
        self._stats = _MatchStats()
        self._modifiers = DifficultyModifiers()

        # Smoothed balance score
        self._smooth_score: float = 0.0

    @property
    def modifiers(self) -> DifficultyModifiers:
        return self._modifiers

    @property
    def balance_score(self) -> float:
        return self._smooth_score

    # ══════════════════════════════════════════════════════
    #  Event Recording
    # ══════════════════════════════════════════════════════

    def record_player_hit(self, damage: int):
        """Player successfully hit the enemy."""
        self._stats.player_damage_dealt += damage
        self._stats.player_hits += 1

    def record_player_miss(self):
        """Player attack missed / was blocked."""
        self._stats.player_misses += 1

    def record_enemy_hit(self, damage: int):
        """Enemy successfully hit the player."""
        self._stats.player_damage_taken += damage
        self._stats.enemy_hits += 1

    def record_enemy_miss(self):
        """Enemy attack missed / was blocked."""
        self._stats.enemy_misses += 1

    def record_player_block(self):
        """Player successfully blocked an attack."""
        self._stats.player_blocks_success += 1

    def record_player_dodge(self):
        """Player successfully dodged an attack."""
        self._stats.player_dodges += 1

    def record_round_result(self, player_won: bool):
        """Record round outcome for cross-round balancing."""
        if player_won:
            self._stats.rounds_player_won += 1
        else:
            self._stats.rounds_enemy_won += 1

    # ══════════════════════════════════════════════════════
    #  Update (call every frame)
    # ══════════════════════════════════════════════════════

    def update(self, dt: float):
        """Recalculate difficulty modifiers based on accumulated stats."""
        self._stats.total_fight_time += dt
        cfg = self.cfg

        raw_score = self._stats.balance_score()

        # Smooth toward raw
        diff = raw_score - self._smooth_score
        self._smooth_score += diff * min(1.0, cfg.smooth_rate * dt)
        self._smooth_score = max(-1.0, min(1.0, self._smooth_score))

        m = self._modifiers
        m.balance_score = self._smooth_score
        s = cfg.strength

        if self._smooth_score < cfg.ease_threshold:
            # ── Player struggling → ease up ───────────────
            intensity = min(1.0, abs(self._smooth_score - cfg.ease_threshold)
                           / (1.0 - abs(cfg.ease_threshold)))
            t = intensity * s

            m.reaction_delay_adj = cfg.ease_reaction_delay_add * t
            m.aggression_mult = 1.0 + (cfg.ease_aggression_mult - 1.0) * t
            m.cooldown_mult = 1.0 + (cfg.ease_cooldown_mult - 1.0) * t
            m.combo_mult = 1.0 + (cfg.ease_combo_mult - 1.0) * t
            m.accuracy_mult = 1.0 + (cfg.ease_accuracy_mult - 1.0) * t
            m.telegraph_chance = cfg.ease_telegraph_add * t
            m.punish_mult = 1.0
            m.variation_boost = 0.0
            m.spacing_tightness = 1.0

        elif self._smooth_score > cfg.sharpen_threshold:
            # ── Player dominating → sharpen AI ────────────
            intensity = min(1.0, (self._smooth_score - cfg.sharpen_threshold)
                           / (1.0 - cfg.sharpen_threshold))
            t = intensity * s

            m.reaction_delay_adj = cfg.sharp_reaction_delay_add * t
            m.aggression_mult = 1.0 + (cfg.sharp_aggression_mult - 1.0) * t
            m.cooldown_mult = 1.0 + (cfg.sharp_cooldown_mult - 1.0) * t
            m.combo_mult = 1.0 + (cfg.sharp_combo_mult - 1.0) * t
            m.accuracy_mult = 1.0
            m.telegraph_chance = 0.0
            m.punish_mult = 1.0 + (cfg.sharp_punish_mult - 1.0) * t
            m.variation_boost = cfg.sharp_variation * t
            m.spacing_tightness = 1.0 + (cfg.sharp_spacing_tightness - 1.0) * t

        else:
            # ── Balanced → neutral ────────────────────────
            m.reaction_delay_adj = 0.0
            m.aggression_mult = 1.0
            m.cooldown_mult = 1.0
            m.combo_mult = 1.0
            m.accuracy_mult = 1.0
            m.telegraph_chance = 0.0
            m.punish_mult = 1.0
            m.variation_boost = 0.0
            m.spacing_tightness = 1.0

    # ══════════════════════════════════════════════════════
    #  Reset
    # ══════════════════════════════════════════════════════

    def reset(self):
        """Reset for a new fight. Preserves round history."""
        rounds_p = self._stats.rounds_player_won
        rounds_e = self._stats.rounds_enemy_won
        self._stats = _MatchStats()
        self._stats.rounds_player_won = rounds_p
        self._stats.rounds_enemy_won = rounds_e
        self._smooth_score = 0.0
        self._modifiers = DifficultyModifiers()

    def full_reset(self):
        """Full reset including round history (new session)."""
        self._stats = _MatchStats()
        self._smooth_score = 0.0
        self._modifiers = DifficultyModifiers()
