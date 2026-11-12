"""Descarga selectiva de archivos del pack Cobbleverse desde modrinth.index.json.

- Prioriza contenido relevante para conversión (mods del ecosistema Cobblemon,
  resource packs y datapacks con assets), omitiendo por defecto mods de
  rendimiento/UI/cliente sin contenido convertible evidente.
- Verifica seguridad básica: solo URLs https://cdn.modrinth.com/, comprobación
  de hashes sha512/sha1 y tamaño cuando están disponibles.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PACK = ROOT / "out" / "cobbleverse_pack"
INDEX = PACK / "modrinth.index.json"
DL_ROOT = PACK / "downloads"

# Palabras clave para mods potencialmente relevantes al contenido Cobblemon/juego
MOD_INCLUDE_KEYWORDS = [
    "cobblemon", "cobble", "pokemon", "pokeblock", "poke", "fightorflight",
    "mega_showdown", "megashowdown", "legendary", "rct", "raid", "capture",
    "pasture", "safe", "lumy", "badge", "tm", "move", "dollar", "furni",
    "cuisine", "battle", "monument", "biome", "structure", "waystone",
    "sophisticated", "toms_storage", "handcrafted", "comforts", "rechiseled",
    "beautify", "moar", "backport", "vanillabackport", "decor", "furniture",
]

# Mods claramente orientados a rendimiento/cliente/debug/UI que suelen no aportar assets convertibles
MOD_EXCLUDE_KEYWORDS = [
    "sodium", "iris", "lithium", "ferritecore", "modernfix", "immediatelyfast",
    "entityculling", "moreculling", "c2me", "krypton", "badoptimizations",
    "debugify", "notenoughcrashes", "stackdeobfuscator", "spark", "modmenu",
    "reeses", "yet_another_config_lib", "fzzy_config", "konkrete", "fancymenu",
    "betterf3", "betterf1", "controlling", "tooltipfix", "zoomify", "particular",
    "particlerain", "sound-physics", "soundsbegone", "highlight", "ping-wheel",
    "betterthirdperson", "euphoria", "continuity", "lambdynamiclights",
    "entity_texture_features", "entity_model_features", "scalablelux",
    "infinite-music", "musicnotification", "resourcepackoverrides", "libjf",
]

# Resource packs "credits only" / deshabilitados suelen no ser necesarios
RP_EXCLUDE_NAME_PATTERNS = [
    "credits only",
    "do not enable",
]


def sha1_file(p: Path) -> str:
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha512_file(p: Path) -> str:
    h = hashlib.sha512()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_safe_url(url: str) -> bool:
    return url.startswith("https://cdn.modrinth.com/")


def find_local(path: str) -> Path | None:
    rel = Path(path)
    candidates = [
        PACK / rel,
        ROOT / "out" / "cobbleverse" / rel.name,
        PACK / "overrides" / rel,
        PACK / "downloads" / rel,
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    # search by basename in overrides/downloads
    for base in [PACK / "overrides", PACK / "downloads", ROOT / "out" / "cobbleverse"]:
        if not base.exists():
            continue
        for c in base.rglob(rel.name):
            if c.is_file():
                return c
    return None


def should_download(entry: dict, include_all_mods: bool = False) -> tuple[bool, str]:
    path = entry.get("path", "")
    p = Path(path)
    kind = p.parts[0] if p.parts else ""
    name_lower = p.name.lower()

    if kind == "resourcepacks":
        if any(pat in name_lower or pat in path.lower() for pat in RP_EXCLUDE_NAME_PATTERNS):
            return False, "resourcepack credits-only/deshabilitado"
        return True, "resourcepack"
    if kind == "datapacks":
        return True, "datapack"
    if kind == "shaderpacks":
        return False, "shaderpack (no convertible a addon Bedrock)"
    if kind == "mods":
        if include_all_mods:
            return True, "mod (all)"
        if any(k in name_lower for k in MOD_EXCLUDE_KEYWORDS):
            # pero si también parece de contenido cobblemon, priorizar include
            if any(k in name_lower for k in MOD_INCLUDE_KEYWORDS):
                return True, "mod ecosistema/contenido"
            return False, "mod rendimiento/cliente/ui"
        if any(k in name_lower for k in MOD_INCLUDE_KEYWORDS):
            return True, "mod ecosistema/contenido"
        # libs/core mods pueden ser necesarias para entender contexto, pero no convertibles; omitir por defecto
        return False, "mod librería/otro (no prioritario para conversión de contenido)"
    return False, f"tipo {kind} no prioritario"


def verify_hashes(file_path: Path, hashes: dict) -> tuple[bool, str]:
    if not hashes:
        return True, "sin hashes en índice"
    if "sha512" in hashes:
        actual = sha512_file(file_path)
        if actual.lower() != str(hashes["sha512"]).lower():
            return False, f"sha512 mismatch (expected {hashes['sha512']}, got {actual})"
    if "sha1" in hashes:
        actual = sha1_file(file_path)
        if actual.lower() != str(hashes["sha1"]).lower():
            return False, f"sha1 mismatch (expected {hashes['sha1']}, got {actual})"
    return True, "ok"


def download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "BabelCraft/0.1 (Cobbleverse asset fetch)"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as out:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)


def main() -> int:
    include_all_mods = "--all-mods" in sys.argv
    dry_run = "--dry-run" in sys.argv

    idx = json.loads(INDEX.read_text(encoding="utf-8"))
    files = idx.get("files", [])

    planned = []
    skipped = []
    already = []

    for entry in files:
        path = entry.get("path", "")
        local = find_local(path)
        if local:
            ok, msg = verify_hashes(local, entry.get("hashes", {}))
            already.append((path, str(local), ok, msg))
            continue
        do, reason = should_download(entry, include_all_mods=include_all_mods)
        if do:
            planned.append((entry, reason))
        else:
            skipped.append((path, reason))

    print(f"Total: {len(files)} | presentes: {len(already)} | a descargar: {len(planned)} | omitidos: {len(skipped)}")
    print("\n== Presentes (verificación hashes) ==")
    bad_present = 0
    for path, local, ok, msg in already:
        status = "OK" if ok else "HASH_FAIL"
        if not ok:
            bad_present += 1
        print(f"[{status}] {path} -> {local} ({msg})")

    print("\n== Omitidos ==")
    for path, reason in skipped:
        print(f"- {path} [{reason}]")

    print("\n== Plan de descarga ==")
    for entry, reason in planned:
        url = (entry.get("downloads") or [None])[0]
        print(f"- {entry.get('path')} [{reason}] size={entry.get('fileSize')} safe={is_safe_url(url or '')} url={url}")

    if dry_run:
        print("\n(dry-run) No se realizaron descargas.")
        return 1 if bad_present else 0

    print("\n== Descargando ==")
    downloaded = 0
    failed = 0
    for entry, reason in planned:
        path = entry.get("path", "")
        urls = entry.get("downloads") or []
        url = urls[0] if urls else None
        if not url or not is_safe_url(url):
            print(f"[SKIP-UNSAFE] {path} url={url}")
            failed += 1
            continue
        dest = DL_ROOT / path
        try:
            print(f"[DL] {path}")
            download_file(url, dest)
            ok, msg = verify_hashes(dest, entry.get("hashes", {}))
            size = dest.stat().st_size
            expected_size = entry.get("fileSize")
            if expected_size and size != expected_size:
                ok = False
                msg = f"size mismatch (expected {expected_size}, got {size}); {msg}"
            if not ok:
                print(f"  [HASH_FAIL] {msg} -> eliminado")
                try:
                    dest.unlink()
                except Exception:
                    pass
                failed += 1
                continue
            print(f"  [OK] {msg} ({size} bytes)")
            downloaded += 1
        except Exception as e:
            print(f"  [ERR] {e}")
            failed += 1

    print(f"\nDescargados OK: {downloaded} | Fallidos: {failed} | Presentes hash-fail: {bad_present}")
    print(f"Directorio: {DL_ROOT}")
    return 1 if (failed or bad_present) else 0


if __name__ == "__main__":
    raise SystemExit(main())
