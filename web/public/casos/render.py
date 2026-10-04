"""Draw the eight Quipu statement cards once. Pillow is not an app dependency.

    uv run --with pillow python web/public/casos/render.py
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# N = 8 demo cards, each a fixed list of rows. Drawn once and committed.
OUT = Path(__file__).parent
W, PAD = 880, 40
ABYSS = (4, 20, 26)
MIST = (230, 244, 241)
FOG = (157, 184, 181)
TEAL = (46, 196, 182)
AMBER = (242, 194, 122)
HAIR = (26, 58, 66)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    name = "Arial Bold.ttf" if bold else "Arial.ttf"
    for path in (
        Path("/System/Library/Fonts/Supplemental") / name,
        Path("/Library/Fonts") / name,
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    ):
        if path.exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def logo(draw: ImageDraw.ImageDraw, ox: float, oy: float, scale: float = 2.2) -> None:
    """The Quipu mark: a ring and 12 rays with knots, from web/components/logo.tsx."""

    def pt(x: float, y: float) -> tuple[float, float]:
        return (ox + x * scale, oy + y * scale)

    cx, cy = pt(16, 16)
    radius = 5.5 * scale
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=MIST, width=3)
    for k in range(12):
        angle = math.radians(k * 30)
        cosine, sine = math.cos(angle), math.sin(angle)
        reach = 14 if k % 2 == 0 else 12
        draw.line(
            [pt(16 + cosine * 8.6, 16 + sine * 8.6), pt(16 + cosine * reach, 16 + sine * reach)],
            fill=TEAL,
            width=2,
        )
        knot = pt(16 + cosine * 11, 16 + sine * 11)
        dot = 1.7 * scale
        draw.ellipse((knot[0] - dot, knot[1] - dot, knot[0] + dot, knot[1] + dot), fill=TEAL)


def card(name: str, title: str, last4: str, rows: list[tuple[str, str, str, str | None]]) -> None:
    row_h, header = 96, 118
    image = Image.new("RGB", (W, PAD + header + len(rows) * row_h + 16), ABYSS)
    draw = ImageDraw.Draw(image)
    logo(draw, PAD, 28)
    draw.text((PAD + 86, 36), "Quipu", font=font(28, bold=True), fill=MIST)
    draw.text((PAD + 86, 72), title, font=font(20), fill=FOG)
    label = f"Tarjeta  •••• {last4}"
    draw.text((W - PAD - draw.textlength(label, font=font(15)), 74), label, font=font(15), fill=FOG)
    y = PAD + header
    draw.line((PAD, y - 18, W - PAD, y - 18), fill=HAIR, width=2)
    merchant_font, amount_font, small = font(22, bold=True), font(22, bold=True), font(15)
    for index, (merchant, when, amount, status) in enumerate(rows):
        draw.text((PAD, y), merchant, font=merchant_font, fill=MIST)
        draw.text((PAD, y + 36), when, font=small, fill=FOG)
        color = AMBER if status else MIST
        amount_width = draw.textlength(amount, font=amount_font)
        draw.text((W - PAD - amount_width, y), amount, font=amount_font, fill=color)
        if status:
            status_width = draw.textlength(status, font=small)
            draw.text((W - PAD - status_width, y + 36), status, font=small, fill=AMBER)
        y += row_h
        if index < len(rows) - 1:
            draw.line((PAD, y - 16, W - PAD, y - 16), fill=HAIR, width=1)
    image.save(OUT / name, "PNG")


# Amounts, times and statuses are the fixture rows (data_pipeline/fixtures.py), newest first.
CASES = [
    (
        "lucia-uber.png",
        "Movimientos",
        "4821",
        [
            ("Uber Trip", "11 jun 2026  ·  09:00:04", "312.40 MXN", None),
            ("Uber Trip", "11 jun 2026  ·  09:00:00", "312.40 MXN", None),
        ],
    ),
    (
        "mariana-bestbuy.png",
        "Movimientos",
        "1937",
        [("Best Buy US", "14 jun 2026  ·  12:00:00  ·  Austin, USA", "1,043.00 MXN", None)],
    ),
    (
        "andres-amazon.png",
        "Movimientos",
        "5502",
        [
            (
                "Amazon Mktp",
                "17 jun 2026  ·  12:00:00  ·  Seattle, USA",
                "148,900.00 COP",
                "Pendiente",
            ),
        ],
    ),
    (
        "ana-ifood.png",
        "Movimentos",
        "7740",
        [
            ("iFood", "15 jun 2026  ·  10:00:06", "27.90 USD", None),
            ("iFood", "15 jun 2026  ·  10:00:00", "27.90 USD", None),
        ],
    ),
    (
        "martina-electromax.png",
        "Movimientos",
        "2208",
        [
            ("ElectroMax Córdoba", "18 jun 2026  ·  11:00:00  ·  Córdoba", "161,700.00 ARS", None),
            ("ElectroMax Córdoba", "18 jun 2026  ·  10:30:00  ·  Córdoba", "161,700.00 ARS", None),
            ("ElectroMax Córdoba", "18 jun 2026  ·  10:00:00  ·  Córdoba", "161,700.00 ARS", None),
        ],
    ),
    (
        "camilo-dia.png",
        "Movimientos",
        "6614",
        [
            ("Amazon Mktp", "17 jun 2026  ·  18:00:00", "149,900.00 COP", None),
            ("Uber Trip", "17 jun 2026  ·  15:00:00", "18,300.00 COP", None),
            ("Éxito", "17 jun 2026  ·  12:00:00", "131,500.00 COP", None),
            ("Rappi", "17 jun 2026  ·  09:00:00", "42,000.00 COP", None),
        ],
    ),
    (
        "diego-liverpool.png",
        "Movimientos",
        "3085",
        [("Liverpool", "16 jun 2026  ·  07:00:00  ·  App", "2,899.00 MXN", None)],
    ),
    (
        "sofia-mercadolibre.png",
        "Movimientos",
        "9146",
        [("Mercado Libre", "13 jun 2026  ·  12:00:00", "54,000.00 ARS", "Reversado")],
    ),
]


if __name__ == "__main__":
    for name, title, last4, rows in CASES:
        card(name, title, last4, rows)
        print(name)
