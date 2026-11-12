"""Escritor del addon: dos árboles (BP/RP), índices, manifest, .mcaddon.

Bedrock no admite namespaces en las RUTAS de ficheros del addon, pero sí
en los identificadores. Estrategia (probada en CobblemonBedrock):

  - BP/items/<ns>_<name>.json, BP/blocks/<ns>_<name>.json, ...:
    nombre de fichero plano y seguro; el identificador interno mantiene
    `ns:name`.
  - Texturas: RP/textures/{items,blocks,entity}/<ns>/<nombre>.png.
  - Índices obligatorios que el juego exige y que nadie puede escribir a
    mano con fiabilidad: item_texture.json, terrain_texture.json,
    blocks.json, sounds.json (dentro de definitions/), textos .lang.
  - Minificación por defecto: los JSON de Bedrock se leen enteros en
    RAM al cargar el pack; sin espacios ni saltos el addon pesa menos y
    arranca antes (en CobblemonBedrock: -57% de RAM).
  - pack_icon.png generado: cuadrado degradado determinista derivado del
    nombre del mod (nunca negro, nunca aleatorio).
"""

from __future__ import annotations

import json
import os
import zipfile
from collections import OrderedDict

from . import versions
from .model import slug
from .pngcodec import Png, encode_png

import uuid as _uuid


def new_uuid() -> str:
    return str(_uuid.uuid4())


class AddonWriter:
    """Acumula ficheros del BP y RP y al final los vuelca todo."""

    def __init__(self, out_dir: str, namespace: str, name: str, version: str, minify: bool = True):
        self.out_dir = out_dir
        self.ns = namespace or "babelcraft"
        self.name = name or namespace or "BabelCraft"
        self.version = version or "1.0.0"
        self.minify = minify

        self.bp: dict[str, bytes] = {}
        self.rp: dict[str, bytes] = {}

        self.bp_uuid = new_uuid()
        self.rp_uuid = new_uuid()

        # Índices que el juego exige.
        self.item_textures: "OrderedDict[str, list[str] | str]" = OrderedDict()
        self.terrain_textures: "OrderedDict[str, str]" = OrderedDict()
        self.blocks_json: dict[str, dict] = {}
        self.lang: dict[str, dict[str, str]] = {}  # "es_ES" -> {clave: valor}
        self.sound_definitions: dict[str, dict] = {}
        self._dirty = {"item_texture", "terrain_texture", "blocks", "lang", "sound"}

    # --- Escritura básica -------------------------------------------------

    def bp_json(self, rel: str, obj: object) -> None:
        self.bp[rel] = self._dumps(obj)

    def rp_json(self, rel: str, obj: object) -> None:
        self.rp[rel] = self._dumps(obj)

    def bp_blob(self, rel: str, data: bytes) -> None:
        self.bp[rel] = data

    def rp_blob(self, rel: str, data: bytes) -> None:
        self.rp[rel] = data

    def _dumps(self, obj: object) -> bytes:
        if self.minify:
            return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return json.dumps(obj, indent=2, ensure_ascii=False).encode("utf-8")

    # --- Índices ------------------------------------------------------------

    def add_item_texture(self, shortname: str, path: str) -> None:
        """Registra `shortname` -> ruta de textura en item_texture.json."""
        self.item_textures[shortname] = {"textures": path}

    def add_terrain_texture(self, shortname: str, path: str) -> None:
        """Ídem para terrain_texture.json (bloques)."""
        self.terrain_textures[shortname] = {"textures": path}

    def add_block_visual(self, identifier: str, sound: str, textures: dict) -> None:
        """Entrada de blocks.json (válido para bloques sin geometría custom)."""
        self.blocks_json[identifier] = {"sound": sound, "textures": textures}

    def add_lang(self, lang: str, key: str, value: str) -> None:
        self.lang.setdefault(lang, {})[key] = value

    def add_sound(self, name: str, definition: dict) -> None:
        self.sound_definitions[name] = definition

    # --- Manifest y empaquetado ---------------------------------------------

    def _manifest(self, side: str, uuid_val: str, module_type: str) -> dict:
        return {
            "format_version": versions.MANIFEST_FORMAT,
            "header": {
                "name": f"{self.name} ({side})",
                "description": f"Convertido de Java con BabelCraft — {side}",
                "uuid": uuid_val,
                "version": [1, 0, 0],
                "min_engine_version": versions.MIN_ENGINE,
            },
            "modules": [
                {"type": module_type, "uuid": new_uuid(), "version": [1, 0, 0]}
            ],
        }

    def finalize(self, pack_mcaddon: bool = True) -> str:
        """Vuelca BP/RP en disco y empaqueta el .mcaddon. Devuelve su ruta."""
        ns = self.ns
        slug_name = slug(self.name)

        # índices de texturas
        if self.item_textures:
            self.rp_json(
                "textures/item_texture.json",
                {
                    "resource_pack_name": slug_name,
                    "texture_name": "atlas.items",
                    "texture_data": self.item_textures,
                },
            )
        if self.terrain_textures:
            self.rp_json(
                "textures/terrain_texture.json",
                {
                    "resource_pack_name": slug_name,
                    "texture_name": "atlas.terrain",
                    "padding": 8,
                    "num_mip_levels": 4,
                    "texture_data": self.terrain_textures,
                },
            )
        if self.blocks_json:
            # blocks.json exige format_version en la raíz; sin él Bedrock
            # ignora las entradas de sonido/textura de los bloques.
            doc: dict = {"format_version": [1, 1, 0]}
            doc.update(self.blocks_json)
            self.rp_json("blocks.json", doc)

        # sonidos
        if self.sound_definitions:
            self.rp_json(
                "sounds/sound_definitions.json",
                {
                    "format_version": versions.SOUND_DEFINITIONS,
                    "sound_definitions": self.sound_definitions,
                },
            )

        # lang: Bedrock exige pack.name / pack.description
        for lang, table in self.lang.items():
            table.setdefault("pack.name", self.name)
            table.setdefault("pack.description", "Convertido con BabelCraft")
            lines = [f"{k}={v}" for k, v in table.items()]
            self.rp_blob(f"texts/{lang}.lang", ("\n".join(lines) + "\n").encode("utf-8"))

        # manifests
        bp_manifest = self._manifest("BP", self.bp_uuid, "data")
        rp_manifest = self._manifest("RP", self.rp_uuid, "resources")
        # Dependencia mutua BP -> RP: al instalar el .mcaddon se activan juntos.
        bp_manifest["dependencies"] = [{"uuid": self.rp_uuid, "version": [1, 0, 0]}]
        self.bp_json("manifest.json", bp_manifest)
        self.rp_json("manifest.json", rp_manifest)

        # iconos de pack (deterministas, derivados del nombre)
        icon = _pack_icon(self.name)
        self.bp_blob("pack_icon.png", icon)
        self.rp_blob("pack_icon.png", icon)

        # volcado (limpiar primero para no arrastrar ficheros de ejecuciones previas)
        bp_dir = os.path.join(self.out_dir, f"BP_{slug_name}")
        rp_dir = os.path.join(self.out_dir, f"RP_{slug_name}")
        _clean_tree(bp_dir)
        _clean_tree(rp_dir)
        _write_tree(bp_dir, self.bp)
        _write_tree(rp_dir, self.rp)

        addon = ""
        if pack_mcaddon:
            addon = os.path.join(self.out_dir, f"{slug_name}.mcaddon")
            with zipfile.ZipFile(addon, "w", zipfile.ZIP_DEFLATED) as z:
                for root, rel in ((bp_dir, f"BP_{slug_name}"), (rp_dir, f"RP_{slug_name}")):
                    for f in sorted(_tree_files(root)):
                        z.write(os.path.join(root, f), f"{rel}/{f}")
        return addon


