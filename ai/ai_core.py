"""
ai_core.py – Central AI brain that orchestrates all sub-systems.

This replaces the old AIController with an intent-driven, adaptive
combat brain that never freezes and always feels like a skilled player.

Architecture:
    ai_core.AIBrain
      ├── phase_system.PhaseSystem                   (combat phase FSM)
      ├── adaptive_learning.AdaptiveLearning         (player pattern learning)
      ├── attack_style_system.AttackStyleSystem      (blendable archetypes)
      ├── difficulty_balancer.DifficultyBalancer      (rubber-banding)
      ├── combat_intent_system.CombatIntentSystem    (intent evaluation)
      ├── aggression_system.AggressionSystem         (pressure / tempo)
      ├── build_difficulty_adapter.BuildDifficultyAdapter (build counters)
      ├── desperation_mode.DesperationMode           (low-HP comeback + rage)
      └── DuelistBehavior (from old ai_system)       (personality-specific)

The brain is the ONLY module that touches the enemy entity.
Sub-systems produce modifiers; the brain applies them.

States: chase | attack | retreat | block_wait | strafe | stunned | feint
"""

from __future__ import annotations

import logging
import math
import random

logger = logging.getLogger(__name__)

import pygame

from settings import (
    SCREEN_WIDTH, SCREEN_HEIGHT, ATTACK_RANGE,
    ENEMY_QUICK_DAMAGE, ENEMY_QUICK_RANGE, ENEMY_QUICK_COOLDOWN,
    ENEMY_HEAVY_DAMAGE, ENEMY_HEAVY_RANGE, ENEMY_HEAVY_COOLDOWN,
    ENEMY_RETREAT_DURATION, ENEMY_RETREAT_SPEED,
    STAMINA_ATTACK_COST, STAMINA_HEAVY_ATTACK_COST,
    DODGE_SPEED, DODGE_DURATION,
    PROJECTILE_COOLDOWN, PROJECTILE_DAMAGE, PROJECTILE_SPEED,
    DUELIST_DAMAGE_MULT, DUELIST_QUICK_COOLDOWN, DUELIST_HEAVY_COOLDOWN,
    DUELIST_ATTACK_DURATION, DUELIST_THINK_INTERVAL,
    DUELIST_COUNTER_WINDOW, DUELIST_COUNTER_DAMAGE,
    DUELIST_COMBO_WINDOW, DUELIST_COMBO_DAMAGE,
    DUELIST_LUNGE_IMPULSE, DUELIST_CHASE_SPEED_MULT,
)

from ai.combat_intent_system import CombatIntentSystem, IntentConfig
from ai.aggression_system import AggressionSystem, AggressionConfig
from ai.build_difficulty_adapter import BuildDifficultyAdapter, BuildModifiers
from ai.desperation_mode import DesperationMode, DesperationConfig
from ai.phase_system import PhaseSystem, PhaseConfig, CombatPhase
from ai.adaptive_learning import AdaptiveLearning, LearningConfig
from ai.attack_style_system import AttackStyleSystem, StyleConfig
from ai.difficulty_balancer import DifficultyBalancer, BalancerConfig
from ai.ai_system import (
    Personality, PERSONALITIES, DuelistBehavior,
    select_personality,
)


# ══════════════════════════════════════════════════════════
#  Block Reaction Profiles (per personality)
# ══════════════════════════════════════════════════════════

BLOCK_PROFILES: dict[str, float] = {
    "Duelist":    0.65,   # high block chance
    "Balanced":   0.40,
    "Berserker":  0.15,
    "Trickster":  0.30,   # may dodge instead
    "Coward":     0.50,
    "Mage":       0.35,
    "Tactician":  0.45,   # reads and blocks
    "Aggressor":  0.10,   # rarely blocks, prefers offense
    "Defender":   0.70,   # blocks most attacks
    "Predator":   0.25,   # blocks sparingly, strikes low-HP
    "Adaptive":   0.35,   # shifts dynamically
}


# ══════════════════════════════════════════════════════════
#  AI Brain
# ══════════════════════════════════════════════════════════

