"""Generate ULTRON.ico from the official logo.

The shipped icon used the logo on a solid square, which reads as a dark box on the
Windows taskbar and triggers more heuristic scanner noise. This script crops the
logo's own artwork, adds transparency and writes a real multi-resolution ICO.

    python tools/make_icon.py            # writes ULTRON.ico in the package root
    python tools/make_icon.py --check    # only reports what the current icon is

No third-party dependency: PNG decoding is done here, so the build works on a bare
Python install (which is also what the installer's bootstrap guarantees).
"""
from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICON = ROOT / "ULTRON.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)

BACKGROUND = (28, 27, 33)
BACKGROUND_TOLERANCE = 26
# Keeps the thin red rim of the shield, which is close to the background colour.
RIM_RGB = (150, 20, 45)


# ---------------------------------------------------------------- PNG decoding
def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _decode_png(payload: bytes) -> tuple[int, int, list[list[tuple[int, int, int]]]]:
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not a PNG payload")
    pos, idat, width, height, depth, color = 8, b"", 0, 0, 0, 0
    while pos < len(payload):
        length = struct.unpack(">I", payload[pos:pos + 4])[0]
        kind = payload[pos + 4:pos + 8]
        data = payload[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, depth, color = struct.unpack(">IIBB", data[:10])
        elif kind == b"IDAT":
            idat += data
        elif kind == b"IEND":
            break
    if depth != 8 or color not in (2, 6):
        raise ValueError(f"unsupported PNG (depth={depth}, color={color})")
    channels = 3 if color == 2 else 4
    stride = width * channels
    raw = zlib.decompress(idat)
    previous = bytearray(stride)
    rows: list[list[tuple[int, int, int]]] = []
    pos = 0
    for _ in range(height):
        filter_type = raw[pos]
        pos += 1
        line = bytearray(raw[pos:pos + stride])
        pos += stride
        if filter_type == 1:
            for x in range(channels, stride):
                line[x] = (line[x] + line[x - channels]) & 0xFF
        elif filter_type == 2:
            for x in range(stride):
                line[x] = (line[x] + previous[x]) & 0xFF
        elif filter_type == 3:
            for x in range(stride):
                left = line[x - channels] if x >= channels else 0
                line[x] = (line[x] + ((left + previous[x]) >> 1)) & 0xFF
        elif filter_type == 4:
            for x in range(stride):
                left = line[x - channels] if x >= channels else 0
                upper = previous[x]
                corner = previous[x - channels] if x >= channels else 0
                line[x] = (line[x] + _paeth(left, upper, corner)) & 0xFF
        rows.append([tuple(line[i * channels:i * channels + 3]) for i in range(width)])
        previous = line
    return width, height, rows


def _decode_ico(payload: bytes) -> tuple[int, int, list[list[tuple[int, int, int]]]]:
    reserved, kind, count = struct.unpack("<HHH", payload[:6])
    if reserved != 0 or kind != 1:
        raise ValueError("not an ICO file")
    best = None
    offset = 6
    for _ in range(count):
        w, h, _colors, _res, _planes, _bpp, size, start = struct.unpack(
            "<BBBBHHII", payload[offset:offset + 16]
        )
        offset += 16
        w = w or 256
        if best is None or w > best[0]:
            best = (w, start, size)
    assert best is not None
    return _decode_png(payload[best[1]:best[1] + best[2]])


def _load(path: Path):
    payload = path.read_bytes()
    return _decode_png(payload) if payload.startswith(b"\x89PNG") else _decode_ico(payload)


# ---------------------------------------------------------------- PNG encoding
def _encode_png(width: int, height: int, pixels: list[list[tuple[int, int, int, int]]]) -> bytes:
    raw = bytearray()
    for row in pixels:
        raw.append(0)
        for r, g, b, a in row:
            raw += bytes((r, g, b, a))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


# ---------------------------------------------------------------- image work
def _background(pixels, width, height):
    return pixels[0][0] if pixels[0][0] else BACKGROUND


def _alpha_for(color, background) -> int:
    """Return 0..255 opacity for a logo pixel sampled over `background`."""
    distance = max(abs(color[i] - background[i]) for i in range(3))
    if distance >= BACKGROUND_TOLERANCE:
        return 255
    # The red rim is dark but must survive: keep it when the pixel leans red.
    if color[0] - max(color[1], color[2]) > 12 and color[0] > RIM_RGB[0] * 0.55:
        return 255
    return 0


def _crop_and_matte(pixels, width, height):
    background = _background(pixels, width, height)
    min_x, min_y, max_x, max_y = width, height, -1, -1
    for y in range(height):
        row = pixels[y]
        for x in range(width):
            if _alpha_for(row[x], background):
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
    if max_x < 0:
        raise ValueError("the logo could not be separated from its background")
    cropped = []
    for y in range(min_y, max_y + 1):
        line = []
        for x in range(min_x, max_x + 1):
            color = pixels[y][x]
            alpha = _alpha_for(color, background)
            if alpha:
                # Unmix the dark backdrop so the artwork keeps its own colours.
                mixed = []
                for i in range(3):
                    value = (color[i] - background[i] * (1 - alpha / 255)) / (alpha / 255)
                    mixed.append(max(0, min(255, round(value))))
                line.append((mixed[0], mixed[1], mixed[2], alpha))
            else:
                line.append((0, 0, 0, 0))
        cropped.append(line)
    return cropped


def _resize(pixels, width, height, target):
    """Box-filter downscale to a square canvas of `target` px, preserving aspect."""
    scale = min(target / width, target / height)
    out_w = max(1, round(width * scale))
    out_h = max(1, round(height * scale))
    pad_x = (target - out_w) // 2
    pad_y = (target - out_h) // 2
    canvas = [[(0, 0, 0, 0)] * target for _ in range(target)]
    for ty in range(out_h):
        y0 = ty * height / out_h
        y1 = (ty + 1) * height / out_h
        sy0, sy1 = int(y0), max(int(y0) + 1, int(y1 + 0.999))
        for tx in range(out_w):
            x0 = tx * width / out_w
            x1 = (tx + 1) * width / out_w
            sx0, sx1 = int(x0), max(int(x0) + 1, int(x1 + 0.999))
            acc = [0.0, 0.0, 0.0, 0.0]
            count = 0
            for sy in range(sy0, min(sy1, height)):
                row = pixels[sy]
                for sx in range(sx0, min(sx1, width)):
                    r, g, b, a = row[sx]
                    weight = a / 255
                    acc[0] += r * weight
                    acc[1] += g * weight
                    acc[2] += b * weight
                    acc[3] += a
                    count += 1
            if count == 0:
                continue
            alpha = acc[3] / count
            if alpha <= 0:
                continue
            weight_sum = acc[3] / 255 or 1
            canvas[pad_y + ty][pad_x + tx] = (
                round(acc[0] / weight_sum), round(acc[1] / weight_sum),
                round(acc[2] / weight_sum), round(alpha),
            )
    return canvas


def _write_ico(path: Path, frames: list[tuple[int, bytes]]) -> None:
    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = 6 + 16 * len(frames)
    directory = b""
    for size, payload in frames:
        directory += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(payload), offset)
        offset += len(payload)
    path.write_bytes(header + directory + b"".join(payload for _, payload in frames))


