"""Tests del códec PNG propio (sin dependencias)."""

from __future__ import annotations

import struct
import zlib

from babelcraft.pngcodec import (
    PNG_SIG,
    Png,
    decode_png,
    downscale_png,
    encode_png,
    png_info,
    texture_stats,
)

from conftest import solid_png


def test_roundtrip_rgba():
    px = bytearray()
    for color in ((255, 0, 0, 255), (0, 255, 0, 128), (0, 0, 255, 0), (10, 20, 30, 255)):
        px.extend(color)
    buf = encode_png(2, 2, px)

    assert buf[:8] == PNG_SIG
    info = png_info(buf)
    assert info["width"] == 2
    assert info["height"] == 2
    assert info["color_type"] == 6

    png = decode_png(buf)
    assert isinstance(png, Png)
    assert (png.width, png.height) == (2, 2)
    assert bytes(png.pixels) == bytes(px)


def test_decode_palette_with_trns():
    # PNG de paleta 2x1: rojo opaco + verde semitransparente.
    ihdr = struct.pack(">IIBBBBB", 2, 1, 8, 3, 0, 0, 0)
    raw = b"\x00" + bytes([0, 1])  # filtro 0 + indices de paleta
    buf = (
        PNG_SIG
        + _chunk("IHDR", ihdr)
        + _chunk("PLTE", bytes([255, 0, 0, 0, 255, 0]))
        + _chunk("tRNS", bytes([255, 128]))
        + _chunk("IDAT", zlib.compress(raw))
        + _chunk("IEND", b"")
    )
    png = decode_png(buf)
    assert png is not None
    assert tuple(png.pixels[0:4]) == (255, 0, 0, 255)
    assert tuple(png.pixels[4:8]) == (0, 255, 0, 128)


def test_decode_rejects_garbage():
    assert decode_png(b"not a png") is None
    assert png_info(b"not a png") is None


def test_texture_stats_and_semi_alpha():
    solid = decode_png(solid_png((255, 0, 0, 255), 4))
    stats = texture_stats(solid)
    assert stats["hex"] == "#ff0000"
    assert stats["overlay"] == "#800000"
    assert stats["semi"] is False

    semi = decode_png(solid_png((0, 0, 255, 128), 4))
    assert texture_stats(semi)["semi"] is True
    assert texture_stats(None)["hex"] == "#8A8A8A"


def test_downscale_keeps_pixel_art_colors():
    # 4x4: color unico por columna, asi el vecino mas proximo es exacto.
    px = bytearray()
    for _y in range(4):
        for x in range(4):
            px.extend((x * 60, 0, 0, 255))
    png = Png(4, 4, px)
    small = downscale_png(png, 2)
    assert (small.width, small.height) == (2, 2)
    assert tuple(small.pixels[0:4]) == (0, 0, 0, 255)
    assert tuple(small.pixels[4:8]) == (120, 0, 0, 255)


def _chunk(ctype: str, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + ctype.encode("ascii")
        + data
        + struct.pack(">I", zlib.crc32(ctype.encode("ascii") + data) & 0xFFFFFFFF)
    )
