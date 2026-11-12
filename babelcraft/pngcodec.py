"""Códec PNG sin dependencias (solo zlib + struct).

Portado del lector de `CobblemonBedrock/tools/cobblemon2bedrock.js` (código
propio del autor de este proyecto), que ya soporta todos los formatos que
traen los mods reales: RGBA, RGB, escala de grises, paleta de 1/2/4/8 bits
con tRNS y bit depth 16. Sin esto, las texturas de paleta (muy comunes en
arte pixel) se pasan sin leer: mal color de huevo, sin detectar
transparencia y sin poder reducirse.

Qué hace falta de aquí:
  - decode: PNG -> píxeles RGBA (para estadísticas, atlas y reducción)
  - encode: RGBA -> PNG (para placeholders, iconos de pack y atlas)
  - downscale: reducción por vecino más próximo (conserva pixel art)
  - texture_stats: color medio de los píxeles opacos (color de huevo de
    invocación, map_color de bloque) y presencia de alfa parcial
"""

from __future__ import annotations

import struct
import zlib

PNG_SIG = b"\x89PNG\r\n\x1a\n"


class PngError(ValueError):
    """El PNG no se puede leer con este códec."""


class Png:
    """Un PNG ya decodificado: dimensiones + píxeles RGBA."""

    __slots__ = ("width", "height", "pixels")

    def __init__(self, width: int, height: int, pixels: bytearray):
        self.width = width
        self.height = height
        self.pixels = pixels  # RGBA plano, 4 bytes por píxel

    def __repr__(self) -> str:  # pragma: no cover - cosmético
        return f"Png({self.width}x{self.height})"


def png_info(buf: bytes) -> dict | None:
    """Cabecera IHDR sin decodificar nada más. None si no es un PNG."""
    if len(buf) < 33 or buf[:8] != PNG_SIG:
        return None
    width, height = struct.unpack(">II", buf[16:24])
    return {
        "width": width,
        "height": height,
        "bit_depth": buf[24],
        "color_type": buf[25],
        "interlace": buf[28],
    }


