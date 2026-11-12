"""Tests del lector de fuentes (carpeta / zip / memoria) y metadatos."""

from __future__ import annotations

import json
import struct
import zipfile

import pytest

from babelcraft.source import Source, detect_loader, load_mod


# ---------------------------------------------------------------------------
#  Builder de .class sintético (solo constant pool + this/super/interfaces).
# ---------------------------------------------------------------------------


def _utf8(text: str) -> bytes:
    raw = text.encode("utf-8")
    return b"\x01" + struct.pack(">H", len(raw)) + raw


def synthetic_class(strings: list[str], name: str = "com/example/Thing") -> bytes:
    pool: list[bytes] = []
    next_index = 1

    def add(entry: bytes) -> int:
        nonlocal next_index
        index = next_index
        pool.append(entry)
        next_index += 2 if entry[0] in (5, 6) else 1
        return index

    this_utf = add(_utf8(name))
    this_class = add(b"\x07" + struct.pack(">H", this_utf))
    super_utf = add(_utf8("java/lang/Object"))
    super_class = add(b"\x07" + struct.pack(">H", super_utf))
    for text in strings:
        add(_utf8(text))

    body = b"\xca\xfe\xba\xbe" + struct.pack(">HH", 0, 61)
    body += struct.pack(">H", next_index) + b"".join(pool)
    body += struct.pack(">H", 0)  # access_flags
    body += struct.pack(">HH", this_class, super_class)
    body += struct.pack(">H", 0)  # sin interfaces
    return body


def _j(obj) -> bytes:
    return json.dumps(obj).encode("utf-8")


# ---------------------------------------------------------------------------
#  Source: memoria, carpeta y zip
# ---------------------------------------------------------------------------


def test_source_memory_dict():
    src = Source({
        "fabric.mod.json": _j({"id": "m", "name": "M"}),
        "assets/m/textures/item/a.png": b"png",
        "zzz.txt": b"z",
    })
    assert src.kind == "memoria"
    assert src.walk() == sorted([
        "fabric.mod.json",
        "assets/m/textures/item/a.png",
        "zzz.txt",
    ])
    assert src.exists("zzz.txt") is True
    assert src.exists("nope") is False
    assert src.read_bytes("zzz.txt") == b"z"
    assert src.read_json("fabric.mod.json") == {"id": "m", "name": "M"}
    assert src.glob("assets/m/", ".png") == ["assets/m/textures/item/a.png"]
    assert src.glob("assets/") == [
        "assets/m/textures/item/a.png",
    ]


def test_source_read_json_or_tolerates_garbage():
    src = Source({"bad.json": b"{nope", "ok.json": b'{"a": 1}', "missing.json": b"x"})
    assert src.read_json_or("bad.json") is None
    assert src.read_json_or("bad.json", {"default": 1}) == {"default": 1}
    assert src.read_json_or("ok.json") == {"a": 1}
    assert src.read_json_or("missing.json", None) is None


def test_source_copy_all_filters():
    src = Source({
        "a.png": b"x",
        "b.ogg": b"x",
        "c.txt": b"x",
        "skip/a.png": b"x",
    })
    assert src.copy_all((".png", ".ogg"), exclude_prefixes=("skip/",)) == ["a.png", "b.ogg"]


def test_source_folder(tmp_path):
    root = tmp_path / "mod"
    (root / "assets" / "m" / "lang").mkdir(parents=True)
    (root / "assets" / "m" / "lang" / "en_us.json").write_text('{"a": "b"}', encoding="utf-8")
    (root / "pack.mcmeta").write_text("{}", encoding="utf-8")

    src = Source(str(root))
    assert src.kind == "carpeta"
    assert src.walk() == [
        "assets/m/lang/en_us.json",
        "pack.mcmeta",
    ]
    assert src.exists("pack.mcmeta") is True
    assert src.exists("assets/m/lang/en_us.json") is True
    assert src.exists("other.json") is False
    assert src.read_json("assets/m/lang/en_us.json") == {"a": "b"}
    assert src.glob("assets/") == ["assets/m/lang/en_us.json"]


def test_source_zip(tmp_path):
    jar = tmp_path / "mod.jar"
    with zipfile.ZipFile(jar, "w") as z:
        z.writestr("fabric.mod.json", _j({"id": "zipmod", "name": "Zip Mod"}))
        z.writestr("assets/zipmod/x.txt", "hola")
        z.writestr("dir/", "")  # los directorios no cuentan como ficheros

    src = Source(str(jar))
    assert src.kind == "jar/zip"
    assert src.walk() == ["assets/zipmod/x.txt", "fabric.mod.json"]
    assert src.read_bytes("assets/zipmod/x.txt") == b"hola"
    assert src.read_json("fabric.mod.json")["id"] == "zipmod"
    assert src.exists("fabric.mod.json") is True


def test_source_rejects_missing_path(tmp_path):
    with pytest.raises(ValueError):
        Source(str(tmp_path / "no_existe_nada"))


# ---------------------------------------------------------------------------
#  detect_loader
# ---------------------------------------------------------------------------


