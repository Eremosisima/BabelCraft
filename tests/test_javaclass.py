"""Tests del lector de bytecode (constant pool de `.class`)."""

from __future__ import annotations

import struct

from babelcraft.javaclass import ClassInfo, extract_ids, mentions_any, read_class


def _utf8(text: str) -> bytes:
    raw = text.encode("utf-8")
    return b"\x01" + struct.pack(">H", len(raw)) + raw


def _class_ref(index: int) -> bytes:
    return b"\x07" + struct.pack(">H", index)


def _long(value: int) -> bytes:
    return b"\x05" + struct.pack(">q", value)


def build_class(
    *,
    this_name: str = "com/example/ModRuby",
    super_name: str = "java/lang/Object",
    interface_name: str | None = "com/example/Api",
    strings: tuple[str, ...] = (
        "minimod:ruby",
        "minimod:ruby_sword",
        "software/bernie/geckolib",
        "minecraft:stone",
        "othermod:thing",
        "BAD ID",
    ),
    major: int = 61,
) -> bytes:
    """Construye un `.class` mínimo válido hasta la tabla de interfaces.

    No incluye campos ni métodos: `read_class` solo necesita el constant
    pool, this_class, super_class e interfaces.
    """
    pool: list[bytes] = []
    next_index = 1

    def add(entry: bytes) -> int:
        nonlocal next_index
        index = next_index
        pool.append(entry)
        # long/double ocupan DOS huecos del constant pool.
        next_index += 2 if entry[0] in (5, 6) else 1
        return index

    this_utf = add(_utf8(this_name))
    this_class = add(_class_ref(this_utf))
    super_utf = add(_utf8(super_name))
    super_class = add(_class_ref(super_utf))
    # Long a propósito: si el lector no lo salta, todo lo siguiente se
    # desalinea y el test falla.
    add(_long(42))
    for text in strings:
        add(_utf8(text))
    interface_class = 0
    if interface_name:
        interface_utf = add(_utf8(interface_name))
        interface_class = add(_class_ref(interface_utf))

    body = b"\xca\xfe\xba\xbe" + struct.pack(">HH", 0, major)
    body += struct.pack(">H", next_index) + b"".join(pool)
    body += struct.pack(">H", 0)  # access_flags
    body += struct.pack(">H", this_class)
    body += struct.pack(">H", super_class)
    body += struct.pack(">H", 1 if interface_name else 0)
    if interface_name:
        body += struct.pack(">H", interface_class)
    return body


def test_read_class_basic_fields():
    info = read_class(build_class())
    assert isinstance(info, ClassInfo)
    assert info.name == "com/example/ModRuby"
    assert info.super_name == "java/lang/Object"
    assert info.interfaces == ["com/example/Api"]
    assert info.version == 61
    assert "minimod:ruby" in info.strings
    assert "com/example/Api" in info.strings


def test_long_constant_pool_entry_does_not_desync():
    # El long va antes de las cadenas: si ocupa un solo hueco, las cadenas
    # se leen corridas y el nombre de la clase sale mal.
    info = read_class(build_class(strings=("minimod:ruby",)))
    assert info is not None
    assert info.name == "com/example/ModRuby"
    assert "minimod:ruby" in info.strings


def test_extract_ids_filters_valid_namespaces_and_chars():
    info = read_class(build_class())
    ids = extract_ids(info.strings, "minimod")
    assert ids == {"minimod:ruby", "minimod:ruby_sword", "othermod:thing"}
    # Un datapack puro sí puede declarar minecraft: como propio.
    assert "minecraft:stone" in extract_ids(info.strings, "minecraft")
    # Espacios y nombres de clase no son ids.
    assert "BAD ID" not in ids
    assert "com/example/ModRuby" not in ids


def test_extract_ids_rejects_long_and_empty():
    assert extract_ids(["", "x" * 100 + ":a", ":", "mod:", ":x"], "mod") == set()


def test_mentions_any():
    info = read_class(build_class())
    assert mentions_any(info.strings, ("geckolib",)) is True
    assert mentions_any(info.strings, ("software/bernie/geckolib",)) is True
    assert mentions_any(info.strings, ("create", "mekanism")) is False


def test_invalid_class_returns_none():
    assert read_class(b"") is None
    assert read_class(b"not a class at all") is None
    assert read_class(b"\xca\xfe\xba\xbe" + b"\x00" * 4) is None
    # Tag de constant pool inexistente (2 no existe en la JVM).
    bad = b"\xca\xfe\xba\xbe" + struct.pack(">HHH", 0, 61, 2) + b"\x02\x00\x00"
    assert read_class(bad) is None
