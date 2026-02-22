"""
settings.py - Game constants for AI Learning Opponent.

All configurable values live here so they're easy to tweak
and easy to reference from any module.
"""

# ── Screen ────────────────────────────────────────────────
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 60
TITLE = "AI Learning Opponent – Adaptive Combat"
BG_COLOR = (30, 30, 30)

# ── Arena ─────────────────────────────────────────────────
ARENA_FLOOR_Y = 460            # Y where characters stand
ARENA_LEFT = 40
ARENA_RIGHT = SCREEN_WIDTH - 40

# ── Colors (R, G, B) ─────────────────────────────────────
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BLUE = (50, 100, 255)          # Player 1
RED = (220, 50, 50)            # Enemy / Player 2
GREEN = (50, 200, 50)          # Health bar fill
DARK_GREEN = (0, 100, 0)       # Health bar fill (enemy)
GRAY = (60, 60, 60)            # Health bar background
YELLOW = (255, 220, 60)
CYAN = (80, 220, 255)
ORANGE = (255, 160, 40)
PURPLE = (180, 80, 255)

# ── Character dimensions (pixel sprite) ──────────────────
CHAR_WIDTH = 48
CHAR_HEIGHT = 56
PLAYER_WIDTH = CHAR_WIDTH      # backward compat
PLAYER_HEIGHT = CHAR_HEIGHT
ENEMY_WIDTH = CHAR_WIDTH
ENEMY_HEIGHT = CHAR_HEIGHT

# ── Player 1 settings ────────────────────────────────────
PLAYER_SPEED = 5
PLAYER_MAX_HP = 120
PLAYER_START_X = 150
PLAYER_START_Y = ARENA_FLOOR_Y - CHAR_HEIGHT

# ── Enemy settings ────────────────────────────────────────
ENEMY_SPEED = 2
ENEMY_MAX_HP = 120
ENEMY_START_X = 600
ENEMY_START_Y = ARENA_FLOOR_Y - CHAR_HEIGHT

# ── Combat settings ───────────────────────────────────────
ATTACK_RANGE = 75              # Pixels – melee hit range
PLAYER_ATTACK_DAMAGE = 12
PLAYER_ATTACK_COOLDOWN = 0.45  # Seconds between player attacks
BLOCK_DAMAGE_REDUCTION = 0.60  # 60 % damage blocked

# (Legacy single-value constants kept for backward compat)
ENEMY_ATTACK_DAMAGE = 5
ENEMY_ATTACK_COOLDOWN = 1.0
ENEMY_ATTACK_RANGE = 70

# ── Enemy attack profiles ────────────────────────────────
ENEMY_QUICK_DAMAGE   = 5
ENEMY_QUICK_RANGE    = 65
ENEMY_QUICK_COOLDOWN = 500     # ms

ENEMY_HEAVY_DAMAGE   = 12
ENEMY_HEAVY_RANGE    = 85
ENEMY_HEAVY_COOLDOWN = 1400    # ms

ENEMY_RETREAT_DURATION = 600
ENEMY_RETREAT_SPEED    = 4

# ── Stamina system ────────────────────────────────────────
STAMINA_MAX = 100.0
STAMINA_REGEN_RATE = 18.0      # per second (when idle)
STAMINA_REGEN_DELAY = 0.6      # seconds after last action before regen
STAMINA_ATTACK_COST = 22.0
STAMINA_DODGE_COST = 28.0
STAMINA_BLOCK_COST_PER_SEC = 14.0
STAMINA_HEAVY_ATTACK_COST = 35.0
STAMINA_LOW_THRESHOLD = 0.25   # fraction – AI notices when player is low