class AIBrain:
    """Production-grade enemy AI controller.

    Replaces the old AIController. Wire into Enemy.update().
    """

    VALID_STATES = {"idle", "chase", "attack", "retreat", "block_wait",
                    "strafe", "stunned", "feint"}

    def __init__(self, personality: Personality,
                 build_type: str = "BALANCED"):
        self.personality = personality
        self.is_duelist = personality.name == "Duelist"

        # ── Sub-systems (existing) ────────────────────────
        self.intent = CombatIntentSystem(
            config=IntentConfig(),
            personality_name=personality.name,
        )
        self.aggression = AggressionSystem(config=AggressionConfig())
        self.build_adapter = BuildDifficultyAdapter(build_type)
        self.desperation = DesperationMode(config=DesperationConfig())

        # ── Sub-systems (NEW – Phase / Learn / Style / Balance) ──
        self.phase = PhaseSystem(config=PhaseConfig())
        self.learner = AdaptiveLearning(config=LearningConfig())
        self.styles = AttackStyleSystem(config=StyleConfig())
        self.balancer = DifficultyBalancer(config=BalancerConfig())

        # Duelist reactive module (only for Duelist personality)
        self.duelist: DuelistBehavior | None = None
        if self.is_duelist:
            self.duelist = DuelistBehavior()

        # ── FSM ───────────────────────────────────────────
        self.state: str = "chase"
        self.last_attack_time: int = 0      # ms
        self.current_cooldown: float = 0.6  # seconds
        self._cooldown_timer: float = 0.0   # seconds remaining
        self.last_attack_type: str | None = None

        # ── Pending damage buffer ─────────────────────────
        self._pending_damage: int = 0
        self._pending_attack_type: str = "quick"

        # ── Projectile ────────────────────────────────────
        self._pending_projectile: bool = False
        self._last_projectile_time: float = 0.0

        # ── Retreat ───────────────────────────────────────
        self.retreat_start: int = 0
        self.retreat_duration: int = ENEMY_RETREAT_DURATION
        self.retreat_speed: float = ENEMY_RETREAT_SPEED
        self.retreat_dir: tuple[float, float] = (0.0, 0.0)

        # ── Block ─────────────────────────────────────────
        self._block_timer: float = 0.0
        self._max_block_duration: float = 0.8

        # ── Attack weights ────────────────────────────────
        self.attack_weights: list[int] = [3, 3]
        self._adapt_weights()

        # ── Movement accumulator (sub-pixel) ──────────────
        self._move_rem_x: float = 0.0
        self._move_rem_y: float = 0.0

        # ── Idle watchdog ─────────────────────────────────
        self._idle_frames: int = 0
        self._IDLE_LIMIT: int = 6  # tighter than before

        # ── Decision timer ────────────────────────────────
        self._decision_timer: float = 0.0
        self._base_think: float = (
            DUELIST_THINK_INTERVAL if self.is_duelist else 0.20
        )

        # ── Player observation ────────────────────────────
        self._player_stamina_low: bool = False
        self._player_is_blocking: bool = False
        self._player_aggression: float = 0.0
        self._player_attack_timestamps: list[float] = []

        # ── Feint state ───────────────────────────────────
        self._feint_timer: float = 0.0

        # ── Risk combo state ──────────────────────────────
        self._risk_combo_remaining: int = 0
        self._risk_combo_cooldown: float = 0.12  # between hits

        # ── Cinematic event flags (consumed by main.py) ───
        self.event_phase_transition: bool = False
        self.event_rage_entered: bool = False
        self.event_perfect_counter: bool = False

        # ── Debug throttle ────────────────────────────────
        self._dbg_timer: float = 0.0

    # ══════════════════════════════════════════════════════
    #  Main Update
    # ══════════════════════════════════════════════════════

    def update(self, enemy, player, dt: float):
        """One frame of AI logic. Guarantees the enemy ALWAYS acts."""
        if not enemy.alive or enemy.anim_state == "death":
            return

        if enemy.is_stunned:
            self.state = "stunned"
            return

        if self.state == "stunned":
            self.state = "chase"

        now_ms = pygame.time.get_ticks()
        now_sec = now_ms / 1000.0
        dist = self._dist(enemy, player)

        # ── Clear one-frame event flags ───────────────────
        self.event_phase_transition = False
        self.event_rage_entered = False
        self.event_perfect_counter = False

        # ── Observe player ────────────────────────────────
        self._observe_player(player, now_sec)

        # ── Enemy HP fraction ─────────────────────────────
        ehp_frac = enemy.hp / max(1, enemy.max_hp)
        estam_frac = 1.0
        if hasattr(enemy, 'stamina_component'):
            estam_frac = enemy.stamina_component.fraction

        # ══════════════════════════════════════════════════
        #  Update ALL sub-systems
        # ══════════════════════════════════════════════════

        # 1. Adaptive learning — observe player patterns
        self.learner.observe(dt, now_sec, player, enemy, dist)

        # 2. Phase system — strategic arc
        flow_ratio = self.aggression.flow.flow_ratio(now_sec)
        self.phase.update(dt, ehp_frac, self.learner.confidence, flow_ratio)
        phase_mods = self.phase.modifiers

        # Detect phase transition events for cinematic triggers
        if phase_mods.just_transitioned:
            self.event_phase_transition = True
            if phase_mods.phase == CombatPhase.RAGE:
                self.event_rage_entered = True

        # 3. Attack style system — blendable archetypes
        self.styles.update(dt, player_profile=self.learner.profile)
        style_mods = self.styles.modifiers

        # 4. Difficulty balancer — rubber-banding
        self.balancer.update(dt)
        diff_mods = self.balancer.modifiers

        # 5. Intent system (feeds from phase + style + difficulty)
        self.intent.update(
            dt, now_sec, dist, estam_frac,
            self._player_aggression,
            self.aggression.tempo_mode,
            ehp_frac,
        )

        # 6. Aggression system
        self.aggression.update(
            dt, now_sec, ehp_frac,
            self.intent.attack_intent,
            self.intent.aggression_level,
            player.is_attacking, dist, ATTACK_RANGE,
        )

        # 7. Desperation + Rage
        self.desperation.update(dt, ehp_frac)

        # 8. Build adapter
        build_mods = self.build_adapter.get_modifiers(
            ehp_frac, getattr(player, 'is_blocking', False),
        )
        desp_mods = self.desperation.modifiers

        # ── Cooldown tick (affected by phase + style + difficulty + desperation) ──
        if self._cooldown_timer > 0:
            cd_speed = 1.0
            # Phase modifier
            cd_speed /= max(0.3, phase_mods.cooldown_mult)
            # Style modifier
            cd_speed /= max(0.3, style_mods.cooldown_mult)
            # Difficulty modifier
            cd_speed /= max(0.3, diff_mods.cooldown_mult)
            # Desperation
            if desp_mods.active:
                cd_speed /= max(0.3, desp_mods.cooldown_mult)
            self._cooldown_timer -= dt * cd_speed
            if self._cooldown_timer < 0:
                self._cooldown_timer = 0

        # ── Feint timer tick ──────────────────────────────
        if self.state == "feint":
            self._feint_timer -= dt
            if self._feint_timer <= 0:
                # Feint ended → real attack
                self.state = "attack"
                self._decision_timer = 0

        # ── Risk combo chain ──────────────────────────────
        if self._risk_combo_remaining > 0 and self._cooldown_timer <= 0:
            if enemy.can_act and dist <= ENEMY_HEAVY_RANGE:
                self.state = "attack"
                self._decision_timer = 0

        # ── Debug log ─────────────────────────────────────
        self._dbg_timer -= dt
        if self._dbg_timer <= 0:
            logger.debug(
                "state=%s phase=%s dist=%.0f intent=%.2f "
                "tempo=%s style=%s conf=%.2f bal=%+.2f "
                "desp=%s rage=%s cd=%.2f hp=%.2f",
                self.state, phase_mods.phase.name, dist,
                self.intent.attack_intent, self.aggression.tempo_mode,
                self.styles.dominant_archetype, self.learner.confidence,
                diff_mods.balance_score, desp_mods.active,
                desp_mods.rage_active, self._cooldown_timer, ehp_frac,
            )
            self._dbg_timer = 1.0

        # ── Duelist reactive (counter / combo / punish) ───
        if self.duelist is not None:
            self.duelist.update(dt, enemy, player, dist)
            if self._try_duelist_reactive(enemy, player, now_ms):
                return

        # ── Punish window (all personalities) ─────────────
        if self.aggression.punish.punish_ready and enemy.can_act:
            if self._cooldown_timer <= 0 and dist <= ENEMY_HEAVY_RANGE:
                self.state = "attack"
                self._decision_timer = 0

        # ── Decision gate ─────────────────────────────────
        # Apply reaction delay from difficulty balancer + counter advice
        effective_think = self._base_think
        effective_think += diff_mods.reaction_delay_adj
        effective_think += self.learner.advice.reaction_delay_adj
        effective_think = max(0.05, effective_think)

        self._decision_timer -= dt
        if self._decision_timer > 0:
            self._tick_state(enemy, player, dist, now_ms, dt, build_mods,
                             desp_mods, phase_mods, style_mods, diff_mods)
            return

        # ── State decision ────────────────────────────────
        self._decide_state(enemy, player, dist, now_ms, build_mods,
                           desp_mods, phase_mods, style_mods, diff_mods,
                           effective_think)
        self._tick_state(enemy, player, dist, now_ms, dt, build_mods,
                         desp_mods, phase_mods, style_mods, diff_mods)

        # ── Idle watchdog (NEVER FREEZE) ──────────────────
        if self.state in ("attack", "block_wait", "idle", "feint"):
            self._idle_frames += 1
        else:
            self._idle_frames = 0

        if self._idle_frames >= self._IDLE_LIMIT:
            if enemy.is_blocking:
                enemy.stop_block()
            self.state = "chase"
            self._idle_frames = 0
            self._move_toward(enemy, player, dt, build_mods, desp_mods,
                              phase_mods, style_mods)

    # ══════════════════════════════════════════════════════
    #  State Decision
    # ══════════════════════════════════════════════════════

    def _decide_state(self, enemy, player, dist: float, now: int,
                      bm: BuildModifiers, dm, pm, sm, dfm, think_time: float):
        """Intent-driven state selection with phase/style/difficulty awareness.

        Args:
            bm: BuildModifiers, dm: DesperationModifiers,
            pm: PhaseModifiers, sm: StyleModifiers, dfm: DifficultyModifiers,
            think_time: effective decision interval after all modifiers.
        """
        p = self.personality
        advice = self.learner.advice

        # ── Stay in retreat if active ─────────────────────
        if self.state == "retreat":
            if now - self.retreat_start < self.retreat_duration:
                return

        # ── Stay in feint if active ───────────────────────
        if self.state == "feint":
            return  # handled by feint timer in update()

        # ── Can't act? → chase ────────────────────────────
        if not enemy.can_act:
            if enemy.is_dodging:
                return
            self.state = "chase"
            return

        # ── Block / dodge reaction (modulated by all systems) ──
        if player.is_attacking and dist < ATTACK_RANGE * 1.4:
            block_base = BLOCK_PROFILES.get(p.name, 0.40)
            block_chance = block_base + bm.block_probability_add
            block_chance += pm.block_bonus                    # phase modifier
            block_chance += sm.block_readiness * 0.3          # style blend
            block_chance += advice.block_readiness * 0.2      # counter-advice

            # Desperation reduces blocking
            if dm.active:
                block_chance -= dm.defense_reduction
            # Rage override: never block
            if dm.rage_active and dm.rage_block_override >= 0:
                block_chance = dm.rage_block_override

            # Difficulty telegraph → slightly slower reaction
            if dfm.telegraph_chance > 0 and random.random() < dfm.telegraph_chance:
                # AI "telegraphs" — delayed block, giving player a window
                self._decision_timer = think_time + 0.10
                return

            # Dodge consideration (style + advice)
            dodge_chance = (p.dodge_probability + bm.dodge_probability_add
                           + sm.dodge_readiness * 0.3
                           + advice.dodge_readiness * 0.2)
            if p.name == "Trickster" or sm.dodge_readiness > 0.3:
                if random.random() < dodge_chance:
                    self._try_dodge(enemy, player)
                    self._decision_timer = think_time
                    return

            if random.random() < max(0.0, block_chance):
                if not enemy.is_blocking:
                    enemy.start_block()
                    self._block_timer = 0.0
                self.state = "block_wait"
                self._decision_timer = think_time + 0.08
                return

        # ── Release block ─────────────────────────────────
        if enemy.is_blocking and not player.is_attacking:
            enemy.stop_block()
            if self.duelist is not None:
                self.duelist.on_block_success()

        # ── Attack decision (intent + phase + style + difficulty) ──
        effective_spacing = (ENEMY_HEAVY_RANGE + bm.spacing_offset
                             + sm.spacing_offset
                             + (advice.preferred_engage_dist - 70.0) * 0.3)
        in_range = dist <= effective_spacing
        cooldown_ready = self._cooldown_timer <= 0
        not_swinging = enemy.anim_state != "attack"

        # Intent threshold modulated by phase aggression + difficulty
        intent_threshold = 0.35
        intent_threshold /= max(0.5, pm.aggression_mult)
        intent_threshold /= max(0.5, dfm.aggression_mult)
        intent_threshold /= max(0.5, sm.aggression_mult * 0.5 + 0.5)
        intent_high = self.intent.attack_intent > intent_threshold

        # Spam counter: if player spamming, bias toward counter-attacks
        if self.aggression.punish.player_is_spamming:
            intent_high = True  # always want to swing back

        if in_range and cooldown_ready and not_swinging and intent_high:
            # Stamina check (modulated by rage stamina ignore)
            stam_cost = STAMINA_ATTACK_COST
            stam_ok = True
            if hasattr(enemy, 'stamina_component'):
                min_frac = 0.5  # normal: 50% of cost
                if dm.rage_active:
                    min_frac = max(0.1, min_frac - dm.rage_stamina_ignore)
                if pm.stamina_ignore_frac > 0:
                    min_frac = max(0.1, min_frac - pm.stamina_ignore_frac)
                min_stam = stam_cost * min_frac
                stam_ok = enemy.stamina_component.stamina >= min_stam

            if stam_ok:
                # ── Feint check (desperation + phase + style) ──
                feint_chance = (dm.feint_chance if dm.active else 0.0)
                feint_chance = max(feint_chance, pm.feint_chance)
                feint_chance = max(feint_chance, sm.feint_chance)
                feint_chance += advice.feint_rate * 0.5

                if feint_chance > 0 and random.random() < feint_chance:
                    # Enter feint state — fake attack then real attack
                    self.state = "feint"
                    self._feint_timer = self.desperation.cfg.feint_cancel_window
                    enemy.start_attack()  # start animation
                    self._decision_timer = think_time
                    self.styles.record_action("feint")
                else:
                    # Anti-repetition: vary attack type if repeating
                    self.state = "attack"
            else:
                # Low stamina → retreat (unless rage overrides)
                if dm.rage_active:
                    self.state = "attack"  # rage: attack anyway
                else:
                    self._begin_retreat(enemy, player, now)
        elif in_range and not cooldown_ready:
            # In range but cooldown active → STRAFE (never idle)
            self.state = "strafe"
        elif not in_range:
            self.state = "chase"
        else:
            self.state = "chase"

        self._decision_timer = think_time

    # ══════════════════════════════════════════════════════
    #  State Execution
    # ══════════════════════════════════════════════════════

    def _tick_state(self, enemy, player, dist: float, now: int,
                    dt: float, bm: BuildModifiers, dm, pm=None, sm=None, dfm=None):
        """Execute current state behavior. Every path moves or acts."""
        acted = False

        if self.state == "chase":
            self._move_toward(enemy, player, dt, bm, dm, pm, sm)
            acted = True

        elif self.state == "strafe":
            # Micro-movement: never stand still in range
            self._do_strafe(enemy, player, dt, bm, sm)
            acted = True

        elif self.state == "retreat":
            self._move_retreat(enemy, now)
            acted = True

        elif self.state == "block_wait":
            self._block_timer += dt
            if not player.is_attacking:
                enemy.stop_block()
                if self.duelist is not None:
                    self.duelist.on_block_success()
                self.state = "chase"
                acted = True
            elif self._block_timer >= self._max_block_duration:
                enemy.stop_block()
                self.state = "chase"
                acted = True
            else:
                acted = True  # blocking counts as action

        elif self.state == "feint":
            # Feint state: enemy is fake-attacking (animation plays)
            # Movement continues (erratic) to sell the feint
            if sm and sm.movement_erratic > 0.2:
                self._do_strafe(enemy, player, dt, bm, sm)
            acted = True

        elif self.state == "attack":
            if enemy.anim_state == "attack":
                # Already swinging → chase to stay in range
                self._move_toward(enemy, player, dt, bm, dm, pm, sm)
                acted = True
            else:
                dmg = self._execute_attack(enemy, player, now, bm, dm,
                                            pm, sm, dfm)
                if dmg > 0:
                    self._pending_damage = dmg
                    self._pending_attack_type = self.last_attack_type or "quick"
                    if self.is_duelist:
                        lunge_dir = 1 if player.rect.centerx > enemy.rect.centerx else -1
                        enemy.apply_knockback(lunge_dir * DUELIST_LUNGE_IMPULSE)
                    # Risk combo check
                    if (self._risk_combo_remaining <= 0
                            and dm.active and self.desperation.should_risk_combo()):
                        self._risk_combo_remaining = dm.risk_combo_hits - 1
                    acted = True
                else:
                    self.state = "chase"
                    self._move_toward(enemy, player, dt, bm, dm, pm, sm)
                    acted = True

        elif self.state == "idle":
            self.state = "chase"
            self._move_toward(enemy, player, dt, bm, dm, pm, sm)
            acted = True

        # ── Fallback: NEVER do nothing ────────────────────
        if not acted:
            self.state = "chase"
            self._move_toward(enemy, player, dt, bm, dm, pm, sm)

        # Mage projectile
        if self.personality.uses_projectiles and dist > ATTACK_RANGE * 1.5:
            self._try_projectile(enemy, player, now)

        # Face player
        enemy.face_toward(player.rect.centerx)

    # ══════════════════════════════════════════════════════
    #  Attack Execution
    # ══════════════════════════════════════════════════════

    def _execute_attack(self, enemy, player, now: int,
                        bm: BuildModifiers, dm,
                        pm=None, sm=None, dfm=None) -> int:
        """Commit an attack. Returns damage (0 on failure).

        Now incorporates phase, style, difficulty, and counter-advice modifiers.
        """
        if not enemy.can_act or enemy.anim_state == "attack":
            return 0
        if self._cooldown_timer > 0:
            return 0

        advice = self.learner.advice

        # Pick attack type
        weights = list(self.attack_weights)

        # Style heavy bias
        if sm and sm.heavy_attack_bias > 0.15:
            weights = [max(1, weights[0] - 1), weights[1] + 2]
        elif sm and sm.heavy_attack_bias < -0.10:
            weights = [weights[0] + 2, max(1, weights[1] - 1)]

        # Counter-advice heavy bias
        if advice.heavy_bias > 0.15:
            weights = [max(1, weights[0] - 1), weights[1] + 2]
        elif advice.heavy_bias < -0.15:
            weights = [weights[0] + 2, max(1, weights[1] - 1)]

        # If player blocking + guard-break build mod → favor heavy
        if self._player_is_blocking and bm.guard_break_chance > 0:
            if random.random() < bm.guard_break_chance:
                weights = [1, 6]  # heavy bias

        # Anti-repetition via style system
        proposed = "heavy" if weights[1] > weights[0] else "quick"
        if self.styles.should_vary_action(proposed):
            weights = list(reversed(weights))  # swap preference

        attack = random.choices(["quick", "heavy"], weights=weights, k=1)[0]
        self.styles.record_action(attack)

        if attack == "quick":
            damage = ENEMY_QUICK_DAMAGE
            reach = ENEMY_QUICK_RANGE
            base_cd = DUELIST_QUICK_COOLDOWN / 1000.0 if self.is_duelist else ENEMY_QUICK_COOLDOWN / 1000.0
            stam_cost = STAMINA_ATTACK_COST
        else:
            damage = ENEMY_HEAVY_DAMAGE
            reach = ENEMY_HEAVY_RANGE
            base_cd = DUELIST_HEAVY_COOLDOWN / 1000.0 if self.is_duelist else ENEMY_HEAVY_COOLDOWN / 1000.0
            stam_cost = STAMINA_HEAVY_ATTACK_COST

        # Duelist damage bonus
        if self.is_duelist:
            damage = int(damage * DUELIST_DAMAGE_MULT)

        # Stamina check (lenient – rage can ignore more)
        if hasattr(enemy, 'stamina_component'):
            available = enemy.stamina_component.stamina
            min_frac = 0.5
            if dm.rage_active:
                min_frac = max(0.1, min_frac - dm.rage_stamina_ignore)
            min_needed = stam_cost * min_frac
            if available < min_needed:
                return 0
            drain_amount = min(stam_cost, available)
            enemy.stamina_component.drain(drain_amount)

        # Cooldown from aggression system (dynamic)
        dynamic_cd = self.aggression.get_dynamic_cooldown()

        # Apply build modifier
        dynamic_cd *= bm.attack_cooldown_mult

        # Apply phase modifier
        if pm:
            dynamic_cd *= pm.cooldown_mult

        # Apply style modifier
        if sm:
            dynamic_cd *= sm.cooldown_mult

        # Apply difficulty modifier
        if dfm:
            dynamic_cd *= dfm.cooldown_mult

        # Apply desperation modifier
        if dm.active:
            dynamic_cd *= dm.cooldown_mult

        # Apply personality speed
        dynamic_cd /= max(0.5, self.personality.attack_frequency)

        # Combo chance (phase + style + difficulty + desperation)
        combo_chance = self.aggression.get_combo_chance()
        if pm:
            combo_chance *= pm.combo_mult
        if sm:
            combo_chance *= sm.combo_complexity
        if dfm:
            combo_chance *= dfm.combo_mult
        if dm.active:
            combo_chance += dm.combo_chance_boost

        # Risk combo: halve cooldown even more
        if self._risk_combo_remaining > 0:
            dynamic_cd *= 0.3
            self._risk_combo_remaining -= 1
        elif random.random() < min(0.9, combo_chance):
            dynamic_cd *= 0.5

        self._cooldown_timer = max(0.15, dynamic_cd)
        self.last_attack_type = attack
        self.last_attack_time = now
        enemy.start_attack()

        if self.is_duelist:
            enemy.attack_duration = DUELIST_ATTACK_DURATION

        # Apply buff modifiers
        if hasattr(enemy, 'buff_manager'):
            self._cooldown_timer = enemy.buff_manager.modify_attack_cooldown(
                self._cooldown_timer
            )

        # Post-attack: retreat or chase (modified by style + phase + rage)
        retreat_chance = self.personality.retreat_tendency
        if sm:
            retreat_chance = retreat_chance * 0.5 + sm.retreat_tendency * 0.5
        if dm.active:
            retreat_chance = max(0.0, retreat_chance - dm.defense_reduction)
        if dm.rage_active and dm.rage_retreat_override >= 0:
            retreat_chance = dm.rage_retreat_override
        if attack == "heavy":
            retreat_chance = min(1.0, retreat_chance + 0.2)
        if random.random() < retreat_chance:
            self._begin_retreat(enemy, player, now)
        else:
            self.state = "chase"

        # Range check (modulated by difficulty accuracy)
        dist = self._dist(enemy, player)
        effective_reach = reach
        if dfm and dfm.accuracy_mult < 1.0:
            effective_reach *= dfm.accuracy_mult  # worse accuracy = shorter effective reach
        if dist > effective_reach:
            self.balancer.record_enemy_miss()
            return 0

        # Buff damage modifiers
        if hasattr(enemy, 'buff_manager'):
            damage = int(enemy.buff_manager.modify_damage_dealt(damage))

        return damage

    # ══════════════════════════════════════════════════════
    #  Duelist Reactive
    # ══════════════════════════════════════════════════════

    def _try_duelist_reactive(self, enemy, player, now: int) -> bool:
        """Handle Duelist counter / combo / punish. Returns True if acted."""
        if self.duelist is None:
            return False

        # Counter-strike after block
        counter_dmg = self.duelist.consume_counter()
        if counter_dmg > 0 and enemy.can_act and enemy.anim_state != "attack":
            counter_dmg = int(counter_dmg * DUELIST_DAMAGE_MULT)
            self._pending_damage = counter_dmg
            self._pending_attack_type = "counter"
            enemy.start_attack()
            lunge = 1 if player.rect.centerx > enemy.rect.centerx else -1
            enemy.apply_knockback(lunge * DUELIST_LUNGE_IMPULSE * 0.6)
            self._decision_timer = self._base_think
            self._idle_frames = 0
            return True

        # Combo follow-up
        combo_dmg = self.duelist.consume_combo()
        if combo_dmg > 0 and enemy.can_act and enemy.anim_state != "attack":
            combo_dmg = int(combo_dmg * DUELIST_DAMAGE_MULT)
            self._pending_damage = combo_dmg
            self._pending_attack_type = "combo"
            enemy.start_attack()
            lunge = 1 if player.rect.centerx > enemy.rect.centerx else -1
            enemy.apply_knockback(lunge * DUELIST_LUNGE_IMPULSE * 0.4)
            self._decision_timer = self._base_think
            self._idle_frames = 0
            return True

        # Reactive punish on whiff
        if self.duelist.wants_punish and enemy.can_act:
            if self._cooldown_timer <= 0:
                self.state = "attack"
                self._decision_timer = 0
                return False  # let normal attack flow handle it

        return False

    # ══════════════════════════════════════════════════════
    #  Movement
    # ══════════════════════════════════════════════════════

    def _move_toward(self, enemy, player, dt: float,
                     bm: BuildModifiers, dm, pm=None, sm=None):
        """Chase with intent-driven speed, modulated by all systems."""
        dx = player.rect.centerx - enemy.rect.centerx
        dy = player.rect.centery - enemy.rect.centery
        dist = math.hypot(dx, dy)
        if dist < 1:
            return

        speed = enemy.speed
        # Personality aggression
        speed *= (0.8 + 0.6 * self.personality.aggression)
        # Aggression system tempo
        speed *= self.aggression.get_chase_speed_mult()
        # Build modifier
        speed *= bm.chase_speed_mult
        # Phase modifier
        if pm:
            speed *= pm.chase_mult
        # Style modifier
        if sm:
            speed *= sm.chase_speed_mult
        # Counter-advice approach speed
        speed *= self.learner.advice.approach_speed_mult
        # Desperation mode
        if dm.active:
            speed *= dm.chase_speed_mult
        # Duelist faster chase
        if self.is_duelist:
            speed *= DUELIST_CHASE_SPEED_MULT
        # Buff speed
        if hasattr(enemy, 'buff_manager'):
            speed = enemy.buff_manager.modify_speed(speed)
        # Floor
        speed = max(speed, 1.5)

        # Rush when player stamina low
        if self._player_stamina_low:
            speed *= 1.3

        # Erratic movement (from style system)
        erratic = 0.0
        if sm:
            erratic = sm.movement_erratic

        # Sub-pixel accumulation
        raw_mx = (dx / dist) * speed + self._move_rem_x
        raw_my = (dy / dist) * speed + self._move_rem_y

        # Add erratic perpendicular noise
        if erratic > 0.1:
            perp_x = -dy / dist
            perp_y = dx / dist
            noise = (random.random() - 0.5) * 2.0 * erratic * speed * 0.3
            raw_mx += perp_x * noise
            raw_my += perp_y * noise

        int_mx = math.trunc(raw_mx)
        int_my = math.trunc(raw_my)
        self._move_rem_x = raw_mx - int_mx
        self._move_rem_y = raw_my - int_my

        enemy.rect.x += int_mx
        enemy.rect.y += int_my

    def _do_strafe(self, enemy, player, dt: float, bm: BuildModifiers,
                   sm=None):
        """Strafe / micro-move when in range but on cooldown."""
        strafe_dir = self.aggression.get_strafe_direction()
        if strafe_dir == 0:
            strafe_dir = 1 if random.random() > 0.5 else -1

        speed = self.aggression.cfg.strafe_speed
        # Style strafe speed boost
        if sm:
            speed *= sm.strafe_speed_mult
        # Perpendicular to player direction
        dx = player.rect.centerx - enemy.rect.centerx
        dy = player.rect.centery - enemy.rect.centery
        dist = math.hypot(dx, dy)
        if dist < 1:
            return

        # Perpendicular vector
        perp_x = -dy / dist * strafe_dir
        perp_y = dx / dist * strafe_dir

        # Also close distance slightly if too far
        approach = 0.0
        if dist > ENEMY_QUICK_RANGE:
            approach = 0.5

        move_x = perp_x * speed + (dx / dist) * approach * speed
        move_y = perp_y * speed + (dy / dist) * approach * speed

        enemy.rect.x += int(move_x)
        enemy.rect.y += int(move_y)

    def _begin_retreat(self, enemy, player, now: int):
        dx = enemy.rect.centerx - player.rect.centerx
        dy = enemy.rect.centery - player.rect.centery
        dist = math.hypot(dx, dy)
        if dist < 1:
            dx, dy, dist = 1, 0, 1
        self.retreat_dir = (dx / dist, dy / dist)
        self.retreat_start = now
        self.retreat_duration = ENEMY_RETREAT_DURATION
        self.state = "retreat"

    def _move_retreat(self, enemy, now: int):
        elapsed = now - self.retreat_start
        if elapsed >= self.retreat_duration:
            self.state = "chase"
            return
        enemy.rect.x += int(self.retreat_dir[0] * self.retreat_speed)
        enemy.rect.y += int(self.retreat_dir[1] * self.retreat_speed)

    def _try_dodge(self, enemy, player):
        from settings import STAMINA_DODGE_COST
        if hasattr(enemy, 'stamina_component'):
            if not enemy.stamina_component.has_enough(STAMINA_DODGE_COST):
                return
            enemy.stamina_component.drain(STAMINA_DODGE_COST)
        direction = -1 if player.rect.centerx > enemy.rect.centerx else 1
        enemy.start_dodge(direction)

    def _try_projectile(self, enemy, player, now: int):
        elapsed_sec = (now - self._last_projectile_time) / 1000.0
        if elapsed_sec < PROJECTILE_COOLDOWN:
            return
        if not enemy.can_act:
            return
        self._pending_projectile = True
        self._last_projectile_time = now

    # ══════════════════════════════════════════════════════
    #  Observation
    # ══════════════════════════════════════════════════════

    def _observe_player(self, player, now_sec: float):
        self._player_stamina_low = (
            hasattr(player, 'stamina_component')
            and player.stamina_component.is_low
        )
        self._player_is_blocking = player.is_blocking

        # Track player attack frequency for aggression estimation
        if player.is_attacking:
            self._player_attack_timestamps.append(now_sec)
        # Prune old
        self._player_attack_timestamps = [
            t for t in self._player_attack_timestamps if now_sec - t < 3.0
        ]
        # Player aggression estimate: attacks per second / max expected
        atk_count = len(self._player_attack_timestamps)
        self._player_aggression = min(1.0, atk_count / 6.0)

        # Adapt weights
        if self._player_is_blocking:
            self.attack_weights = [2, 5]  # heavy to break guard
        else:
            self._adapt_weights()

    def _adapt_weights(self):
        p = self.personality
        if p.aggression > 0.8:
            self.attack_weights = [2, 5]
        elif p.aggression < 0.3:
            self.attack_weights = [5, 1]
        else:
            self.attack_weights = [3, 3]

    # ══════════════════════════════════════════════════════
    #  Public API (consumed by CombatSystem / main.py)
    # ══════════════════════════════════════════════════════

    def get_pending_damage(self, enemy, player) -> int:
        dmg = self._pending_damage
        self._pending_damage = 0
        if dmg > 0:
            self.last_attack_type = self._pending_attack_type
        return dmg

    def notify_hit_landed(self):
        """Enemy hit confirmed → queue combo, notify balancer."""
        if self.duelist is not None:
            self.duelist.on_hit_landed()
        # Aggression system: queue combo follow-up
        self.aggression.queue_combo_followup()
        # Notify learner: player was hit → track "after hit" defence
        self.learner.notify_player_hit()

    def notify_damage_dealt(self, now_sec: float, amount: int):
        """Enemy dealt damage to player."""
        self.intent.record_damage_dealt(now_sec, amount)
        self.aggression.flow.record_enemy_damage(now_sec, amount)
        self.balancer.record_enemy_hit(amount)

    def notify_damage_taken(self, now_sec: float, amount: int):
        """Enemy took damage from player."""
        self.intent.record_damage_taken(now_sec, amount)
        self.aggression.flow.record_player_damage(now_sec, amount)
        self.balancer.record_player_hit(amount)

    def notify_player_blocked(self):
        """Player successfully blocked an enemy attack."""
        self.balancer.record_player_block()

    def notify_player_dodged(self):
        """Player successfully dodged."""
        self.balancer.record_player_dodge()

    def notify_player_missed(self):
        """Player attack missed / was blocked by enemy."""
        self.balancer.record_player_miss()

    def get_pending_projectile(self) -> bool:
        if self._pending_projectile:
            self._pending_projectile = False
            return True
        return False

    def reset(self):
        self.state = "chase"
        self._cooldown_timer = 0.0
        self._pending_damage = 0
        self._idle_frames = 0
        self._feint_timer = 0.0
        self._risk_combo_remaining = 0
        self.event_phase_transition = False
        self.event_rage_entered = False
        self.event_perfect_counter = False
        # Reset all sub-systems
        self.intent.reset()
        self.aggression.reset()
        self.desperation.reset()
        self.phase.reset()
        self.learner.reset()
        self.styles.reset()
        self.balancer.reset()
        if self.duelist:
            self.duelist.reset()

    # ── Helpers ───────────────────────────────────────────

    @staticmethod
    def _dist(a, b) -> float:
        return math.hypot(
            a.rect.centerx - b.rect.centerx,
            a.rect.centery - b.rect.centery,
        )
