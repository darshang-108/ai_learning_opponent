"""
audio_manager.py  –  Dynamic audio engine for AAA sensory polish.

Provides procedurally-generated sound effects using numpy waveform
synthesis, stereo positioning, volume ducking during slow-motion,
low-HP tension hum, ambient arena loop, and impact layering.

All playback is non-blocking via pygame.mixer channels.
No audio files required — everything is synthesised at startup.
If WAV files exist in ``assets/audio/`` they override procedural tones.
"""

from __future__ import annotations

import math
import os
from typing import Callable, Optional

import numpy as np
import pygame

from settings import SCREEN_WIDTH

# ─── Constants ────────────────────────────────────────────
_SAMPLE_RATE = 44100
_CHANNELS_MIX = 16        # pygame mixer channels to reserve
_BASE_VOLUME = 0.55        # master volume (0.0 – 1.0)
_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets", "audio")

# ─── Waveform helpers ────────────────────────────────────


def _sine(freq: float, dur: float, sr: int = _SAMPLE_RATE) -> np.ndarray:
    """Pure sine wave."""
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    return np.sin(2 * np.pi * freq * t)


def _square(freq: float, dur: float, sr: int = _SAMPLE_RATE) -> np.ndarray:
    """Square wave (sign of sine)."""
    return np.sign(_sine(freq, dur, sr))


def _noise(dur: float, sr: int = _SAMPLE_RATE) -> np.ndarray:
    """White noise burst."""
    return np.random.uniform(-1, 1, int(sr * dur))