# ── Perfect Parry ─────────────────────────────────────────
PARRY_WINDOW = 0.18            # seconds before impact to trigger parry
PARRY_STUN_DURATION = 1.2      # seconds enemy is stunned
PARRY_BONUS_DAMAGE_MULT = 1.8  # bonus damage multiplier during stun
PARRY_FLASH_DURATION = 0.15    # screen flash
PARRY_SLOWMO_SCALE = 0.2       # time scale during parry slow-motion
PARRY_SLOWMO_DURATION = 0.35   # duration of parry slow-motion

# ── Dodge / Roll ──────────────────────────────────────────
DODGE_SPEED = 12               # pixels per frame during dodge
DODGE_DURATION = 0.2           # seconds of iframe
DODGE_COOLDOWN = 0.5           # seconds between dodges
DODGE_IFRAMES = True           # invincibility during dodge

# ── Buff system ───────────────────────────────────────────
BUFF_DROP_CHANCE = 1.0         # 100% drop on enemy defeat (roguelike)
BUFF_BASE_DURATION = 8.0       # seconds

BUFF_RAGE_ATTACK_SPEED_MULT = 1.5
BUFF_RAGE_DURATION = 8.0

BUFF_SHIELD_DAMAGE_REDUCTION = 0.40   # extra 40% reduction
BUFF_SHIELD_DURATION = 10.0

BUFF_LIFESTEAL_FRACTION = 0.25        # heal 25% of damage dealt
BUFF_LIFESTEAL_DURATION = 8.0

BUFF_FROST_SLOW_MULT = 0.55           # enemy speed multiplied by this
BUFF_FROST_DURATION = 6.0

BUFF_SHADOW_DODGE_BONUS = 0.35        # +35% dodge chance
BUFF_SHADOW_DURATION = 7.0

# ── Execution / Finisher ─────────────────────────────────
EXECUTION_HP_THRESHOLD = 0.15  # fraction of max HP
EXECUTION_DAMAGE_MULT = 3.0
EXECUTION_SLOWMO_SCALE = 0.15
EXECUTION_SLOWMO_DURATION = 0.6

# ── Invulnerability frames ────────────────────────────────
HIT_INVULN_DURATION = 0.25     # seconds of i-frames after taking damage

# ── Hitbox system ─────────────────────────────────────────
MELEE_HITBOX_WIDTH = 40        # pixels – width of melee attack hitbox
MELEE_HITBOX_HEIGHT = 50       # pixels – height of melee attack hitbox
MELEE_HITBOX_OFFSET_X = 30     # pixels – offset from character center
ATTACK_ACTIVE_START = 0.3      # fraction of attack anim when hitbox activates
ATTACK_ACTIVE_END = 0.7        # fraction of attack anim when hitbox deactivates

# ── Projectile / Magic system ─────────────────────────────
PROJECTILE_SPEED = 350.0       # pixels/sec
PROJECTILE_DAMAGE = 8
PROJECTILE_RADIUS = 8          # collision and visual radius
PROJECTILE_LIFETIME = 3.0      # seconds before self-destruct
PROJECTILE_COOLDOWN = 2.0      # seconds between projectile spawns
PROJECTILE_GLOW_RADIUS = 18    # outer glow visual radius
PROJECTILE_COLOR = (120, 60, 220)       # core color (purple magic)
PROJECTILE_GLOW_COLOR = (180, 120, 255) # outer glow

# ── Enemy personality base parameters ────────────────────
PERSONALITY_BERSERKER = {
    "attack_frequency": 1.6,   # multiplier on attack rate
    "dodge_probability": 0.05,
    "retreat_tendency": 0.05,
    "aggression": 0.95,
    "buff_use_chance": 0.1,
}
PERSONALITY_DUELIST = {
    "attack_frequency": 1.8,   # fast attack tempo
    "dodge_probability": 0.30,
    "retreat_tendency": 0.12,  # rarely retreats – prefers counter-play
    "aggression": 0.75,        # highly aggressive but controlled
    "buff_use_chance": 0.2,
}

