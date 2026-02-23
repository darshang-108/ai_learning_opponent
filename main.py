"""
main.py - Entry point for AI Learning Opponent.

Integrates all systems:
- Pixel Character sprites (entities/character.py)
- Stamina system (systems/stamina_system.py)
- Perfect Parry (systems/combat_system.py)
- Roguelike Buff system (systems/buff_system.py)
- Enemy Personality AI (ai/ai_system.py)
- Execution / Finisher (systems/combat_system.py)
- Procedural VFX (systems/vfx_system.py)
- Local PVP Mode (systems/pvp_system.py)
- Avatar Generation (avatar_generator.py)
- Modular Architecture (separate system files)

Run:  python main.py
"""
VERSION = "1.1.0"

import pygame
import sys
import logging
import math

logger = logging.getLogger(__name__)

# ── Project imports ───────────────────────────────────────
from settings import (
    SCREEN_WIDTH, SCREEN_HEIGHT, FPS, TITLE, BG_COLOR, WHITE,
    PLAYER_ATTACK_DAMAGE, RED, GREEN, BLUE, YELLOW, CYAN, ORANGE,
    STAMINA_MAX, ATTACK_RANGE,
    PARRY_SLOWMO_SCALE, PARRY_SLOWMO_DURATION,
    EXECUTION_SLOWMO_SCALE, EXECUTION_SLOWMO_DURATION,
    HEALTHBAR_WIDTH, HEALTHBAR_HEIGHT, HEALTHBAR_Y,
    PLAYER_HB_X, ENEMY_HB_X,
    STAMINABAR_HEIGHT, STAMINABAR_Y,
    ENEMY_QUICK_DAMAGE, ENEMY_HEAVY_DAMAGE,
    PROJECTILE_DAMAGE, PROJECTILE_SPEED, PROJECTILE_COLOR,
)
from entities import Player, Enemy
from systems.combat_system import CombatSystem, CombatResult
from systems.stamina_system import StaminaSystem
from systems.buff_system import BuffManager, roll_buff_drop, draw_buff_indicators
from systems.vfx_system import VFXSystem
from systems.pvp_system import PVPManager
from systems.projectile_system import ProjectileSystem, Projectile
from systems.healthbar import draw_health_bars, _clear_cache as clear_healthbar_cache
from utils import draw_text, draw_end_screen
from utils.vfx import (
    draw_gradient, ScreenShake, FloatingTextManager, EffectsManager,
    TimeScaleManager, HitStop, CameraZoom, ImpactFlash,
    ComboCounter, draw_vignette, FinalHitCinematic, ArchetypeBanner,
)
from ai.data_logger import DataLogger
from ai.behavior_analyzer import BehaviorAnalyzer
from ai.stats import MatchStats
from ai.persistence import load_archetype_stats, update_after_match
from avatar_generator import (
    generate_avatar, load_cached_avatar, cache_avatar,
    pick_image_file, cleanup_original, _HAS_DEPS as _AVATAR_DEPS_OK,
)
from audio_manager import AudioManager
from keybinds import SOLO_KEYS, ControlsMenu


# ══════════════════════════════════════════════════════════
#  MODE SELECTION SCREEN
# ══════════════════════════════════════════════════════════