def test_detect_loader_all_kinds():
    assert detect_loader(Source({"fabric.mod.json": b"{}"})) == ("fabric", ["fabric"])
    assert detect_loader(Source({"META-INF/mods.toml": b"modId=x"})) == ("forge", ["forge"])
    assert detect_loader(Source({"neoforge.mods.toml": b"modId=x"})) == ("neoforge", ["neoforge"])
    assert detect_loader(Source({"quilt.mod.json": b"{}"})) == ("quilt", ["quilt"])
    assert detect_loader(Source({"data/dp/recipe/a.json": b"{}"})) == ("datapack", ["datapack"])
    assert detect_loader(Source({"readme.txt": b"hola"})) == ("desconocido", [])


# ---------------------------------------------------------------------------
#  load_mod: metadatos y bytecode
# ---------------------------------------------------------------------------


def test_load_mod_fabric_metadata():
    mod = load_mod(Source({
        "fabric.mod.json": _j({"id": "minimod", "name": "Mini Mod", "version": "1.2.3"}),
        "assets/minimod/lang/en_us.json": b"{}",
    }))
    assert mod.namespace == "minimod"
    assert mod.name == "Mini Mod"
    assert mod.version == "1.2.3"
    assert mod.loader == "fabric"
    assert mod.mentions_geckolib is False
    assert mod.java_version == 0


def test_load_mod_forge_toml_metadata():
    toml = (
        'modLoader="javafml"\n'
        "loaderVersion=\"[40,)\"\n"
        "\n"
        "[[mods]]\n"
        'modId="Forgy"\n'
        'version="3.1.0"\n'
        'displayName="Forgy Mod"\n'
        "\n"
        "[[dependencies.forgy]]\n"
        'modId="minecraft"\n'
    )
    mod = load_mod(Source({"META-INF/mods.toml": toml.encode("utf-8")}))
    assert mod.loader == "forge"
    assert mod.namespace == "forgy"  # modId se normaliza a minúsculas
    assert mod.name == "Forgy Mod"
    assert mod.version == "3.1.0"


def test_load_mod_neoforge_and_quilt(tmp_path):
    mod = load_mod(Source({"neoforge.mods.toml": b'[[mods]]\nmodId="neo1"\n'}))
    assert (mod.loader, mod.namespace) == ("neoforge", "neo1")
    mod = load_mod(Source({"quilt.mod.json": _j({"quilt_loader": {"id": "quilty"}})}))
    assert mod.loader == "quilt"
    # quilt sin id en la raíz: el namespace sale de las carpetas data/assets.
    mod = load_mod(Source({
        "quilt.mod.json": _j({}),
        "data/quilty/recipe/a.json": b"{}",
    }))
    assert mod.namespace == "quilty"


def test_load_mod_datapack_namespace_from_folders():
    mod = load_mod(Source({
        "pack.mcmeta": _j({"pack": {"pack_format": 48}}),
        "data/dpmod/recipe/a.json": _j({"type": "minecraft:crafting_shapeless"}),
        "data/minecraft/tags/item/a.json": b"{}",
    }))
    assert mod.loader == "datapack"
    assert mod.namespace == "dpmod"  # minecraft se descarta como namespace
    assert mod.name == "dpmod"


def test_load_mod_invalid_metadata_falls_back_to_folders():
    mod = load_mod(Source({
        "fabric.mod.json": b"{roto",
        "assets/other/lang/en_us.json": b"{}",
    }))
    assert mod.namespace == "other"


def test_load_mod_bytecode_evidence():
    mod = load_mod(Source({
        "fabric.mod.json": _j({"id": "minimod", "name": "Mini Mod"}),
        "com/example/Thing.class": synthetic_class([
            "minimod:ruby",
            "minimod:ruby_ore",
            "othermod:gem",
            "software/bernie/geckolib3",
            "minecraft:stone",
            "una frase con espacios",
        ]),
    }))
    assert mod.ids_from_bytecode == {"minimod:ruby", "minimod:ruby_ore", "othermod:gem"}
    assert mod.mentions_geckolib is True
    assert mod.foreign_namespaces == {"othermod"}
    assert mod.java_version == 61
    assert "minimod:ruby" in mod.class_strings


def test_load_mod_geckolib_dependency_not_foreign():
    mod = load_mod(Source({
        "fabric.mod.json": _j({"id": "minimod"}),
        "a.class": synthetic_class(["geckolib:model", "minimod:x"]),
    }))
    assert mod.mentions_geckolib is True
    assert "geckolib" not in mod.foreign_namespaces


def test_load_mod_accepts_dict_and_folder(tmp_path, minimod_files):
    # dict directamente...
    mod = load_mod(minimod_files)
    assert mod.namespace == "minimod"
    # ...y carpeta en disco.
    root = tmp_path / "jar"
    for rel, data in minimod_files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    mod2 = load_mod(str(root))
    assert mod2.namespace == "minimod"
    assert mod2.loader == "fabric"
    assert mod2.name == "Mini Mod"