# ── Duelist-specific tuning ───────────────────────────────
DUELIST_HP_MULT         = 0.75     # 75% of base HP (glass cannon)
DUELIST_DAMAGE_MULT     = 1.3      # 30% extra damage on all attacks
DUELIST_QUICK_COOLDOWN  = 300      # ms – faster than generic 500
DUELIST_HEAVY_COOLDOWN  = 700      # ms – faster than generic 1400
DUELIST_ATTACK_DURATION = 0.25     # seconds – snappier animation
DUELIST_THINK_INTERVAL  = 0.15     # seconds – faster decision cycle
DUELIST_COUNTER_WINDOW  = 0.45     # seconds – window to counter after blocking
DUELIST_COUNTER_DAMAGE  = 8        # flat damage for counter-strike
DUELIST_COMBO_WINDOW    = 0.20     # seconds – gap between combo hits
DUELIST_COMBO_DAMAGE    = 4        # flat damage for 2nd combo hit
DUELIST_LUNGE_IMPULSE   = 7.0      # forward impulse on attack
DUELIST_CHASE_SPEED_MULT = 1.45    # chase faster than other archetypes
PERSONALITY_COWARD = {
    "attack_frequency": 0.6,
    "dodge_probability": 0.50,
    "retreat_tendency": 0.70,
    "aggression": 0.20,
    "buff_use_chance": 0.5,
}
PERSONALITY_TRICKSTER = {
    "attack_frequency": 1.2,
    "dodge_probability": 0.40,
    "retreat_tendency": 0.50,
    "aggression": 0.60,
    "buff_use_chance": 0.7,
}
PERSONALITY_MAGE = {
    "attack_frequency": 0.7,
    "dodge_probability": 0.35,
    "retreat_tendency": 0.65,
    "aggression": 0.40,
    "buff_use_chance": 0.4,
    "uses_projectiles": True,
}

# ── PVP settings ──────────────────────────────────────────
PVP_P1_UP = "w"
PVP_P1_DOWN = "s"
PVP_P1_LEFT = "a"
PVP_P1_RIGHT = "d"
PVP_P1_ATTACK = "f"
PVP_P1_BLOCK = "g"
PVP_P1_DODGE = "h"

PVP_P2_UP = "up"
PVP_P2_DOWN = "down"
PVP_P2_LEFT = "left"
PVP_P2_RIGHT = "right"
PVP_P2_ATTACK = "kp1"         # numpad 1
PVP_P2_BLOCK = "kp2"          # numpad 2
PVP_P2_DODGE = "kp3"          # numpad 3

# ── VFX particles ─────────────────────────────────────────
PARTICLE_GRAVITY = 400.0       # pixels/s²
PARTICLE_MAX_COUNT = 300
BLOOD_PARTICLE_COUNT = 12
BLOOD_PARTICLE_SPEED = 180.0
TRAIL_SEGMENT_LIFETIME = 0.15
AURA_PARTICLE_COUNT = 20

# ── Health bar display ────────────────────────────────────
HEALTHBAR_WIDTH = 200
HEALTHBAR_HEIGHT = 18
HEALTHBAR_Y = 20
PLAYER_HB_X = 20
ENEMY_HB_X = SCREEN_WIDTH - HEALTHBAR_WIDTH - 20
STAMINABAR_HEIGHT = 8
STAMINABAR_Y = HEALTHBAR_Y + HEALTHBAR_HEIGHT + 4

# ── Font ──────────────────────────────────────────────────
FONT_SIZE = 22
SMALL_FONT_SIZE = 18

# ── Enemy regeneration ────────────────────────────────────
ENEMY_REGEN_INTERVAL   = 2500
ENEMY_REGEN_MIN_PCT    = 0.10
ENEMY_REGEN_MAX_PCT    = 0.20
ENEMY_REGEN_CAP_PCT    = 0.80
ENEMY_REGEN_IDLE_MS    = 2000
ENEMY_REGEN_FLASH_DUR  = 0.4
ENEMY_REGEN_TEXT_DUR   = 1.0
