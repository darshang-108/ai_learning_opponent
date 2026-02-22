"""
stamina_system.py – Stamina resource management for all characters.

Rules:
- Attacking drains stamina
- Dodging drains stamina
- Blocking drains stamina over time
- Stamina regenerates when not acting
- AI adapts if player stamina is low
"""

from __future__ import annotations

from settings import (
    STAMINA_MAX, STAMINA_REGEN_RATE, STAMINA_REGEN_DELAY,
    STAMINA_ATTACK_COST, STAMINA_DODGE_COST,
    STAMINA_BLOCK_COST_PER_SEC, STAMINA_HEAVY_ATTACK_COST,
    STAMINA_LOW_THRESHOLD,
)


class StaminaComponent:
    """Per-character stamina tracker.

    Attach to any Character instance. Call ``update(dt)`` each frame.
    """

    def __init__(self, max_stamina: float = STAMINA_MAX):
        self.max_stamina = max_stamina
        self.stamina = max_stamina
        self.regen_rate = STAMINA_REGEN_RATE
        self.regen_delay = STAMINA_REGEN_DELAY
        self._time_since_action = 999.0   # seconds

    # ── Queries ───────────────────────────────────────────

    @property
    def fraction(self) -> float:
        return self.stamina / max(1.0, self.max_stamina)

    @property
    def is_low(self) -> bool:
        return self.fraction < STAMINA_LOW_THRESHOLD

    @property
    def is_empty(self) -> bool:
        return self.stamina <= 0.0

    def has_enough(self, cost: float) -> bool:
        return self.stamina >= cost

    # ── Modifiers ─────────────────────────────────────────

    def drain(self, amount: float) -> bool:
        """Drain stamina. Returns False if not enough."""
        if self.stamina < amount:
            return False
        self.stamina = max(0.0, self.stamina - amount)
        self._time_since_action = 0.0
        return True

    def drain_attack(self) -> bool:
        return self.drain(STAMINA_ATTACK_COST)

    def drain_heavy_attack(self) -> bool:
        return self.drain(STAMINA_HEAVY_ATTACK_COST)

    def drain_dodge(self) -> bool:
        return self.drain(STAMINA_DODGE_COST)

    def drain_block(self, dt: float) -> bool:
        """Drain stamina for blocking. Returns False when empty."""
        cost = STAMINA_BLOCK_COST_PER_SEC * dt
        self.stamina = max(0.0, self.stamina - cost)
        self._time_since_action = 0.0
        return self.stamina > 0

    def restore(self, amount: float):
        self.stamina = min(self.max_stamina, self.stamina + amount)

    def reset(self):
        self.stamina = self.max_stamina
        self._time_since_action = 999.0

    # ── Per-frame ─────────────────────────────────────────

    def update(self, dt: float, is_acting: bool = False):
        """Regenerate stamina when not acting.

        Parameters
        ----------
        dt        : delta time in seconds
        is_acting : True if the character is attacking/blocking/dodging
        """
        if is_acting:
            self._time_since_action = 0.0
        else:
            self._time_since_action += dt

        # Regen after delay
        if self._time_since_action >= self.regen_delay:
            self.stamina = min(
                self.max_stamina,
                self.stamina + self.regen_rate * dt,
            )


class StaminaSystem:
    """System-level manager that updates stamina for a list of characters."""

    @staticmethod
    def update(character, dt: float):
        """Update one character's stamina component."""
        if not hasattr(character, "stamina_component"):
            return
        comp: StaminaComponent = character.stamina_component
        is_acting = (
            character.is_attacking
            or character.is_blocking
            or character.is_dodging
        )
        comp.update(dt, is_acting)

        # Sync display value
        character.stamina = comp.stamina
        character.max_stamina = comp.max_stamina

        # Auto-release block when stamina empty
        if character.is_blocking and comp.is_empty:
            character.stop_block()
