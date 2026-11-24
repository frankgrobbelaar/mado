"""Made-up scenes with known depth, drawn by code for the depth tools' tests and measurements:
never a real photo. Each comes with its truth: how near each pixel is, as the depth model says
it (0 for the sky, far away, up to 1 for the nearest thing), so a test knows what's in front.

The ground is a flat field seen from a little above it, so its nearness grows straight down the
picture from the horizon (as a camera sees a flat ground); posts and a ball stand on it, each as
near as the ground where it stands, and the ball, the subject, is the nearest thing."""

import numpy as np
import numpy.typing as npt
from PIL import Image, ImageDraw

type Floats = npt.NDArray[np.float32]

HORIZON = 0.42  # the horizon, as a fraction of the picture's height
HILLS = 0.06  # how near the far hills are: a little nearer than the sky


def field(
    size: tuple[int, int] = (1200, 900),
    *,
    ball: bool = True,
    ball_at: tuple[float, float] = (0.62, 0.86),
    grain: float = 2.0,
    seed: int = 4,
) -> tuple[Image.Image, Floats]:
    """A field under a sky with a sun, far hills, a row of posts going away and a red ball near
    the camera (`ball_at`: where it rests, as fractions across and down); and its truth."""
    width, height = size
    rng = np.random.default_rng(seed)
    horizon = int(height * HORIZON)
    rows = np.arange(height, dtype=np.float32)[:, None]
    near = np.zeros((height, width), np.float32)
    ground = np.clip((rows - horizon) / (height - horizon), 0, 1)
    near[:] = np.where(rows >= horizon, 0.1 + 0.85 * ground, 0.0)

    # The sky, pale at the horizon, and the ground's furrows, closer together far away.
    sky_top, sky_low = np.array([96, 150, 222], np.float32), np.array([205, 226, 245], np.float32)
    fade = np.clip(rows / max(horizon, 1), 0, 1)[..., None]
    pixels = np.broadcast_to(sky_top * (1 - fade) + sky_low * fade, (height, width, 3)).copy()
    depth_row = np.maximum(rows - horizon, 1.0)
    furrow = 0.5 + 0.5 * np.sin(np.log(depth_row) * 18.0)
    grass = np.array([78, 128, 58], np.float32) * (0.82 + 0.18 * furrow)[..., None]
    grass = grass * (0.75 + 0.25 * ground[..., None])
    below = (rows >= horizon)[..., None]
    pixels = np.where(below, np.broadcast_to(grass, (height, width, 3)), pixels)
    image = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))
    paint = ImageDraw.Draw(image)
    truth = Image.fromarray(near, "F")
    mark = ImageDraw.Draw(truth)

    # The sun, and far hills along the horizon.
    sun = width * 0.05
    paint.ellipse(
        [width * 0.2 - sun, height * 0.14 - sun, width * 0.2 + sun, height * 0.14 + sun],
        fill=(255, 238, 190),
    )
    across = np.linspace(0, 1, 90)
    ridge = HORIZON - 0.06 - 0.03 * np.sin(across * 7.0 + 1.0) - 0.02 * np.sin(across * 17.0)
    hill = [(float(a * width), float(r * height)) for a, r in zip(across, ridge, strict=True)]
    outline = [(0, horizon + 1), *hill, (width, horizon + 1)]
    paint.polygon(outline, fill=(104, 128, 150))
    mark.polygon(outline, fill=HILLS)

    # Posts going away along the field, each as near as the ground where it stands.
    for step in range(7):
        base = horizon + (height - horizon) * (0.08 + 0.12 * step)
        at = ground_near(base, height)
        x = width * (0.08 + 0.11 * step)
        tall = (height - horizon) * (0.12 + 0.5 * at)
        wide = max(2.0, width * 0.004 * (1 + 6 * at))
        box = [x - wide, base - tall, x + wide, base]
        paint.rectangle(box, fill=(92, 64, 40))
        mark.rectangle(box, fill=float(at))

    if ball:
        bx, by = ball_at[0] * width, ball_at[1] * height
        radius = height * 0.11
        at = ground_near(by, height)
        box = [bx - radius, by - 2 * radius, bx + radius, by]
        mark.ellipse(box, fill=float(min(at + 0.04, 1.0)))
        # Shaded as a ball is, lit from the top left.
        ys, xs = np.mgrid[0 : int(2 * radius), 0 : int(2 * radius)].astype(np.float32)
        u, v = (xs - radius) / radius, (ys - radius) / radius
        inside = u * u + v * v <= 1.0
        light = np.clip(1.0 - 0.55 * np.hypot(u + 0.4, v + 0.45), 0.25, 1.0)
        red = np.stack([215 * light, 40 * light, 36 * light], axis=-1)
        spot = Image.fromarray(np.clip(red, 0, 255).astype(np.uint8))
        image.paste(
            spot, (int(box[0]), int(box[1])), Image.fromarray(inside.astype(np.uint8) * 255)
        )

    if grain > 0:
        noisy = np.asarray(image, np.float32) + rng.normal(0, grain, (height, width, 1))
        image = Image.fromarray(np.clip(noisy, 0, 255).astype(np.uint8))
    return image, np.asarray(truth, np.float32)


