"""
avatar_generator.py  –  Procedural Low-Poly Face Avatar Generator.

Uses Delaunay triangulation on edge-detected keypoints to convert
any user-supplied image into a stylised low-poly face surface that
can be composited onto the player character.

Pipeline:
    1. Load & resize  →  2. Canny edges  →  3. Keypoint sampling
    4. Delaunay triangulation  →  5. Triangle avg-color fill
    6. Convert to circular Pygame surface

Dependencies: opencv-python, numpy, scipy, pygame
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)
from typing import TYPE_CHECKING

import pygame

# Provide type-checker-only imports so Pyright always sees the names bound.
if TYPE_CHECKING:
    import cv2
    import numpy as np
    from scipy.spatial import Delaunay

# Heavy deps imported lazily — game still works if not installed
try:
    import cv2
    import numpy as np
    from scipy.spatial import Delaunay
    _HAS_DEPS = True
except ImportError as _exc:
    _HAS_DEPS = False
    _MISSING_MSG = str(_exc)

# ── Cache directory for generated avatars ─────────────────
_CACHE_DIR = Path(__file__).resolve().parent / ".avatar_cache"

# ── Tunables ──────────────────────────────────────────────
_MAX_PROCESS_SIZE = 256        # resize longest edge before processing
_EDGE_SAMPLE_STEP = 8          # take every Nth edge pixel
_RANDOM_INTERIOR_PTS = 80      # random points inside image
_CANNY_LOW = 80
_CANNY_HIGH = 180
_BLUR_KERNEL = (5, 5)


# ==============================================================
#  Public API
# ==============================================================

class PolyFaceGenerator:
    """Convert an image file into a low-poly Pygame surface.

    Usage::

        gen = PolyFaceGenerator("photo.jpg", output_size=64)
        surface = gen.generate()   # pygame.Surface | None
    """

    def __init__(self, image_path: str, output_size: int = 128):
        self.image_path = image_path
        self.output_size = output_size

    # ----------------------------------------------------------
    def generate(self) -> pygame.Surface | None:
        """Run the full pipeline.  Returns a circular Pygame surface
        ready for blitting, or *None* on any failure."""
        if not _HAS_DEPS:
            logger.warning("Missing dependency: %s", _MISSING_MSG)
            logger.warning("Install with: pip install opencv-python numpy scipy")
            return None
        try:
            img = self._load_image()
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            edges = self._detect_edges(gray)
            points = self._sample_keypoints(edges, img.shape[:2])
            tri = Delaunay(points)
            poly_img = self._fill_triangles(img, points, tri)
            surface = self._to_pygame_surface(poly_img)
            return surface
        except Exception as exc:
            logger.error("Avatar generation failed: %s", exc)
            return None

    # ----------------------------------------------------------
    #  Step 1 – Load & resize
    # ----------------------------------------------------------
    def _load_image(self) -> np.ndarray:
        raw = cv2.imread(self.image_path, cv2.IMREAD_COLOR)
        if raw is None:
            raise FileNotFoundError(
                f"Could not read image: {self.image_path}"
            )
        # BGR → RGB
        img = cv2.cvtColor(raw, cv2.COLOR_BGR2RGB)

        # Resize so longest edge ≤ _MAX_PROCESS_SIZE
        h, w = img.shape[:2]
        scale = _MAX_PROCESS_SIZE / max(h, w)
        if scale < 1.0:
            new_w, new_h = int(w * scale), int(h * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

        # Make square by centre-cropping
        h, w = img.shape[:2]
        side = min(h, w)
        y0 = (h - side) // 2
        x0 = (w - side) // 2
        img = img[y0:y0 + side, x0:x0 + side]

        return img

    # ----------------------------------------------------------
    #  Step 2 – Edge detection
    # ----------------------------------------------------------
    @staticmethod
    def _detect_edges(gray: np.ndarray) -> np.ndarray:
        blurred = cv2.GaussianBlur(gray, _BLUR_KERNEL, 0)
        edges = cv2.Canny(blurred, _CANNY_LOW, _CANNY_HIGH)
        return edges

    # ----------------------------------------------------------
    #  Step 3 – Keypoint sampling
    # ----------------------------------------------------------
    @staticmethod
    def _sample_keypoints(edges: np.ndarray,
                          shape: tuple[int, int]) -> np.ndarray:
        h, w = shape

        # Edge pixels (sparse)
        ey, ex = np.where(edges > 0)
        if len(ex) > 0:
            step = max(1, _EDGE_SAMPLE_STEP)
            idx = np.arange(0, len(ex), step)
            edge_pts = np.column_stack((ex[idx], ey[idx]))
        else:
            edge_pts = np.empty((0, 2), dtype=np.int32)

        # Random interior points
        rx = np.random.randint(0, w, size=_RANDOM_INTERIOR_PTS)
        ry = np.random.randint(0, h, size=_RANDOM_INTERIOR_PTS)
        rand_pts = np.column_stack((rx, ry))

        # Four corners + mid-edges (ensure hull coverage)
        border_pts = np.array([
            [0, 0], [w - 1, 0], [0, h - 1], [w - 1, h - 1],
            [w // 2, 0], [w // 2, h - 1],
            [0, h // 2], [w - 1, h // 2],
        ])

        points = np.vstack([edge_pts, rand_pts, border_pts])
        return points.astype(np.float64)

    # ----------------------------------------------------------
    #  Step 4 + 5 – Triangle fill with average colour
    # ----------------------------------------------------------
    @staticmethod
    def _fill_triangles(img: np.ndarray,
                        points: np.ndarray,
                        tri: Delaunay) -> np.ndarray:
        h, w = img.shape[:2]
        output = np.zeros_like(img)

        for simplex in tri.simplices:
            pts = points[simplex].astype(np.int32)

            # Bounding-box clip
            xs, ys = pts[:, 0], pts[:, 1]
            x_min, x_max = max(int(xs.min()), 0), min(int(xs.max()), w - 1)
            y_min, y_max = max(int(ys.min()), 0), min(int(ys.max()), h - 1)
            if x_min >= x_max or y_min >= y_max:
                continue

            # Mask for the triangle
            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.fillConvexPoly(mask, pts.reshape(-1, 1, 2), 255)

            # Average colour inside triangle
            mean_color = cv2.mean(img, mask=mask)[:3]
            color = tuple(int(c) for c in mean_color)

            # Draw filled triangle onto output
            cv2.fillConvexPoly(output, pts.reshape(-1, 1, 2), color)

        return output

    # ----------------------------------------------------------
    #  Step 6 – Convert to circular Pygame surface
    # ----------------------------------------------------------
    def _to_pygame_surface(self, img: np.ndarray) -> pygame.Surface:
        size = self.output_size

        # Resize to output_size × output_size
        img = cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)

        # NumPy RGB → Pygame surface
        surf = pygame.surfarray.make_surface(
            np.transpose(img, (1, 0, 2))  # HWC → WHC for pygame
        )

        # Circular mask with SRCALPHA
        final = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(
            final, (255, 255, 255, 255),
            (size // 2, size // 2), size // 2,
        )
        # Use the circle as mask: blit surf then apply per-pixel alpha
        mask_surf = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(
            mask_surf, (255, 255, 255, 255),
            (size // 2, size // 2), size // 2,
        )
        # Composite: keep only pixels inside the circle
        final.blit(surf, (0, 0))
        final.blit(mask_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

        # Thin white outline for polish
        pygame.draw.circle(
            final, (255, 255, 255, 200),
            (size // 2, size // 2), size // 2, 2,
        )

        return final


# ==============================================================
#  Convenience helpers
# ==============================================================

def generate_avatar(image_path: str,
                    output_size: int = 64) -> pygame.Surface | None:
    """One-shot helper.  Returns ready surface or None."""
    return PolyFaceGenerator(image_path, output_size).generate()


def load_cached_avatar(output_size: int = 64) -> pygame.Surface | None:
    """Load a previously cached avatar PNG, if it exists."""
    path = _CACHE_DIR / "avatar.png"
    if not path.exists():
        return None
    try:
        surf = pygame.image.load(str(path))
        # convert_alpha requires a display surface; fall back gracefully
        try:
            surf = surf.convert_alpha()
        except pygame.error:
            pass
        return pygame.transform.smoothscale(surf, (output_size, output_size))
    except Exception:
        return None


def cache_avatar(surface: pygame.Surface) -> None:
    """Save a generated avatar surface to disk for reuse."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _CACHE_DIR / "avatar.png"
    pygame.image.save(surface, str(path))
    logger.info("Cached avatar → %s", path)


def pick_image_file() -> str | None:
    """Open a native file dialog to select an image.

    Uses tkinter (bundled with CPython) so no extra deps needed.
    Returns the file path as a string, or None if cancelled.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()            # hide the root window
        root.attributes("-topmost", True)
        file_path = filedialog.askopenfilename(
            title="Select a face image",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.bmp *.webp"),
                ("All files", "*.*"),
            ],
        )
        root.destroy()
        return file_path if file_path else None
    except Exception as exc:
        logger.error("File dialog error: %s", exc)
        return None


def cleanup_original(image_path: str) -> None:
    """Delete the source image after processing (privacy)."""
    try:
        os.remove(image_path)
        logger.info("Deleted original: %s", image_path)
    except OSError:
        pass