def build() -> None:
    source = ICON if ICON.exists() else ROOT / "electron" / "assets" / "ULTRON.ico"
    width, height, pixels = _load(source)
    artwork = _crop_and_matte(pixels, width, height)
    art_w = len(artwork[0])
    art_h = len(artwork)
    frames = []
    for size in SIZES:
        scaled = _resize(artwork, art_w, art_h, size)
        frames.append((size, _encode_png(size, size, scaled)))
    _write_ico(ICON, frames)
    asset = ROOT / "electron" / "assets" / "ULTRON.ico"
    if asset.parent.is_dir() and asset.resolve() != ICON.resolve():
        _write_ico(asset, frames)
    print(f"ULTRON.ico gerado com {len(frames)} tamanhos "
          f"({', '.join(str(s) for s in SIZES)}); arte {art_w}x{art_h} recortada.")


def check() -> int:
    if not ICON.exists():
        print("ULTRON.ico ausente.", file=sys.stderr)
        return 1
    payload = ICON.read_bytes()
    reserved, kind, count = struct.unpack("<HHH", payload[:6])
    problems = []
    if (reserved, kind) != (0, 1):
        problems.append("cabeçalho ICO inválido")
    offset = 6
    sizes = []
    for _ in range(count):
        w, h, _c, _r, _p, bpp, _s, _o = struct.unpack("<BBBBHHII", payload[offset:offset + 16])
        offset += 16
        sizes.append(w or 256)
        if bpp not in (32, 0):
            problems.append(f"entrada {w or 256}px com {bpp} bits")
    if 256 not in sizes:
        problems.append("falta a entrada de 256px")
    if 32 not in sizes:
        problems.append("falta a entrada de 32px")
    if problems:
        print("ICONE COM PROBLEMAS: " + "; ".join(problems), file=sys.stderr)
        return 1
    print(f"Ícone ok: {count} tamanhos ({', '.join(map(str, sizes))}).")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="apenas valida o ícone atual")
    arguments = parser.parse_args()
    raise SystemExit(check() if arguments.check else (build() or 0))
