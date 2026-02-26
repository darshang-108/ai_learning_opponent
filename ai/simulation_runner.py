"""
simulation_runner.py – Automated AI-vs-AI rendered simulation.

Runs N matches where a second AIBrain controls the player entity.
All matches are rendered on screen but require no keyboard input.

Usage (from CLI):
    python main.py --simulate 50

Architecture:
    SimulationRunner wraps a Game instance, replacing the normal
    event/update loop with an automated version where both sides
    are AI-driven.  No gameplay logic is duplicated; the existing
    CombatSystem, ProjectileSystem, etc. are reused as-is.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field

import pygame

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════
#  Per-match result
# ══════════════════════════════════════════════════════════

@dataclass
class MatchResult:
    """Lightweight record for one simulated match."""
    match_number: int = 0
    winner: str = ""               # "player" or "enemy"
    player_personality: str = ""   # AIBrain personality driving the player
    enemy_personality: str = ""    # AIBrain personality driving the enemy
    player_role: str = ""          # role assigned to the player this match
    enemy_role: str = ""           # role assigned to the enemy this match
    duration_sec: float = 0.0
    avg_aggression: float = 0.0
    phase_transitions: int = 0


# ══════════════════════════════════════════════════════════
#  Simulation Runner
# ══════════════════════════════════════════════════════════

class SimulationRunner:
    """Run *n_matches* fully-rendered AI-vs-AI matches.

    Parameters
    ----------
    game : Game
        A fully-constructed ``Game`` instance (from main.py).
    n_matches : int
        How many matches to run.
    """

    def __init__(self, game, n_matches: int = 10) -> None:
        self._game = game
        self._n_matches = max(1, n_matches)
        self._results: list[MatchResult] = []

        # Player-side AI brain (created fresh each match in _setup_match)
        self._player_brain = None

        # Per-match trackers
        self._match_timer: float = 0.0
        self._aggression_sum: float = 0.0
        self._aggression_samples: int = 0
        self._phase_transition_count: int = 0
        self._last_phase: str = ""

    # ── Public entry point ────────────────────────────────

    def run(self) -> list[MatchResult]:
        """Execute all N matches, then print and return results."""
        for i in range(1, self._n_matches + 1):
            if not self._game.running:
                logger.info("Window closed — stopping simulation early.")
                break
            logger.info("=== Simulation match %d / %d ===", i, self._n_matches)
            result = self._run_one_match(i)
            self._results.append(result)
            logger.info(
                "Match %d: winner=%s  p_role=%s  e_role=%s  dur=%.1fs  aggro=%.2f  phases=%d",
                i, result.winner, result.player_role, result.enemy_role,
                result.duration_sec, result.avg_aggression, result.phase_transitions,
            )
        self._print_summary()
        return self._results

    # ── Single match ──────────────────────────────────────

    def _run_one_match(self, match_number: int) -> MatchResult:
        game = self._game

        # Pick random roles for both sides
        from systems.character_select import PLAYER_ROLES, role_to_build_type
        role_names = list(PLAYER_ROLES.keys())
        p_role_name = random.choice(role_names)
        e_role_name = random.choice(role_names)

        # Apply player role via game's _selected_role mechanism
        game._selected_role = {**PLAYER_ROLES[p_role_name], "name": p_role_name}
        self._setup_match()

        # Apply enemy role stats post-init (mimic player _apply_role scaling)
        e_role_cfg = PLAYER_ROLES[e_role_name]
        if game.enemy is not None:
            game.enemy.speed = game.enemy.speed * (e_role_cfg["speed"] / 5.0)
            game.enemy.base_speed = game.enemy.speed

        # Grab references
        player = game.player
        enemy = game.enemy
        assert player is not None and enemy is not None

        # Create an AIBrain to drive the player side
        from ai.ai_system import select_personality
        from ai.ai_core import AIBrain
        player_personality = select_personality("Unknown")
        p_build = role_to_build_type(p_role_name)
        self._player_brain = AIBrain(player_personality, build_type=p_build)
        player_pers_name = player_personality.name

        # Also update enemy AI build type to match its assigned role
        e_build = role_to_build_type(e_role_name)
        if hasattr(enemy, 'ai_controller') and hasattr(enemy.ai_controller, 'balancer'):
            enemy.ai_controller.balancer.build_type = e_build.upper()

        # Reset per-match trackers
        self._match_timer = 0.0
        self._aggression_sum = 0.0
        self._aggression_samples = 0
        self._phase_transition_count = 0
        self._last_phase = ""
        match_start = time.monotonic()

        # Run frames until a winner is decided (or safety timeout)
        from settings import FPS
        max_seconds = 120.0  # hard cap per match
        while game.running:
            game.clock.tick(FPS)
            raw_dt = game.clock.get_time() / 1000.0
            raw_dt = min(raw_dt, 0.05)  # clamp spikes

            # Drain pygame events (keep window responsive, ignore input)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    game.running = False
                    return self._build_result(match_number, "aborted",
                                              player_pers_name, match_start,
                                              p_role_name, e_role_name)

            # AI-driven player actions
            self._ai_drive_player(raw_dt)

            # Normal game update (enemy AI, combat, projectiles, VFX…)
            game._update()

            # Render
            game._draw()

            # Track metrics
            self._match_timer += raw_dt
            self._sample_metrics()

            # Check for match end
            if game.game_over:
                winner = "player" if (enemy and not enemy.alive) else "enemy"
                return self._build_result(match_number, winner,
                                          player_pers_name, match_start,
                                          p_role_name, e_role_name)

            if self._match_timer > max_seconds:
                logger.warning("Match %d timed out after %.0fs", match_number, max_seconds)
                return self._build_result(match_number, "timeout",
                                          player_pers_name, match_start,
                                          p_role_name, e_role_name)

        # Window closed mid-sim
        return self._build_result(match_number, "aborted",
                                  player_pers_name, match_start,
                                  p_role_name, e_role_name)

    # ── Setup / teardown ──────────────────────────────────

    def _setup_match(self) -> None:
        """Reset game state for a new match."""
        game = self._game
        game.game_over = False
        game.game_state = "PLAYING"
        game.simulation_mode = True
        game._show_mode_select = False
        game._show_menu = False
        game._show_char_select = False
        game.combat.reset()
        game._init_solo()

        # Reset VFX / cinematic systems
        from utils.vfx import (
            ScreenShake, FloatingTextManager, EffectsManager,
            TimeScaleManager, HitStop, CameraZoom, ImpactFlash,
            ComboCounter, FinalHitCinematic,
        )
        from systems.vfx_system import VFXSystem
        from systems.healthbar import _clear_cache as clear_healthbar_cache

        game.screen_shake = ScreenShake()
        game.floating_texts = FloatingTextManager()
        game.effects = EffectsManager()
        game.vfx = VFXSystem()
        game.projectiles.clear()
        clear_healthbar_cache()
        game._regen_ring_cd = 0.0
        game._player_block_was_pressed = False
        game.time_scale = TimeScaleManager()
        game.hit_stop = HitStop()
        game.camera_zoom = CameraZoom()
        game.impact_flash = ImpactFlash()
        game.combo = ComboCounter()
        game.final_hit = FinalHitCinematic()
        game.audio.reset()

    # ── AI-driven player ──────────────────────────────────

    def _ai_drive_player(self, dt: float) -> None:
        """Use an AIBrain to control the player entity each frame.

        The brain treats the player entity as 'self' and the enemy as
        the opponent — the same interface Enemy.update() uses.
        """
        game = self._game
        player = game.player
        enemy = game.enemy
        if player is None or enemy is None or self._player_brain is None:
            return
        if not player.alive or game.game_over:
            return

        brain = self._player_brain

        # Run the AI brain update (drives FSM state, movement, attack decisions)
        brain.update(player, enemy, dt)

        # Sync FSM state back so combat resolution path works
        # (The brain writes to player.rect for movement already)

        # Consume pending melee damage → resolve via CombatSystem
        pending_dmg = brain.get_pending_damage(player, enemy)
        if pending_dmg > 0:
            import math
            from settings import ATTACK_RANGE
            # check hitbox or range
            hitbox = player.attack_hitbox
            hit_ok = False
            if hitbox is not None:
                hit_ok = hitbox.colliderect(enemy.rect)
            else:
                d = math.hypot(
                    player.rect.centerx - enemy.rect.centerx,
                    player.rect.centery - enemy.rect.centery,
                )
                hit_ok = d <= ATTACK_RANGE
            if hit_ok:
                result = game.combat.player_attack(player, enemy)
                if result.hit and result.damage > 0:
                    if game.match_stats:
                        game.match_stats.record_player_damage(result.damage)
                    # Notify enemy AI of damage taken
                    now_sec = pygame.time.get_ticks() / 1000.0
                    if hasattr(enemy, 'ai_controller'):
                        enemy.ai_controller.notify_damage_taken(now_sec, result.damage)

        # Consume pending projectile
        if brain.get_pending_projectile():
            from settings import PROJECTILE_DAMAGE, PROJECTILE_SPEED
            game.projectiles.spawn_at(
                x=float(player.rect.centerx),
                y=float(player.rect.centery),
                target_x=float(enemy.rect.centerx),
                target_y=float(enemy.rect.centery),
                damage=PROJECTILE_DAMAGE,
                speed=PROJECTILE_SPEED,
                owner_id=id(player),
            )

        # Face toward opponent
        player.face_toward(enemy.rect.centerx)

    # ── Metrics sampling ──────────────────────────────────

    def _sample_metrics(self) -> None:
        game = self._game
        if game.enemy is None:
            return
        ai = getattr(game.enemy, 'ai_controller', None)
        if ai is None:
            return

        # Aggression level
        intent = getattr(ai.intent, 'aggression_level', None)
        if intent is not None:
            self._aggression_sum += intent
            self._aggression_samples += 1

        # Phase transition detection
        phase_name = ""
        if hasattr(ai, 'phase'):
            phase_name = getattr(ai.phase, 'phase_name', "")
        if phase_name and phase_name != self._last_phase:
            if self._last_phase:  # don't count the initial phase
                self._phase_transition_count += 1
            self._last_phase = phase_name

    # ── Result builders ───────────────────────────────────

    def _build_result(self, match_num: int, winner: str,
                      player_pers: str, start_time: float,
                      player_role: str = "",
                      enemy_role: str = "") -> MatchResult:
        game = self._game
        enemy_pers = ""
        if game.enemy:
            enemy_pers = getattr(game.enemy, 'archetype', "Unknown")
        avg_aggro = (
            self._aggression_sum / max(1, self._aggression_samples)
        )
        return MatchResult(
            match_number=match_num,
            winner=winner,
            player_personality=player_pers,
            enemy_personality=enemy_pers,
            player_role=player_role,
            enemy_role=enemy_role,
            duration_sec=time.monotonic() - start_time,
            avg_aggression=avg_aggro,
            phase_transitions=self._phase_transition_count,
        )

    # ── Summary printout ──────────────────────────────────

    def _print_summary(self) -> None:
        n = len(self._results)
        if n == 0:
            print("\nNo matches completed.")
            return

        print(f"\n{'=' * 58}")
        print(f"  Simulation Results  ({n} matches)")
        print(f"{'=' * 58}")

        # Win counts
        player_wins = sum(1 for r in self._results if r.winner == "player")
        enemy_wins = sum(1 for r in self._results if r.winner == "enemy")
        other = n - player_wins - enemy_wins

        print(f"\n  Player wins : {player_wins:>4d}  ({100 * player_wins / n:.1f}%)")
        print(f"  Enemy wins  : {enemy_wins:>4d}  ({100 * enemy_wins / n:.1f}%)")
        if other:
            print(f"  Other       : {other:>4d}  (timeout / aborted)")

        # Average duration
        durations = [r.duration_sec for r in self._results]
        avg_dur = sum(durations) / n
        print(f"\n  Avg match duration    : {avg_dur:.1f}s")

        # Average aggression
        aggros = [r.avg_aggression for r in self._results]
        avg_aggro = sum(aggros) / n
        print(f"  Avg aggression        : {avg_aggro:.3f}")

        # Average phase transitions
        phases = [r.phase_transitions for r in self._results]
        avg_phases = sum(phases) / n
        print(f"  Avg phase transitions : {avg_phases:.1f}")

        # ── Role Usage & Win Rates ────────────────────────
        self._print_role_table("Player Role Stats", "player")
        self._print_role_table("Enemy Role Stats",  "enemy")

        # ── Personality Distribution ──────────────────────
        # Enemy side
        pers_count: dict[str, int] = {}
        pers_wins: dict[str, int] = {}
        for r in self._results:
            name = r.enemy_personality or "Unknown"
            pers_count[name] = pers_count.get(name, 0) + 1
            if r.winner == "enemy":
                pers_wins[name] = pers_wins.get(name, 0) + 1

        print(f"\n  Enemy Personality Distribution:")
        for name in sorted(pers_count, key=lambda k: pers_count[k], reverse=True):
            cnt = pers_count[name]
            wins = pers_wins.get(name, 0)
            wr = 100 * wins / cnt if cnt else 0
            print(f"    {name:<14s}  played={cnt:>3d}  won={wins:>3d}  WR={wr:5.1f}%")

        # Player-side personality frequency
        p_pers_count: dict[str, int] = {}
        p_pers_wins: dict[str, int] = {}
        for r in self._results:
            name = r.player_personality or "Unknown"
            p_pers_count[name] = p_pers_count.get(name, 0) + 1
            if r.winner == "player":
                p_pers_wins[name] = p_pers_wins.get(name, 0) + 1

        print(f"\n  Player AI Personality Distribution:")
        for name in sorted(p_pers_count, key=lambda k: p_pers_count[k], reverse=True):
            cnt = p_pers_count[name]
            wins = p_pers_wins.get(name, 0)
            wr = 100 * wins / cnt if cnt else 0
            print(f"    {name:<14s}  played={cnt:>3d}  won={wins:>3d}  WR={wr:5.1f}%")

        print(f"\n{'=' * 58}\n")

    # ── Role table helper ─────────────────────────────────

    def _print_role_table(self, title: str, side: str) -> None:
        """Print a per-role usage / win-rate table for *side* ('player' or 'enemy')."""
        role_count: dict[str, int] = {}
        role_wins: dict[str, int] = {}
        role_dur: dict[str, list[float]] = {}

        for r in self._results:
            name = r.player_role if side == "player" else r.enemy_role
            if not name:
                name = "Unknown"
            role_count[name] = role_count.get(name, 0) + 1
            role_dur.setdefault(name, []).append(r.duration_sec)
            if r.winner == side:
                role_wins[name] = role_wins.get(name, 0) + 1

        n = len(self._results) or 1
        print(f"\n  {title}:")
        print(f"    {'Role':<12s}  {'Played':>6s}  {'Usage%':>6s}  {'Wins':>4s}  {'WR%':>6s}  {'AvgDur':>6s}")
        print(f"    {'-' * 48}")
        for name in sorted(role_count, key=lambda k: role_count[k], reverse=True):
            cnt = role_count[name]
            wins = role_wins.get(name, 0)
            wr = 100 * wins / cnt if cnt else 0
            usage = 100 * cnt / n
            avg_d = sum(role_dur[name]) / cnt
            print(f"    {name:<12s}  {cnt:>6d}  {usage:>5.1f}%  {wins:>4d}  {wr:>5.1f}%  {avg_d:>5.1f}s")