def _tree_files(root: str) -> set[str]:
    files: set[str] = set()
    for dirpath, _dirs, fs in os.walk(root):
        for name in fs:
            full = os.path.join(dirpath, name)
            files.add(os.path.relpath(full, root).replace("\\", "/"))
    return files


def _clean_tree(root: str) -> None:
    """Elimina un árbol de directorios si existe."""
    if os.path.exists(root):
        import shutil
        shutil.rmtree(root)


def _write_tree(root: str, files: dict[str, bytes]) -> None:
    for rel, data in files.items():
        full = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(data)


def _pack_icon(name: str, size: int = 64) -> bytes:
    """Icono de pack determinista: degradado diagonal derivado del nombre."""
    seed = sum(name.encode("utf-8")) or 1
    c1 = ((seed * 37) % 200 + 40, (seed * 61) % 200 + 40, (seed * 89) % 200 + 40)
    c2 = ((seed * 113) % 200 + 40, (seed * 29) % 200 + 40, (seed * 47) % 200 + 40)
    px = bytearray(size * size * 4)
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size - 2)
            i = (y * size + x) * 4
            px[i] = round(c1[0] + (c2[0] - c1[0]) * t)
            px[i + 1] = round(c1[1] + (c2[1] - c1[1]) * t)
            px[i + 2] = round(c1[2] + (c2[2] - c1[2]) * t)
            px[i + 3] = 255
    return encode_png(size, size, px)