def _fade_env(samples: np.ndarray, attack: float = 0.005,
              release: float = 0.05) -> np.ndarray:
    """Apply a linear attack/release envelope so clips don't pop."""
    n = len(samples)
    sr = _SAMPLE_RATE
    att = min(int(attack * sr), n // 2)
    rel = min(int(release * sr), n // 2)
    env = np.ones(n, dtype=np.float64)
    if att > 0:
        env[:att] = np.linspace(0, 1, att)
    if rel > 0:
        env[-rel:] = np.linspace(1, 0, rel)
    return samples * env


def _to_sound(samples: np.ndarray, volume: float = 0.45) -> pygame.mixer.Sound:
    """Convert a float64 numpy array to a pygame Sound (16-bit stereo)."""
    samples = np.clip(samples * volume, -1, 1)
    pcm = (samples * 32767).astype(np.int16)
    # Duplicate mono to stereo (interleaved L R L R ...)
    stereo = np.column_stack((pcm, pcm)).flatten()
    return pygame.mixer.Sound(buffer=stereo.tobytes())


# ─── Procedural sound definitions ────────────────────────


def _gen_light_hit() -> pygame.mixer.Sound:
    """Short punch click – snappy transient."""
    click = _noise(0.015) * 0.7
    body = _sine(300, 0.06) * 0.5
    tail = _sine(180, 0.04) * 0.3
    samples = np.concatenate([click, body, tail])
    return _to_sound(_fade_env(samples, 0.001, 0.03), 0.40)


def _gen_heavy_hit() -> pygame.mixer.Sound:
    """Deep bass impact – layered."""
    thud = _sine(55, 0.18) * 0.8
    crack = _noise(0.02) * 0.6
    mid = _sine(120, 0.10) * 0.4
    samples = np.concatenate([crack, thud])
    samples[:len(mid)] += mid
    return _to_sound(_fade_env(samples, 0.001, 0.06), 0.50)


def _gen_heavy_transient() -> pygame.mixer.Sound:
    """Sharp transient layer for heavy hits."""
    click = _noise(0.008) * 0.9
    ring = _sine(800, 0.03) * 0.3
    samples = np.concatenate([click, ring])
    return _to_sound(_fade_env(samples, 0.001, 0.02), 0.30)


def _gen_heavy_debris() -> pygame.mixer.Sound:
    """Tiny debris crunch for heavy hits."""
    crunch = _noise(0.06) * 0.3
    env = np.linspace(1, 0, len(crunch))
    samples = crunch * env
    return _to_sound(_fade_env(samples, 0.002, 0.03), 0.20)


def _gen_health_tick() -> pygame.mixer.Sound:
    """Sharp tick for health loss."""
    tick = _sine(1200, 0.04) * 0.6
    click = _noise(0.04) * 0.3
    samples = tick + click
    samples = _fade_env(samples, 0.001, 0.02)
    return _to_sound(samples, 0.30)


def _gen_combo_whoosh() -> pygame.mixer.Sound:
    """Rising whoosh for combo >= 3."""
    dur = 0.35
    t = np.linspace(0, dur, int(_SAMPLE_RATE * dur), endpoint=False)
    freq_sweep = np.sin(2 * np.pi * (200 + 600 * (t / dur)) * t) * 0.4
    noise_layer = _noise(dur) * 0.15
    samples = freq_sweep + noise_layer[:len(freq_sweep)]
    return _to_sound(_fade_env(samples, 0.02, 0.10), 0.35)


def _gen_dash() -> pygame.mixer.Sound:
    """Air whoosh for dash / fast movement."""
    dur = 0.15
    t = np.linspace(0, dur, int(_SAMPLE_RATE * dur), endpoint=False)
    sweep = _noise(dur) * 0.4
    env = np.exp(-t * 20)
    samples = sweep * env
    return _to_sound(_fade_env(samples, 0.005, 0.05), 0.25)


def _gen_pull_spell() -> pygame.mixer.Sound:
    """Low gravity hum."""
    dur = 0.40
    hum = _sine(80, dur) * 0.5 + _sine(120, dur) * 0.3
    return _to_sound(_fade_env(hum, 0.03, 0.10), 0.30)


def _gen_fireball() -> pygame.mixer.Sound:
    """Crackling burst."""
    crack = _noise(0.08) * 0.7
    body = _sine(200, 0.20) * 0.4
    sizzle = _noise(0.15) * np.linspace(0.4, 0, int(_SAMPLE_RATE * 0.15))
    samples = np.concatenate([crack, body])
    samples = np.concatenate([samples, sizzle])
    return _to_sound(_fade_env(samples, 0.002, 0.08), 0.40)


def _gen_regen_tick() -> pygame.mixer.Sound:
    """Soft green shimmer – high, pleasant tone."""
    dur = 0.25
    shimmer = _sine(880, dur) * 0.3 + _sine(1320, dur) * 0.15
    return _to_sound(_fade_env(shimmer, 0.03, 0.10), 0.20)


def _gen_enemy_death() -> pygame.mixer.Sound:
    """Dark descending fall tone."""
    dur = 0.50
    t = np.linspace(0, dur, int(_SAMPLE_RATE * dur), endpoint=False)
    freq = 300 - 250 * (t / dur)
    wave = np.sin(2 * np.pi * freq * t) * 0.5
    rumble = _sine(40, dur) * 0.3
    samples = wave + rumble
    return _to_sound(_fade_env(samples, 0.01, 0.15), 0.45)


def _gen_player_death() -> pygame.mixer.Sound:
    """Lower descending tone – heavier."""
    dur = 0.60
    t = np.linspace(0, dur, int(_SAMPLE_RATE * dur), endpoint=False)
    freq = 200 - 170 * (t / dur)
    wave = np.sin(2 * np.pi * freq * t) * 0.5
    sub = _sine(30, dur) * 0.4
    samples = wave + sub
    return _to_sound(_fade_env(samples, 0.01, 0.20), 0.50)


def _gen_victory() -> pygame.mixer.Sound:
    """Bright short flourish – ascending arpeggio feel."""
    notes = [523, 659, 784, 1047]  # C5 E5 G5 C6
    parts = []
    for f in notes:
        parts.append(_sine(f, 0.10) * 0.4)
    samples = np.concatenate(parts)
    return _to_sound(_fade_env(samples, 0.005, 0.08), 0.40)


def _gen_heartbeat() -> pygame.mixer.Sound:
    """Loopable low heartbeat bass – ~0.8 s loop."""
    dur = 0.80
    t = np.linspace(0, dur, int(_SAMPLE_RATE * dur), endpoint=False)
    # Double thump
    beat1_env = np.exp(-((t - 0.05) ** 2) / 0.002)
    beat2_env = np.exp(-((t - 0.25) ** 2) / 0.003)
    wave = (_sine(45, dur) * (beat1_env + beat2_env * 0.7))
    return _to_sound(_fade_env(wave, 0.01, 0.05), 0.35)


def _gen_ambient_loop() -> pygame.mixer.Sound:
    """Subtle low ambient drone – ~2 s loop."""
    dur = 2.0
    drone = _sine(55, dur) * 0.15 + _sine(82.5, dur) * 0.08
    # Gentle noise bed
    bed = _noise(dur) * 0.03
    samples = drone + bed
    return _to_sound(_fade_env(samples, 0.10, 0.10), 0.18)


def _gen_bass_drop() -> pygame.mixer.Sound:
    """Slow bass drop for death sequence."""
    dur = 0.70
    t = np.linspace(0, dur, int(_SAMPLE_RATE * dur), endpoint=False)
    freq = 120 - 100 * (t / dur)
    wave = np.sin(2 * np.pi * freq * t) * 0.6
    rumble = _sine(25, dur) * 0.4
    samples = wave + rumble
    return _to_sound(_fade_env(samples, 0.02, 0.20), 0.50)


# ─── Sound registry ──────────────────────────────────────

_SOUND_GENERATORS: dict[str, Callable[[], pygame.mixer.Sound]] = {
    "light_hit":        _gen_light_hit,
    "heavy_hit":        _gen_heavy_hit,
    "heavy_transient":  _gen_heavy_transient,
    "heavy_debris":     _gen_heavy_debris,
    "health_tick":      _gen_health_tick,
    "combo_whoosh":     _gen_combo_whoosh,
    "dash":             _gen_dash,
    "pull_spell":       _gen_pull_spell,
    "fireball":         _gen_fireball,
    "regen_tick":       _gen_regen_tick,
    "enemy_death":      _gen_enemy_death,
    "player_death":     _gen_player_death,
    "victory":          _gen_victory,
    "heartbeat":        _gen_heartbeat,
    "ambient_loop":     _gen_ambient_loop,
    "bass_drop":        _gen_bass_drop,
}


# ==============================================================
#  AudioManager
# ==============================================================

class AudioManager:
    """Central sound engine.

    * Preloads all sounds at startup (procedural or WAV files).
    * Non-blocking playback via dedicated mixer channels.
    * Volume ducking when time_scale < 1.0.
    * Stereo panning based on world X position.
    * Low-HP tension heartbeat loop.
    * Death-sequence orchestration.
    * Ambient arena loop.
    """

    def __init__(self):
        # Initialise mixer if not already done
        if not pygame.mixer.get_init():
            pygame.mixer.pre_init(
                frequency=_SAMPLE_RATE, size=-16, channels=2, buffer=512,
            )
            pygame.mixer.init()

        pygame.mixer.set_num_channels(_CHANNELS_MIX)

        # Preload all sounds
        self._sounds: dict[str, pygame.mixer.Sound] = {}
        self._preload()

        # Volume state
        self._base_volume = _BASE_VOLUME
        self._current_volume = _BASE_VOLUME
        self._time_scale = 1.0

        # Heartbeat (low-HP tension) state
        self._heartbeat_channel: Optional[pygame.mixer.Channel] = None
        self._heartbeat_active = False
        self._heartbeat_target_vol = 0.0

        # Ambient loop state
        self._ambient_channel: Optional[pygame.mixer.Channel] = None
        self._ambient_active = False

        # Death sequence state
        self._death_sequence_active = False
        self._death_sequence_timer = 0.0
        self._death_played_drop = False
        self._death_played_sting = False
        self._death_winner: str = ""

    # ── Preload ───────────────────────────────────────────

    def _preload(self):
        """Load all sounds – prefer WAV files, fall back to procedural."""
        for name, gen_fn in _SOUND_GENERATORS.items():
            wav_path = os.path.join(_ASSETS_DIR, f"{name}.wav")
            if os.path.isfile(wav_path):
                try:
                    self._sounds[name] = pygame.mixer.Sound(wav_path)
                    continue
                except Exception:
                    pass  # fall through to procedural
            # Procedural generation
            self._sounds[name] = gen_fn()

    # ── Core playback ─────────────────────────────────────

    def play_sfx(self, name: str, x_pos: Optional[float] = None,
                 volume_mult: float = 1.0):
        """Play a sound effect by name.

        Parameters
        ----------
        name        : key in the sound registry.
        x_pos       : world X position for stereo panning (None = centre).
        volume_mult : extra multiplier on top of ducked volume.
        """
        sound = self._sounds.get(name)
        if sound is None:
            return

        channel = pygame.mixer.find_channel()
        if channel is None:
            return  # all channels busy

        vol = self._current_volume * volume_mult

        if x_pos is not None:
            left, right = self._stereo_pan(x_pos)
            channel.set_volume(left * vol, right * vol)
        else:
            channel.set_volume(vol, vol)

        channel.play(sound)

    def play_layered(self, names: list[str], x_pos: Optional[float] = None,
                     volume_mult: float = 1.0):
        """Play multiple sounds simultaneously for impact layering."""
        for name in names:
            self.play_sfx(name, x_pos=x_pos, volume_mult=volume_mult)

    # ── Per-frame update ──────────────────────────────────

    def update(self, dt: float, time_scale: float,
               player_hp_frac: float = 1.0,
               match_active: bool = True):
        """Call once per frame.

        Parameters
        ----------
        dt             : real (un-scaled) delta time in seconds.
        time_scale     : current TimeScaleManager.scale value.
        player_hp_frac : player HP / max HP  (0.0 – 1.0).
        match_active   : False when match has ended.
        """
        self._time_scale = time_scale

        # ── Volume ducking during slow-motion ─────────────
        target_vol = self._base_volume
        if time_scale < 1.0:
            target_vol = self._base_volume * max(0.25, time_scale)
        # Smooth interpolation
        self._current_volume += (target_vol - self._current_volume) * 0.15

        # ── Low-HP heartbeat ──────────────────────────────
        self._update_heartbeat(player_hp_frac)

        # ── Ambient loop ──────────────────────────────────
        if match_active and not self._ambient_active:
            self._start_ambient()
        elif not match_active and self._ambient_active:
            self._stop_ambient()

        # ── Death sequence ────────────────────────────────
        if self._death_sequence_active:
            self._update_death_sequence(dt)

    # ── Stereo panning ────────────────────────────────────

    @staticmethod
    def _stereo_pan(x_pos: float) -> tuple[float, float]:
        """Compute (left, right) volume from world X position."""
        pan = max(0.0, min(1.0, x_pos / SCREEN_WIDTH))
        right = 0.3 + 0.7 * pan        # never fully silent on either side
        left = 0.3 + 0.7 * (1.0 - pan)
        return left, right

    # ── Heartbeat (low-HP tension) ────────────────────────

    def _update_heartbeat(self, hp_frac: float):
        """Start / stop / modulate the heartbeat loop."""
        if hp_frac < 0.30 and hp_frac > 0:
            # Louder as HP drops toward 0
            intensity = 1.0 - (hp_frac / 0.30)  # 0 at 30%, 1 at 0%
            self._heartbeat_target_vol = 0.15 + 0.35 * intensity

            if not self._heartbeat_active:
                self._start_heartbeat()

            # Smooth fade
            if self._heartbeat_channel is not None:
                cur = self._heartbeat_channel.get_volume()
                new_vol = cur + (self._heartbeat_target_vol - cur) * 0.08
                self._heartbeat_channel.set_volume(new_vol, new_vol)
        else:
            if self._heartbeat_active:
                self._stop_heartbeat()

    def _start_heartbeat(self):
        """Begin looping the heartbeat sound."""
        sound = self._sounds.get("heartbeat")
        if sound is None:
            return
        ch = pygame.mixer.find_channel()
        if ch is None:
            return
        ch.set_volume(0.0, 0.0)  # start silent, fade in
        ch.play(sound, loops=-1)
        self._heartbeat_channel = ch
        self._heartbeat_active = True

    def _stop_heartbeat(self):
        """Fade out and stop the heartbeat."""
        if self._heartbeat_channel is not None:
            self._heartbeat_channel.fadeout(400)
        self._heartbeat_channel = None
        self._heartbeat_active = False

    # ── Ambient arena loop ────────────────────────────────

    def _start_ambient(self):
        """Begin the subtle ambient drone."""
        sound = self._sounds.get("ambient_loop")
        if sound is None:
            return
        ch = pygame.mixer.find_channel()
        if ch is None:
            return
        vol = 0.10  # very subtle
        ch.set_volume(vol, vol)
        ch.play(sound, loops=-1)
        self._ambient_channel = ch
        self._ambient_active = True

    def _stop_ambient(self):
        """Fade out the ambient loop."""
        if self._ambient_channel is not None:
            self._ambient_channel.fadeout(600)
        self._ambient_channel = None
        self._ambient_active = False

    # ── Death sequence ────────────────────────────────────

    def trigger_death_sequence(self, winner: str = "player"):
        """Begin the cinematic death audio sequence.

        Parameters
        ----------
        winner : "player" or "enemy" — determines the sting sound.
        """
        if self._death_sequence_active:
            return  # prevent overlapping
        self._death_sequence_active = True
        self._death_sequence_timer = 0.0
        self._death_played_drop = False
        self._death_played_sting = False
        self._death_winner = winner

        # Silence ambient immediately
        self._stop_ambient()
        self._stop_heartbeat()

    def _update_death_sequence(self, dt: float):
        """Advance the death audio timeline."""
        self._death_sequence_timer += dt

        # Phase 1: bass drop at start
        if not self._death_played_drop and self._death_sequence_timer >= 0.0:
            self.play_sfx("bass_drop", volume_mult=1.0)
            self._death_played_drop = True

        # Phase 2: victory/death sting after freeze (at ~0.8 s)
        if not self._death_played_sting and self._death_sequence_timer >= 0.80:
            if self._death_winner == "player":
                self.play_sfx("enemy_death", volume_mult=0.8)
                self.play_sfx("victory", volume_mult=0.9)
            else:
                self.play_sfx("player_death", volume_mult=0.9)
            self._death_played_sting = True

        # Sequence complete after ~2 s
        if self._death_sequence_timer >= 2.0:
            self._death_sequence_active = False

    # ── Reset ─────────────────────────────────────────────

    def reset(self):
        """Stop all audio and reset state.  Call on match restart."""
        pygame.mixer.stop()
        self._heartbeat_active = False
        self._heartbeat_channel = None
        self._ambient_active = False
        self._ambient_channel = None
        self._death_sequence_active = False
        self._death_sequence_timer = 0.0
        self._death_played_drop = False
        self._death_played_sting = False
        self._current_volume = self._base_volume