def decode_png(buf: bytes) -> Png | None:
    """Decodifica un PNG no entrelazado. None si no puede.

    Soporta color types 0 (gris), 2 (RGB), 3 (paleta), 4 (gris+alfa),
    6 (RGBA) y bit depths 1/2/4/8/16. El resultado siempre es RGBA de 8
    bits: los valores de bit depth menor se escalan, la paleta se resuelve
    con PLTE + tRNS.
    """
    info = png_info(buf)
    if not info or info["interlace"] != 0:
        return None
    bit_depth = info["bit_depth"]
    color_type = info["color_type"]
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    if channels is None or bit_depth not in (1, 2, 4, 8, 16):
        return None

    # Reunir chunks: IDAT (en orden), PLTE y tRNS.
    idat: list[bytes] = []
    palette = None
    trns = None
    p = 8
    while p + 8 <= len(buf):
        (length,) = struct.unpack(">I", buf[p : p + 4])
        ctype = buf[p + 4 : p + 8]
        data = buf[p + 8 : p + 8 + length]
        if ctype == b"IDAT":
            idat.append(data)
        elif ctype == b"PLTE":
            palette = data
        elif ctype == b"tRNS":
            trns = data
        elif ctype == b"IEND":
            break
        p += 12 + length
    if not idat:
        return None
    if color_type == 3 and palette is None:
        return None

    try:
        raw = zlib.decompress(b"".join(idat))
    except zlib.error:
        return None

    w, h = info["width"], info["height"]
    # Bytes por pixel (para el desfiltro) y bytes por línea de escaneo.
    bpp = max(1, (channels * bit_depth + 7) // 8)
    stride = (w * channels * bit_depth + 7) // 8

    out = bytearray(w * h * 4)
    prev = bytearray(stride)
    cur = bytearray(stride)
    pos = 0
    max_val = (1 << bit_depth) - 1

    for y in range(h):
        if pos >= len(raw):
            return None
        filt = raw[pos]
        pos += 1
        if pos + stride > len(raw):
            return None
        cur[:] = raw[pos : pos + stride]
        pos += stride

        # Desfiltrado PNG (línea a línea, véase la especificación).
        for x in range(stride):
            a = cur[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            v = cur[x]
            if filt == 1:
                v = (v + a) & 0xFF
            elif filt == 2:
                v = (v + b) & 0xFF
            elif filt == 3:
                v = (v + ((a + b) >> 1)) & 0xFF
            elif filt == 4:
                pa = abs(b - c)
                pb = abs(a - c)
                pc = abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                v = (v + pr) & 0xFF
            elif filt != 0:
                return None
            cur[x] = v

        # Extraer los valores de cada pixel según el bit depth.
        for x in range(w):
            i = (y * w + x) * 4
            chan = []
            for c in range(channels):
                idx = x * channels + c
                if bit_depth == 8:
                    val = cur[idx]
                elif bit_depth == 16:
                    val = cur[idx * 2]  # se toma el byte alto
                else:
                    # Varios pixeles por byte, del bit más alto al más bajo.
                    bit_pos = idx * bit_depth
                    byte = cur[bit_pos >> 3]
                    shift = 8 - bit_depth - (bit_pos & 7)
                    val = (byte >> shift) & max_val
                    # Escalar a 8 bits.
                    val = 255 if val else 0 if bit_depth == 1 else round(val * 255 / max_val)
                chan.append(val)

            if color_type == 6:
                out[i], out[i + 1], out[i + 2], out[i + 3] = chan
            elif color_type == 2:
                out[i], out[i + 1], out[i + 2] = chan
                out[i + 3] = 255
            elif color_type == 0:
                out[i] = out[i + 1] = out[i + 2] = chan[0]
                out[i + 3] = 255
            elif color_type == 4:
                out[i] = out[i + 1] = out[i + 2] = chan[0]
                out[i + 3] = chan[1]
            elif color_type == 3:
                idx = chan[0]
                out[i] = palette[idx * 3] if idx * 3 < len(palette) else 0
                out[i + 1] = palette[idx * 3 + 1] if idx * 3 + 1 < len(palette) else 0
                out[i + 2] = palette[idx * 3 + 2] if idx * 3 + 2 < len(palette) else 0
                out[i + 3] = trns[idx] if trns is not None and idx < len(trns) else 255

        prev, cur = cur, prev

    return Png(w, h, out)


def _png_chunk(ctype: str, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + ctype.encode("ascii")
        + data
        + struct.pack(">I", zlib.crc32(ctype.encode("ascii") + data) & 0xFFFFFFFF)
    )


def encode_png(width: int, height: int, rgba) -> bytes:
    """Codifica RGBA plano (bytes o bytearray) como PNG RGBA de 8 bits."""
    stride = width * 4
    raw = bytearray((stride + 1) * height)
    for y in range(height):
        base = y * (stride + 1)
        raw[base] = 0  # filtro None
        raw[base + 1 : base + 1 + stride] = rgba[y * stride : (y + 1) * stride]
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        PNG_SIG
        + _png_chunk("IHDR", ihdr)
        + _png_chunk("IDAT", zlib.compress(bytes(raw), 9))
        + _png_chunk("IEND", b"")
    )


def downscale_png(png: Png, max_size: int) -> Png:
    """Reduce la textura para que su lado mayor sea `max_size`.

    Muestreo por vecino más próximo: conserva los colores exactos del arte
    original (pixel art) y es determinista.
    """
    if max_size <= 0 or max(png.width, png.height) <= max_size:
        return png
    if png.width >= png.height:
        nw = max_size
        nh = max(1, round(png.height * max_size / png.width))
    else:
        nh = max_size
        nw = max(1, round(png.width * max_size / png.height))
    src, sw, sh = png.pixels, png.width, png.height
    su, sv = sw / nw, sh / nh
    dst = bytearray(nw * nh * 4)
    for y in range(nh):
        sy = min(sh - 1, int(y * sv))
        for x in range(nw):
            sx = min(sw - 1, int(x * su))
            si = (sy * sw + sx) * 4
            di = (y * nw + x) * 4
            dst[di] = src[si]
            dst[di + 1] = src[si + 1]
            dst[di + 2] = src[si + 2]
            dst[di + 3] = src[si + 3]
    return Png(nw, nh, dst)


def texture_stats(png: Png | None) -> dict:
    """Color medio de los pixeles opacos + si hay transparencia parcial.

    Sirve para elegir el render_method de un bloque (opaque /
    alpha_test / blend), el color del huevo de invocación y el map_color,
    todo derivado del arte real en vez de inventado.
    """
    if png is None:
        return {"hex": "#8A8A8A", "overlay": "#4A4A4A", "semi": False}
    pixels = png.pixels
    r = g = b = n = 0
    semi = False
    for i in range(0, len(pixels), 4):
        a = pixels[i + 3]
        if a == 0:
            continue
        if a != 255:
            semi = True
        r += pixels[i]
        g += pixels[i + 1]
        b += pixels[i + 2]
        n += 1
    if not n:
        return {"hex": "#8A8A8A", "overlay": "#4A4A4A", "semi": False}
    hx = lambda v: format(round(v / n), "02x")  # noqa: E731
    return {
        "hex": "#" + hx(r) + hx(g) + hx(b),
        # Overlay: versión oscurecida del color base (huevos de invocación).
        "overlay": "#" + hx(r / 2) + hx(g / 2) + hx(b / 2),
        "semi": semi,
    }