def ground_near(row: float, height: int) -> float:
    """How near the field is at `row` (pixels down): 0.1 at the horizon, 0.95 at the foot."""
    horizon = height * HORIZON
    return float(0.1 + 0.85 * np.clip((row - horizon) / (height - horizon), 0, 1))


def scan(size: tuple[int, int] = (1200, 1600), *, seed: int = 2) -> Image.Image:
    """A made-up scan of a page: paper with rows of dark marks where words would be, flat."""
    width, height = size
    rng = np.random.default_rng(seed)
    image = Image.new("RGB", size, (246, 243, 236))
    paint = ImageDraw.Draw(image)
    for top in range(int(height * 0.08), int(height * 0.92), max(8, height // 40)):
        left = int(width * 0.1)
        while left < width * 0.88:
            word = int(rng.integers(width // 40, width // 12))
            paint.rectangle(
                [left, top, left + word, top + max(3, height // 120)], fill=(40, 40, 46)
            )
            left += word + width // 60
    noisy = np.asarray(image, np.float32) + rng.normal(0, 1.5, (height, width, 1))
    return Image.fromarray(np.clip(noisy, 0, 255).astype(np.uint8))


def layers(
    size: tuple[int, int] = (960, 540), shift: float = 0.0, *, post: bool = True
) -> tuple[Image.Image, Floats, npt.NDArray[np.bool_]]:
    """Three flat layers at known depths, for the 3D photo: a far wall of stripes (0.1), a middle
    board of squares (0.5) and a near post (0.9). `shift` moves the view to the right by that
    many pixels at nearness 1 (each layer by its nearness times it), as a camera moving would:
    the scene as it'd truly look from there, for comparing what a 3D photo fills in; without the
    post (`post` false), what's truly behind it. Also where the post covers what's behind it."""
    width, height = size
    xs = np.arange(width, dtype=np.float32)[None, :]
    ys = np.arange(height, dtype=np.float32)[:, None]

    def wall(x: Floats) -> Floats:
        stripe = 0.5 + 0.5 * np.sin(x / 9.0) * np.cos(ys / 23.0)
        return np.stack(
            [70 + 90 * stripe, 110 + 60 * stripe, 160 + 50 * (1 - stripe)], axis=-1
        ).astype(np.float32)

    def board(x: Floats) -> Floats:
        squares = ((x // 24 + ys // 24) % 2).astype(np.float32)
        return np.stack([200 - 80 * squares, 170 - 40 * squares, 90 + 30 * squares], axis=-1)

    far = wall(np.broadcast_to(xs - 0.1 * shift, (height, width)))
    middle_x = xs - 0.5 * shift
    on_board = (middle_x > width * 0.15) & (middle_x < width * 0.75) & (ys > height * 0.25)
    mid = board(np.broadcast_to(middle_x, (height, width)))
    post_x = xs - 0.9 * shift
    on_post = (np.abs(post_x - width * 0.55) < width * 0.05) & (ys > height * 0.08) & post
    near = np.full((height, width), 0.1, np.float32)
    pixels = far
    pixels = np.where(on_board[..., None], mid, pixels)
    near = np.where(on_board, 0.5, near)
    red = np.broadcast_to(np.array([150, 52, 44], np.float32), (height, width, 3))
    pixels = np.where(on_post[..., None], red, pixels)
    near = np.where(on_post, 0.9, near).astype(np.float32)
    image = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))
    return image, near, np.broadcast_to(on_post, (height, width)).copy()