def _draw_mode_select(screen: pygame.Surface):
    """Draw the Solo / PVP mode selection screen."""
    draw_gradient(screen)
    cx = SCREEN_WIDTH // 2
    title_font = pygame.font.SysFont(None, 54)
    opt_font = pygame.font.SysFont(None, 36)
    hint_font = pygame.font.SysFont(None, 24)

    title = title_font.render("AI Learning Opponent", True, WHITE)
    screen.blit(title, (cx - title.get_width() // 2, 80))

    sub = hint_font.render("Adaptive Combat Game", True, (160, 160, 160))
    screen.blit(sub, (cx - sub.get_width() // 2, 130))

    options = [
        ("1.  Solo vs AI", (180, 200, 255)),
        ("2.  Local PVP (2 Players)", (255, 200, 180)),
        ("3.  Controls", (200, 255, 200)),
    ]
    y = 220
    for text, color in options:
        surf = opt_font.render(text, True, color)
        screen.blit(surf, (cx - surf.get_width() // 2, y))
        y += 55

    hint = hint_font.render(
        "Press 1, 2, or 3 to select  |  ESC to quit", True, (140, 140, 140),
    )
    screen.blit(hint, (cx - hint.get_width() // 2, SCREEN_HEIGHT - 50))
    pygame.display.flip()


# ══════════════════════════════════════════════════════════
#  STAMINA BAR DRAWING
# ══════════════════════════════════════════════════════════

def draw_stamina_bars(surface: pygame.Surface, player, enemy, dt: float = 0.016):
    """Draw stamina bars beneath health bars for both characters."""
    for i, (entity, hb_x) in enumerate([(player, PLAYER_HB_X),
                                         (enemy, ENEMY_HB_X)]):
        x = hb_x
        y = STAMINABAR_Y
        w = HEALTHBAR_WIDTH
        h = STAMINABAR_HEIGHT

        # Background
        pygame.draw.rect(surface, (40, 40, 40), (x, y, w, h), border_radius=2)

        # Fill
        if hasattr(entity, 'stamina_component'):
            frac = entity.stamina_component.stamina / max(1, entity.stamina_component.max_stamina)
        elif hasattr(entity, 'stamina'):
            frac = entity.stamina / max(1, entity.max_stamina)
        else:
            frac = 1.0
        fill_w = int(w * max(0.0, min(1.0, frac)))

        # Color: blue → orange when low
        if frac > 0.5:
            color = (60, 160, 255)
        elif frac > 0.25:
            color = (255, 180, 60)
        else:
            color = (255, 80, 60)

        if fill_w > 0:
            pygame.draw.rect(surface, color, (x, y, fill_w, h), border_radius=2)

        # Border
        pygame.draw.rect(surface, (80, 80, 80), (x, y, w, h), 1, border_radius=2)


# ══════════════════════════════════════════════════════════
#  GAME CLASS
# ══════════════════════════════════════════════════════════

class Game:
    """Top-level game controller.  Owns the loop, events, and rendering."""

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption(TITLE)
        self.clock = pygame.time.Clock()

        # Ensure persistent archetype stats file exists
        load_archetype_stats()

        # Avatar state (persists across resets)
        self._avatar_surface: pygame.Surface | None = load_cached_avatar(
            output_size=64
        )

        # Mode state
        self._show_mode_select = True
        self._mode = "solo"            # "solo" | "pvp"
        self._show_menu = False        # avatar menu (Solo only)

        # PVP manager (created on PVP start)
        self.pvp_manager: PVPManager | None = None

        # Solo-mode entities (created after mode/avatar selection)
        self.player: Player | None = None
        self.enemy: Enemy | None = None

        # Systems
        self.combat = CombatSystem()
        self.stamina_system = StaminaSystem()
        self.vfx = VFXSystem()
        self.projectiles = ProjectileSystem()

        # Behavior analysis (Phase 3)
        self.analyzer = BehaviorAnalyzer()
        self.player_style = "Unknown"

        # Data logging (Phase 2)
        self.logger = DataLogger()

        # Match statistics (Phase 6)
        self.match_stats: MatchStats | None = None

        # Visual-effects managers (legacy VFX)
        self.screen_shake = ScreenShake()
        self.floating_texts = FloatingTextManager()
        self.effects = EffectsManager()

        # Cinematic systems
        self.time_scale = TimeScaleManager()
        self.hit_stop = HitStop()
        self.camera_zoom = CameraZoom()
        self.impact_flash = ImpactFlash()
        self.combo = ComboCounter()
        self.final_hit = FinalHitCinematic()
        self.archetype_banner: ArchetypeBanner | None = None

        # Audio engine
        self.audio = AudioManager()

        # State
        self.game_state = "MENU"   # "MENU" | "PLAYING" | "GAME_OVER"
        self.running = True
        self.game_over = False
        self.winner_text = ""

        # Block timing registry
        self._player_block_was_pressed = False

        # Regen ring cooldown
        self._regen_ring_cd = 0.0

        # Buff drop pending
        self._buff_dropped = False

    # ── Solo-mode initialization ──────────────────────────

    def _init_solo(self):
        """Create solo-mode entities and start match."""
        self.player_style = self.analyzer.detect_player_style()
        logger.info("Detected player style: %s", self.player_style)

        self.player = Player()
        if self._avatar_surface:
            self.player.avatar_surface = self._avatar_surface

        self.enemy = Enemy(player_style=self.player_style)

        self.logger.start_match()
        self.match_stats = MatchStats(self.player_style, self.enemy.archetype)

        self.archetype_banner = ArchetypeBanner(
            f"Enemy: {self.enemy.archetype}"
        )

        self.game_over = False
        self.winner_text = ""
        self._buff_dropped = False

    # ── Main loop ─────────────────────────────────────────

    def run(self):
        """Start the game loop."""
        while self.running:
            self.clock.tick(FPS)

            if self.game_state == "MENU":
                self._handle_home_events()
                self._draw_home_screen()

            elif self.game_state == "PLAYING":
                if self._show_mode_select:
                    self._handle_mode_select_events()
                    _draw_mode_select(self.screen)
                elif self._show_menu:
                    self._handle_menu_events()
                    self._draw_menu()
                elif self._mode == "pvp" and self.pvp_manager:
                    self._handle_pvp_events()
                    self._update_pvp()
                    self._draw_pvp()
                else:
                    # Solo mode
                    self._handle_events()
                    self._update()
                    self._draw()

            elif self.game_state == "GAME_OVER":
                self._handle_game_over_events()
                self._draw_game_over_screen()

        pygame.quit()
        sys.exit()

    # ── Home Screen (MENU state) ──────────────────────────

    def _handle_home_events(self):
        """Process events on the home screen."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    self.game_state = "PLAYING"
                    self._show_mode_select = True
                elif event.key == pygame.K_ESCAPE:
                    self.running = False

    def _draw_home_screen(self):
        """Render the home / title screen."""
        self.screen.fill((15, 15, 25))
        cx = SCREEN_WIDTH // 2
        cy = SCREEN_HEIGHT // 2

        title_font = pygame.font.SysFont(None, 72)
        subtitle_font = pygame.font.SysFont(None, 36)
        footer_font = pygame.font.SysFont(None, 28)

        # Title
        title_surf = title_font.render("ADAPTIVE COMBAT AI", True, WHITE)
        self.screen.blit(
            title_surf,
            (cx - title_surf.get_width() // 2, cy - 80),
        )

        # Subtitle
        sub_surf = subtitle_font.render("Press ENTER to Start", True, (180, 200, 255))
        self.screen.blit(
            sub_surf,
            (cx - sub_surf.get_width() // 2, cy + 10),
        )

        # Footer
        foot_surf = footer_font.render("Press ESC to Quit", True, (140, 140, 140))
        self.screen.blit(
            foot_surf,
            (cx - foot_surf.get_width() // 2, SCREEN_HEIGHT - 60),
        )

        pygame.display.flip()

    # ── Mode selection ────────────────────────────────────

    def _handle_mode_select_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_1:
                    self._mode = "solo"
                    self._show_mode_select = False
                    self._show_menu = True  # Go to avatar menu
                elif event.key == pygame.K_2:
                    self._mode = "pvp"
                    self._show_mode_select = False
                    self._start_pvp()
                elif event.key == pygame.K_3:
                    self._open_controls_menu()
                elif event.key == pygame.K_ESCAPE:
                    self.game_state = "MENU"

    def _start_pvp(self):
        """Initialize PVP mode."""
        self.pvp_manager = PVPManager()
        self.pvp_manager.start_round()
        self.game_over = False

    def _open_controls_menu(self):
        """Open the full-screen controls rebinding UI."""
        menu = ControlsMenu()
        menu.run(self.screen, self.clock)

    # ── PVP event / update / draw ─────────────────────────

    def _handle_pvp_events(self):
        self._pvp_events = []
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self._show_mode_select = True
                    self.pvp_manager = None
                    return
                if event.key == pygame.K_r and self.pvp_manager and self.pvp_manager.round_over:
                    self.pvp_manager.start_round()
            self._pvp_events.append(event)

    def _update_pvp(self):
        if self.pvp_manager is None:
            return
        raw_dt = self.clock.get_time() / 1000.0
        keys = pygame.key.get_pressed()
        events = getattr(self, '_pvp_events', [])
        self.pvp_manager.handle_input(keys, events, self.combat)
        self.pvp_manager.update(raw_dt, self.combat)

        # Audio update
        self.audio.update(
            dt=raw_dt,
            time_scale=1.0,
            player_hp_frac=1.0,
            match_active=not self.pvp_manager.round_over,
        )

    def _draw_pvp(self):
        if self.pvp_manager is None:
            return
        raw_dt = self.clock.get_time() / 1000.0
        world = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        draw_gradient(world)
        self.pvp_manager.draw(world, raw_dt)
        draw_vignette(world)
        self.screen.blit(world, (0, 0))

        # Controls hint
        hint_font = pygame.font.SysFont(None, 18)
        p1h = hint_font.render("P1: WASD + F/G/H", True, (120, 120, 180))
        p2h = hint_font.render("P2: Arrows + Num1/2/3", True, (180, 120, 120))
        self.screen.blit(p1h, (10, SCREEN_HEIGHT - 20))
        self.screen.blit(p2h, (SCREEN_WIDTH - p2h.get_width() - 10, SCREEN_HEIGHT - 20))

        if self.pvp_manager.round_over:
            winner_text = "Draw!"
            if self.pvp_manager.winner:
                winner_text = f"Player {self.pvp_manager.winner.player_id} Wins!"
            draw_end_screen(self.screen, winner_text)

        pygame.display.flip()

    # ── Avatar menu ───────────────────────────────────────

    def _handle_menu_events(self):
        """Process events while the avatar selection menu is shown."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_1:
                    self._avatar_surface = None
                    self._show_menu = False
                    self._init_solo()
                elif event.key == pygame.K_2:
                    if _AVATAR_DEPS_OK:
                        self._try_generate_avatar()
                        self._show_menu = False
                        self._init_solo()
                    else:
                        logger.warning("opencv-python/numpy/scipy not installed – skipping avatar.")
                        self._avatar_surface = None
                        self._show_menu = False
                        self._init_solo()
                elif event.key == pygame.K_3 and self._avatar_surface is not None:
                    self._show_menu = False
                    self._init_solo()
                elif event.key == pygame.K_ESCAPE:
                    self._show_mode_select = True
                    self._show_menu = False

    def _draw_menu(self):
        """Render the avatar selection menu."""
        draw_gradient(self.screen)
        cx = SCREEN_WIDTH // 2

        title_font = pygame.font.SysFont(None, 48)
        opt_font = pygame.font.SysFont(None, 32)
        hint_font = pygame.font.SysFont(None, 24)

        title = title_font.render("Character Setup", True, WHITE)
        self.screen.blit(title, (cx - title.get_width() // 2, 100))

        opts = [
            ("1.  Default Character", (180, 200, 255)),
        ]
        if _AVATAR_DEPS_OK:
            opts.append(("2.  Upload Face Image", (180, 255, 180)))
        else:
            opts.append(("2.  Upload Face (needs opencv)", (120, 120, 120)))
        if self._avatar_surface is not None:
            opts.append(("3.  Reuse Cached Avatar", (255, 255, 180)))

        y = 200
        for text, color in opts:
            surf = opt_font.render(text, True, color)
            self.screen.blit(surf, (cx - surf.get_width() // 2, y))
            y += 50

        if self._avatar_surface is not None:
            preview = pygame.transform.smoothscale(
                self._avatar_surface, (96, 96),
            )
            self.screen.blit(preview, (cx - 48, y + 20))
            lbl = hint_font.render("(cached)", True, (160, 160, 160))
            self.screen.blit(lbl, (cx - lbl.get_width() // 2, y + 120))

        hint = hint_font.render(
            "Press a number key to choose  |  ESC to go back",
            True, (140, 140, 140),
        )
        self.screen.blit(hint, (cx - hint.get_width() // 2, SCREEN_HEIGHT - 50))
        pygame.display.flip()

    def _try_generate_avatar(self):
        """Open file dialog, generate poly-face, cache it."""
        draw_gradient(self.screen)
        draw_text(
            self.screen, "Opening file dialog...",
            SCREEN_WIDTH // 2 - 90, SCREEN_HEIGHT // 2,
            WHITE, 28,
        )
        pygame.display.flip()

        path = pick_image_file()
        if not path:
            logger.info("No file selected – using default avatar.")
            return

        draw_gradient(self.screen)
        draw_text(
            self.screen, "Generating low-poly avatar...",
            SCREEN_WIDTH // 2 - 120, SCREEN_HEIGHT // 2,
            WHITE, 28,
        )
        pygame.display.flip()

        surface = generate_avatar(path, output_size=64)
        if surface is not None:
            self._avatar_surface = surface
            cache_avatar(surface)
            logger.info("Avatar generated and cached.")
        else:
            logger.warning("Avatar generation failed – using default.")
            self._avatar_surface = None

    # ── Events (Solo Mode) ────────────────────────────────

    def _handle_events(self):
        if self.player is None:
            return
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            if event.type == pygame.KEYDOWN:
                # Quick attack
                if event.key == SOLO_KEYS["quick_attack"] and not self.game_over:
                    self._player_attack()

                # Dodge
                if event.key == SOLO_KEYS["dodge"] and not self.game_over:
                    keys = pygame.key.get_pressed()
                    if self.player is not None and self.player.try_dodge(keys):
                        self.audio.play_sfx("combo_whoosh",
                                            x_pos=float(self.player.rect.centerx))

                # ESC → back to home screen
                if event.key == pygame.K_ESCAPE:
                    self.game_state = "MENU"
                    self.player = None
                    self.enemy = None
                    self.game_over = False

    def _player_attack(self):
        """Handle a player attack input."""
        if self.player is None or self.enemy is None:
            return
        if not self.player.try_attack():
            return

        result = self.combat.player_attack(self.player, self.enemy)
        self.logger.log_attack()

        if result.hit:
            if self.match_stats:
                self.match_stats.record_player_damage(result.damage)
            # Notify AI brain of damage taken (for match flow / desperation)
            if self.enemy and hasattr(self.enemy, 'ai_controller'):
                now_sec = pygame.time.get_ticks() / 1000.0
                self.enemy.ai_controller.notify_damage_taken(now_sec, result.damage)
            self.combo.register_hit()
            combo_count = self.combo.count

            # Floating damage number
            ex = self.enemy.rect.centerx
            ey = self.enemy.rect.top - 10
            color = (255, 100, 100) if not result.execution else (255, 50, 50)
            size = 26 if not result.execution else 36
            label = f"-{result.damage}"
            if result.execution:
                label = f"EXECUTE! -{result.damage}"
            self.floating_texts.spawn(label, ex - 20, ey, color=color, size=size)

            # Impact ring
            self.effects.spawn_ring(
                self.enemy.rect.centerx, self.enemy.rect.centery,
                (255, 200, 80), max_radius=35, duration=0.3,
            )

            # VFX: blood + sparks
            self.vfx.spawn_blood(
                float(self.enemy.rect.centerx), float(self.enemy.rect.centery),
            )
            self.vfx.spawn_impact_sparks(
                float(self.enemy.rect.centerx), float(self.enemy.rect.centery),
            )

            # Screen shake + flash
            shake_intensity = 4 if not result.execution else 12
            self.screen_shake.trigger(intensity=shake_intensity, duration=0.12)
            self.impact_flash.trigger(color=(255, 255, 255), alpha=80, duration=0.08)
            self.hit_stop.trigger(0.04 if not result.execution else 0.12)

            # Audio
            sfx = "heavy_hit" if result.execution else "light_hit"
            self.audio.play_sfx(sfx, x_pos=float(self.enemy.rect.centerx))
            self.audio.play_sfx("health_tick")

            # Execution cinematic
            if result.execution:
                self.vfx.spawn_execution_burst(
                    float(self.enemy.rect.centerx), float(self.enemy.rect.centery),
                )
                self.time_scale.trigger(scale=EXECUTION_SLOWMO_SCALE,
                                        duration=EXECUTION_SLOWMO_DURATION)
                self.camera_zoom.punch(1.15, decay=0.03)
                self.audio.play_layered(
                    ["heavy_hit", "heavy_transient", "heavy_debris"],
                    x_pos=float(self.enemy.rect.centerx),
                )

            # Combo whoosh at 3+ hits
            if combo_count >= 3:
                self.audio.play_sfx("combo_whoosh",
                                    x_pos=float(self.enemy.rect.centerx))

        elif result.blocked:
            # Blocked hit – spark VFX + stamina chip feedback
            self.floating_texts.spawn(
                "BLOCKED", self.enemy.rect.centerx - 30,
                self.enemy.rect.top - 10, color=(180, 180, 255), size=22,
            )
            # Block spark effect
            self.vfx.spawn_impact_sparks(
                float(self.enemy.rect.centerx),
                float(self.enemy.rect.centery),
                color=(200, 220, 255), count=6,
            )
            self.screen_shake.trigger(intensity=2, duration=0.06)
            self.hit_stop.trigger(0.02)
            self.audio.play_sfx("light_hit", x_pos=float(self.enemy.rect.centerx))
            # Block knockback
            if result.block_knockback_vx:
                self.enemy.apply_knockback(result.block_knockback_vx)
            # Notify AI: player attack was blocked (for balancer)
            if hasattr(self.enemy, 'ai_controller'):
                self.enemy.ai_controller.notify_player_missed()
        else:
            # Player attack missed entirely
            if hasattr(self.enemy, 'ai_controller'):
                self.enemy.ai_controller.notify_player_missed()

    # ── Update (Solo Mode) ────────────────────────────────

    def _update(self):
        """Per-frame game logic."""
        if self.player is None or self.enemy is None:
            return

        # Raw delta time
        raw_dt = self.clock.get_time() / 1000.0

        # Apply time-scale (slow-motion)
        dt = self.time_scale.apply(raw_dt)

        # Hit-stop: skip movement updates while frozen
        frozen = self.hit_stop.frozen(raw_dt)

        # Camera zoom interpolation
        self.camera_zoom.update(raw_dt)

        # Tick cinematic overlays
        self.combo.update(dt)
        if self.archetype_banner:
            self.archetype_banner.update(dt)
        self.final_hit.update(dt)

        if frozen:
            self.floating_texts.update(dt)
            self.effects.update(dt)
            self.vfx.update(dt)
            return

        # ── Player input ─────────────────────────────────
        keys = pygame.key.get_pressed()
        self.player.handle_input(keys)

        # Block (held key)
        block_pressed = keys[SOLO_KEYS["block"]]
        was_blocking = self.player.is_blocking
        self.player.try_block(block_pressed)

        # Register block start/end for parry detection
        if self.player.is_blocking and not was_blocking:
            self.combat.register_block_start(self.player)
        elif not self.player.is_blocking and was_blocking:
            self.combat.register_block_end(self.player)

        # Player animation update
        self.player.update_animation(dt)

        # Log movement
        if any(keys[k] for k in (SOLO_KEYS["move_left"], SOLO_KEYS["move_right"],
                                  SOLO_KEYS["move_up"], SOLO_KEYS["move_down"])):
            self.logger.log_movement()

        # ── Stamina system update ────────────────────────
        self.stamina_system.update(self.player, dt)
        self.stamina_system.update(self.enemy, dt)

        # ── Buff system update ───────────────────────────
        self.player.buff_manager.update(dt, self.player)
        self.enemy.buff_manager.update(dt, self.enemy)

        # ── Enemy AI ─────────────────────────────────────
        prev_state = self.enemy.state

        # Pass player activity info to enemy
        player_is_active = (
            any(keys[k] for k in (SOLO_KEYS["move_left"], SOLO_KEYS["move_right"],
                                  SOLO_KEYS["move_up"], SOLO_KEYS["move_down"]))
            or self.player.is_attacking
        )
        self.enemy.clock_dt = dt
        self.enemy.update(self.player, player_is_active=player_is_active, dt=dt)

        # Face toward each other
        self.player.face_toward(self.enemy.rect.centerx)

        # ── Enemy MELEE attack resolution ────────────────
        # The AIController buffers damage in _pending_damage.
        # We consume it here via get_pending_damage().
        pending_damage = self.enemy.ai_controller.get_pending_damage(
            self.enemy, self.player,
        )

        if pending_damage > 0:
            # Hitbox collision check (if enemy has active hitbox)
            hitbox = self.enemy.attack_hitbox
            hit_confirmed = False
            if hitbox is not None:
                hit_confirmed = hitbox.colliderect(self.player.rect)
                if hit_confirmed:
                    logger.debug("Hitbox collision confirmed (enemy → player)")
            else:
                # Fallback: range check
                dist_check = math.hypot(
                    self.enemy.rect.centerx - self.player.rect.centerx,
                    self.enemy.rect.centery - self.player.rect.centery,
                )
                hit_confirmed = dist_check <= ATTACK_RANGE
                if hit_confirmed:
                    logger.debug("Range collision confirmed (enemy → player, dist=%.0f)", dist_check)

            if hit_confirmed:
                atk_type = self.enemy.last_attack_type or "quick"
                result = self.combat.enemy_attack(
                    self.enemy, self.player,
                    damage=pending_damage,
                    attack_type=atk_type,
                )
                self._handle_enemy_hit_result(result)

                # Notify AI brain: hit landed → queues combo + match flow
                if result.hit and result.damage > 0:
                    self.enemy.ai_controller.notify_hit_landed()
                    now_sec = pygame.time.get_ticks() / 1000.0
                    self.enemy.ai_controller.notify_damage_dealt(now_sec, result.damage)

                # Weapon trail VFX on every attack (all personalities)
                ex = float(self.enemy.rect.centerx)
                ey = float(self.enemy.rect.centery)
                trail_dx = 35.0 * self.enemy.facing
                is_duelist = self.enemy.personality.name == "Duelist"
                trail_color = (180, 220, 255) if is_duelist else (220, 200, 180)
                self.vfx.spawn_weapon_trail(
                    ex, ey - 10, ex + trail_dx, ey + 10,
                    color=trail_color,
                )
                # Counter/combo attacks get extra feedback
                if atk_type in ("counter", "combo"):
                    label = "COUNTER!" if atk_type == "counter" else "COMBO!"
                    color = (80, 220, 255) if atk_type == "counter" else (255, 200, 60)
                    self.floating_texts.spawn(
                        label,
                        self.enemy.rect.centerx - 30,
                        self.enemy.rect.top - 30,
                        color=color, size=28,
                    )

                # Match stats
                if self.match_stats:
                    self.match_stats.record_enemy_attack(
                        attack_type=atk_type,
                        damage=result.damage,
                        was_combo=self.enemy._was_combo,
                    )

        # ── Enemy PROJECTILE spawning ────────────────────
        if self.enemy.ai_controller.get_pending_projectile():
            self.projectiles.spawn_at(
                x=float(self.enemy.rect.centerx),
                y=float(self.enemy.rect.centery),
                target_x=float(self.player.rect.centerx),
                target_y=float(self.player.rect.centery),
                damage=PROJECTILE_DAMAGE,
                speed=PROJECTILE_SPEED,
                owner_id=id(self.enemy),
            )
            self.audio.play_sfx("combo_whoosh",
                                x_pos=float(self.enemy.rect.centerx))

        # ── Projectile update & collision ────────────────
        self.projectiles.update(dt)
        proj_hits = self.projectiles.check_collisions(self.player)
        for proj in proj_hits:
            # Apply projectile damage through CombatSystem
            result = self.combat.enemy_attack(
                self.enemy, self.player,
                damage=proj.damage,
                attack_type="magic",
            )
            if result.hit and result.damage > 0:
                px = self.player.rect.centerx
                py = self.player.rect.centery
                # Magic impact VFX
                self.vfx.spawn_magic_impact(float(px), float(py))
                self.vfx.spawn_hit_flash(float(px), float(py))
                # Floating damage number
                self.floating_texts.spawn(
                    f"-{result.damage}", px - 12,
                    self.player.rect.top - 10,
                    color=(180, 120, 255), size=26,
                )
                # Screen shake + flash
                self.screen_shake.trigger(intensity=5, duration=0.12)
                self.impact_flash.trigger(
                    color=(180, 120, 255), alpha=80, duration=0.1,
                )
                self.audio.play_sfx("light_hit", x_pos=float(px))
                self.audio.play_sfx("health_tick")
                logger.debug("Projectile hit player for %d damage", result.damage)

        # ── Match stats tracking ─────────────────────────
        if self.match_stats:
            if self.enemy.state == "chase":
                self.match_stats.record_forward_move()
            if self.enemy.state == "retreat" and prev_state != "retreat":
                self.match_stats.record_enemy_retreat()

        # Log player-enemy distance
        dist = math.hypot(
            self.player.rect.centerx - self.enemy.rect.centerx,
            self.player.rect.centery - self.enemy.rect.centery,
        )
        self.logger.log_distance(dist)

        # ── Regen VFX ────────────────────────────────────
        if self.enemy._is_regenerating:
            self._regen_ring_cd -= dt
            if self._regen_ring_cd <= 0:
                self.effects.spawn_ring(
                    self.enemy.rect.centerx, self.enemy.rect.centery,
                    (80, 255, 80), max_radius=50, duration=0.7, width=2,
                )
                self.vfx.spawn_heal_sparkle(
                    float(self.enemy.rect.centerx),
                    float(self.enemy.rect.centery),
                )
                self.audio.play_sfx("regen_tick",
                                    x_pos=float(self.enemy.rect.centerx))
                self._regen_ring_cd = 1.0

        # ── Desperation aura VFX ─────────────────────────
        if hasattr(self.enemy.ai_controller, 'desperation'):
            desp = self.enemy.ai_controller.desperation
            if desp.active:
                # Red aura particles around enemy, intensity scales with desperation
                count = max(1, int(3 * desp.modifiers.intensity))
                self.vfx.spawn_aura_particles(
                    float(self.enemy.rect.centerx),
                    float(self.enemy.rect.centery),
                    color=(255, 60, 40), count=count, radius=28,
                )
                # Rage mode: extra golden/orange particles + glow
                if desp.modifiers.rage_active:
                    self.vfx.spawn_aura_particles(
                        float(self.enemy.rect.centerx),
                        float(self.enemy.rect.centery),
                        color=(255, 180, 30), count=count + 2, radius=35,
                    )

        # ── Phase transition cinematic triggers ───────────
        ai = self.enemy.ai_controller
        if hasattr(ai, 'event_phase_transition') and ai.event_phase_transition:
            # Phase shift burst: aggression spike VFX + screen shake
            ex = float(self.enemy.rect.centerx)
            ey = float(self.enemy.rect.centery)
            phase_name = ai.phase.phase_name if hasattr(ai, 'phase') else "?"
            # Burst ring
            self.effects.spawn_ring(
                int(ex), int(ey),
                (255, 200, 80), max_radius=80, duration=0.5, width=3,
            )
            self.vfx.spawn_impact_sparks(ex, ey, color=(255, 220, 100), count=12)
            self.screen_shake.trigger(intensity=4, duration=0.15)
            # Floating label
            phase_colors = {
                "OBSERVE": (120, 200, 255),
                "COUNTER": (255, 200, 80),
                "DESPERATION": (255, 80, 50),
                "RAGE": (255, 40, 20),
            }
            label_color = phase_colors.get(phase_name, (255, 255, 255))
            self.floating_texts.spawn(
                f">> {phase_name} <<",
                int(ex) - 50, int(ey) - 60,
                color=label_color, size=32,
            )

        # ── Rage mode entry cinematic ─────────────────────
        if hasattr(ai, 'event_rage_entered') and ai.event_rage_entered:
            ex = float(self.enemy.rect.centerx)
            ey = float(self.enemy.rect.centery)
            # Heavy screen shake + slow-mo hint
            self.screen_shake.trigger(intensity=8, duration=0.25)
            # Big burst explosion
            self.vfx.spawn_impact_sparks(ex, ey, color=(255, 50, 20), count=25)
            self.effects.spawn_ring(
                int(ex), int(ey),
                (255, 30, 10), max_radius=120, duration=0.7, width=4,
            )
            self.floating_texts.spawn(
                "!! RAGE !!",
                int(ex) - 40, int(ey) - 80,
                color=(255, 20, 10), size=36,
            )

        # ── Tick VFX ─────────────────────────────────────
        self.floating_texts.update(dt)
        self.effects.update(dt)
        self.vfx.update(dt)

        # ── Audio update ─────────────────────────────────
        player_hp_frac = self.player.hp / max(1, self.player.max_hp)
        self.audio.update(
            dt=raw_dt,
            time_scale=self.time_scale.scale,
            player_hp_frac=player_hp_frac,
            match_active=not self.game_over,
        )

        # Aggression snapshot
        if self.match_stats:
            self.match_stats.tick()

        # ── Parry bonus decay ────────────────────────────
        if self.player.damage_mult > 1.0:
            self.player.damage_mult -= dt * 0.5
            if self.player.damage_mult < 1.0:
                self.player.damage_mult = 1.0

        # Note: player.is_attacking is managed by the animation system
        # in update_animation(). Do NOT forcibly clear it here, or the
        # hitbox system won't work across the full attack duration.

        # ── Win/loss check ───────────────────────────────
        if not self.enemy.alive:
            self._on_match_end("Player Wins!", "win", enemy_won=False)
        elif not self.player.alive:
            self._on_match_end("Enemy Wins!", "lose", enemy_won=True)

    def _handle_enemy_hit_result(self, result: CombatResult):
        """React to enemy attack result with VFX, audio, and feedback."""
        assert self.player is not None  # called from _update which checks
        if result.parried:
            # Perfect parry!
            self.floating_texts.spawn(
                "PERFECT PARRY!", self.player.rect.centerx - 50,
                self.player.rect.top - 20, color=CYAN, size=30,
            )
            self.vfx.spawn_parry_flash(
                float(self.player.rect.centerx),
                float(self.player.rect.centery),
            )
            self.screen_shake.trigger(intensity=6, duration=0.15)
            self.time_scale.trigger(scale=PARRY_SLOWMO_SCALE,
                                    duration=PARRY_SLOWMO_DURATION)
            self.impact_flash.trigger(color=CYAN, alpha=100, duration=0.12)
            self.audio.play_layered(
                ["heavy_hit", "heavy_transient"],
                x_pos=float(self.player.rect.centerx),
            )
            return

        if result.hit and result.damage > 0:
            px = self.player.rect.centerx
            py = self.player.rect.top - 10
            self.floating_texts.spawn(
                f"-{result.damage}", px - 12, py,
                color=(255, 60, 60), size=26,
            )
            self.vfx.spawn_blood(float(px), float(self.player.rect.centery))

            is_duelist_hit = (
                self.enemy is not None
                and self.enemy.personality.name == "Duelist"
            )

            if result.attack_type == "heavy":
                self.screen_shake.trigger(intensity=7, duration=0.18)
                self.time_scale.trigger(scale=0.35, duration=0.15)
                self.camera_zoom.punch(1.08, decay=0.04)
                self.impact_flash.trigger(color=(255, 100, 100), alpha=120,
                                          duration=0.12)
                self.hit_stop.trigger(0.05)
                self.audio.play_layered(
                    ["heavy_hit", "heavy_transient", "heavy_debris"],
                    x_pos=float(px),
                )
            elif result.attack_type in ("counter", "combo") and is_duelist_hit:
                # Duelist counter/combo: sharp, precise feedback
                shake = 5 if result.attack_type == "counter" else 3
                self.screen_shake.trigger(intensity=shake, duration=0.10)
                self.hit_stop.trigger(0.04)
                flash_color = (80, 220, 255) if result.attack_type == "counter" else (255, 200, 60)
                self.impact_flash.trigger(color=flash_color, alpha=90,
                                          duration=0.08)
                self.camera_zoom.punch(1.05, decay=0.05)
                self.audio.play_sfx("heavy_hit", x_pos=float(px))
            elif is_duelist_hit:
                # Duelist quick hit: slightly stronger feedback
                self.screen_shake.trigger(intensity=4, duration=0.10)
                self.impact_flash.trigger(color=(255, 220, 180), alpha=70,
                                          duration=0.07)
                self.hit_stop.trigger(0.03)
                self.audio.play_sfx("light_hit", x_pos=float(px))
            else:
                self.screen_shake.trigger(intensity=3, duration=0.08)
                self.impact_flash.trigger(color=(255, 255, 255), alpha=60,
                                          duration=0.06)
                self.audio.play_sfx("light_hit", x_pos=float(px))

            self.audio.play_sfx("health_tick")

        elif result.blocked:
            self.floating_texts.spawn(
                "BLOCKED", self.player.rect.centerx - 30,
                self.player.rect.top - 10, color=(200, 200, 255), size=22,
            )
            # Block spark VFX
            self.vfx.spawn_impact_sparks(
                float(self.player.rect.centerx),
                float(self.player.rect.centery),
                color=(200, 220, 255), count=6,
            )
            self.screen_shake.trigger(intensity=2, duration=0.06)
            self.hit_stop.trigger(0.02)
            self.audio.play_sfx("light_hit", x_pos=float(self.player.rect.centerx))
            # Block knockback
            if result.block_knockback_vx:
                self.player.apply_knockback(result.block_knockback_vx)
            # Notify AI that the player successfully blocked
            if self.enemy and hasattr(self.enemy, "ai_controller"):
                self.enemy.ai_controller.notify_player_blocked()
        else:
            # Enemy attack missed / player dodged
            if self.enemy and hasattr(self.enemy, "ai_controller"):
                self.enemy.ai_controller.notify_player_dodged()

    def _on_match_end(self, text: str, outcome: str, enemy_won: bool):
        """Handle end-of-match logic."""
        if self.game_over:
            return
        self.game_over = True
        self.game_state = "GAME_OVER"
        self.winner_text = text
        self.logger.end_match(outcome)
        if self.match_stats:
            self.match_stats.end_match(outcome)

        if self.enemy:
            update_after_match(
                self.enemy.archetype,
                enemy_won=enemy_won,
                damage_dealt=self.match_stats.damage_dealt if self.match_stats else 0,
                match_duration=self.match_stats.match_duration if self.match_stats else 0,
            )

        # Death VFX
        target = self.enemy if not enemy_won else self.player
        if target:
            self.vfx.spawn_death_particles(
                float(target.rect.centerx), float(target.rect.centery),
                target.base_color,
            )

        # Final-hit cinematic
        if not self.final_hit.active:
            self.final_hit.trigger(
                self.screen_shake, self.time_scale,
                self.camera_zoom, self.impact_flash,
            )
            winner = "player" if not enemy_won else "enemy"
            self.audio.trigger_death_sequence(winner=winner)

        # Buff drop for player on win
        if not enemy_won and not self._buff_dropped and self.player:
            buff = roll_buff_drop()
            if buff is not None:
                self.player.buff_manager.add_buff(buff, self.player)
                self.floating_texts.spawn(
                    f"+{buff.name}!", self.player.rect.centerx - 30,
                    self.player.rect.top - 30, color=buff.color, size=28,
                )
            self._buff_dropped = True

    # ── Game Over (GAME_OVER state) ───────────────────────

    def _handle_game_over_events(self):
        """Process events on the game-over screen."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    self.reset_game()
                elif event.key == pygame.K_ESCAPE:
                    self.game_state = "MENU"
                    self.player = None
                    self.enemy = None
                    self.game_over = False

    def _update_game_over(self):
        """Minimal per-frame update during GAME_OVER (VFX & cinematics only)."""
        raw_dt = self.clock.get_time() / 1000.0
        dt = self.time_scale.apply(raw_dt)

        # Keep cinematics alive
        self.camera_zoom.update(raw_dt)
        self.combo.update(dt)
        if self.archetype_banner:
            self.archetype_banner.update(dt)
        self.final_hit.update(dt)

        # Keep VFX animating
        self.floating_texts.update(dt)
        self.effects.update(dt)
        self.vfx.update(dt)

        # Audio heartbeat
        player_hp_frac = (
            self.player.hp / max(1, self.player.max_hp)
            if self.player else 1.0
        )
        self.audio.update(
            dt=raw_dt,
            time_scale=self.time_scale.scale,
            player_hp_frac=player_hp_frac,
            match_active=False,
        )

    def _draw_game_over_screen(self):
        """Render the frozen game world with the game-over overlay."""
        self._update_game_over()
        self._draw()

    def reset_game(self):
        """Reset all game variables and start a fresh match."""
        self._reset()
        self.game_state = "PLAYING"

    # ── Draw (Solo Mode) ──────────────────────────────────

    def _draw(self):
        """Render everything to the screen."""
        if self.player is None:
            return
        raw_dt = self.clock.get_time() / 1000.0

        world = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        draw_gradient(world)

        # Screen shake offset
        sx, sy = self.screen_shake.get_offset(raw_dt)

        if sx or sy:
            shifted = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            draw_gradient(shifted)
            self._draw_world(shifted, raw_dt)
            world.blit(shifted, (sx, sy))
        else:
            self._draw_world(world, raw_dt)

        # Vignette
        draw_vignette(world)

        # Camera zoom → blit to screen
        self.camera_zoom.apply(world, self.screen)

        # Post-composite overlays
        self.impact_flash.draw(self.screen, raw_dt)
        self.combo.draw(self.screen)
        self.final_hit.draw(self.screen)

        # Game-over overlay
        if self.game_over and not self.final_hit.active:
            draw_end_screen(self.screen, self.winner_text)

        pygame.display.flip()

    def _draw_world(self, surface, dt: float = 0.016):
        """Draw all game entities, HUD, and VFX onto the given surface."""
        if self.player is None or self.enemy is None:
            return

        # Arena floor line
        pygame.draw.line(surface, (60, 60, 60),
                         (0, self.player.rect.bottom + 4),
                         (SCREEN_WIDTH, self.player.rect.bottom + 4), 1)

        # Entities
        self.player.draw(surface, dt=dt)
        self.enemy.draw(surface, dt=dt)

        # Projectiles
        self.projectiles.draw(surface)

        # VFX layers
        self.vfx.draw(surface)
        self.floating_texts.draw(surface)
        self.effects.draw(surface)

        # HUD: Health bars
        draw_health_bars(surface, self.player, self.enemy, dt=dt)

        # HUD: Stamina bars
        draw_stamina_bars(surface, self.player, self.enemy, dt)

        # HUD: Buff indicators
        if self.player.buff_manager.active_buffs:
            draw_buff_indicators(surface, self.player.buff_manager,
                                 PLAYER_HB_X, STAMINABAR_Y + STAMINABAR_HEIGHT + 6)
        if self.enemy.buff_manager.active_buffs:
            draw_buff_indicators(surface, self.enemy.buff_manager,
                                 ENEMY_HB_X, STAMINABAR_Y + STAMINABAR_HEIGHT + 6)

        # Controls hint
        draw_text(
            surface,
            "Arrows=Move  Space=Attack  Shift=Block  Z=Dodge",
            SCREEN_WIDTH // 2 - 200, SCREEN_HEIGHT - 28,
            WHITE, 18,
        )

        # Archetype banner
        if self.archetype_banner:
            self.archetype_banner.draw(surface)

        # Debug HUD
        state_label = f"Enemy: {self.enemy.archetype} ({self.enemy.state})"
        if self.enemy.last_attack_type:
            state_label += f"  |  {self.enemy.last_attack_type}"
        # Show tempo mode and intent level from new AI brain
        if hasattr(self.enemy.ai_controller, 'aggression'):
            tempo = self.enemy.ai_controller.aggression.tempo_mode
            intent = self.enemy.ai_controller.intent.attack_intent
            state_label += f"  |  {tempo} ({intent:.1f})"
        draw_text(surface, state_label, SCREEN_WIDTH // 2 - 180, 10, WHITE, 18)

        hud_line = (
            f"Style: {self.player_style}"
            f"  |  Personality: {self.enemy.archetype}"
        )
        draw_text(
            surface, hud_line,
            SCREEN_WIDTH // 2 - 180, SCREEN_HEIGHT - 48,
            (160, 160, 160), 18,
        )

    # ── Reset ─────────────────────────────────────────────

    def _reset(self):
        """Restart the game without closing the window."""
        self.combat.reset()
        self._init_solo()

        # Apply avatar
        if self.player and self._avatar_surface is not None:
            self.player.avatar_surface = self._avatar_surface

        # Reset VFX
        self.screen_shake = ScreenShake()
        self.floating_texts = FloatingTextManager()
        self.effects = EffectsManager()
        self.vfx = VFXSystem()
        self.projectiles.clear()
        clear_healthbar_cache()
        self._regen_ring_cd = 0.0
        self._player_block_was_pressed = False

        # Reset cinematic state
        self.time_scale = TimeScaleManager()
        self.hit_stop = HitStop()
        self.camera_zoom = CameraZoom()
        self.impact_flash = ImpactFlash()
        self.combo = ComboCounter()
        self.final_hit = FinalHitCinematic()

        # Reset audio state
        self.audio.reset()


# ── Run ───────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    Game().run()
