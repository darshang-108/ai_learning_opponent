"""helpers.py - Reusable utility functions."""

import pygame
from settings import WHITE, SCREEN_WIDTH, SCREEN_HEIGHT, FONT_SIZE


def draw_text(surface, text, x, y, color=WHITE, size=FONT_SIZE):
    """Render a single line of text at (x, y)."""
    font = pygame.font.SysFont(None, size)
    rendered = font.render(text, True, color)
    surface.blit(rendered, (x, y))


def draw_end_screen(surface, message):
    """Fill the screen with a dark overlay and show a large
    win/loss message plus a restart hint."""
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
    overlay.set_alpha(180)
    overlay.fill((0, 0, 0))
    surface.blit(overlay, (0, 0))

    # Main message
    big_font = pygame.font.SysFont(None, 72)
    text = big_font.render(message, True, WHITE)
    rect = text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 30))
    surface.blit(text, rect)

    # Hint
    small_font = pygame.font.SysFont(None, 30)
    hint = small_font.render("Press R to Restart  |  ESC for Menu", True, WHITE)
    hint_rect = hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 40))
    surface.blit(hint, hint_rect)
