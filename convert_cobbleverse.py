"""Conversión del pack Cobbleverse (mejor esfuerzo) a un addon de Bedrock.

Estrategia:
- Usa el jar de Cobblemon como base.
- Superpone (overlay) resource packs y datapacks del pack Cobbleverse en un
  directorio fusionado (assets/ y data/) respetando orden de prioridad.
- Convierte el resultado con BabelCraft y reporta hallazgos.

Nota: Cobbleverse es un modpack completo con muchos mods Java; este script
convierte principalmente el contenido declarativo disponible localmente
(Cobblemon + RPs/DPs/config overrides relevantes), no la lógica Java.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

import babelcraft


ROOT = Path(__file__).resolve().parent
PACK_DIR = ROOT / "out" / "cobbleverse_pack"
BASE_JAR = ROOT / "out" / "cobbleverse" / "Cobblemon-fabric-1.7.3+1.21.1.jar"
MERGED_DIR = ROOT / "out" / "cobbleverse_merged_source"
OUT_DIR = ROOT / "out" / "cobbleverse_converted"

# Prioridad de overlays (de menor a mayor): los últimos sobreescriben.
RESOURCEPACK_ORDER = [
    "COBBLEVERSE RP.zip",
    "CobbleMotion RP.zip",
    "HydroReanimodel RP.zip",
    "OJsAnimations RP.zip",
    "ATMxMSD RP.zip",
    "CavsCobbleMons RP.zip",
    "E19 Cobblemon Minimap Icons.zip",
    "GlitchDex RP.zip",
    "LackingMons RP.zip",
    "MissingMons RP.zip",
    "MundialMons RP.zip",
    "MysticMons RP.zip",
    "PlanetaCobblemon RP.zip",
    "Pokemans RP.zip",
    "TDmon RP.zip",
    "COBBLEVERSE RCTmod RP.zip",
    # Packs de interfaz/sonido pueden aportar poco a Bedrock addon, pero se incluyen si tienen assets útiles.
    "Cobblemon Interface.zip.rpo",
    "Cobblemon Interface Modded.zip.rpo",
]

DATAPACK_ORDER = [
    # Se intentan nombres conocidos; además se escanean todos los zips en datapacks/.
    "COBBLEVERSE-DP-v30.7.0.zip",
    "COBBLEVERSE-DP-v30.zip",
    "COBBLEVERSE-Loot-DP-v1.6.2.zip",
    "COBBLEVERSE-Loot-DP-v11.zip",
    "COBBLEVERSE-RCT-DP-v0.0.17.zip",
    "COBBLEVERSE-RCT-DP-v20.zip",
    "COBBLEVERSE - No Evolution Items Recipe.zip",
    "COBBLEVERSE - No Held Items Recipe.zip",
    # extras
    "extra/COBBLEVERSE - Wild Level 50 Max [DP].zip",
    "extra/COBBLEVERSE - Wild Level 75 Max [DP].zip",
    "extra/COBBLEVERSE - Wild Level 100 Max [DP].zip",
    "extra/COBBLEVERSE-Hoenn-DP.zip",
    "extra/COBBLEVERSE-Johto-DP.zip",
    "extra/COBBLEVERSE-Sinnoh-DP.zip",
    "extra/Terralith-DP.zip",
]


def _is_pack_zip(path: Path) -> bool:
    return path.suffix.lower() == ".zip" and zipfile.is_zipfile(path)


def _extract_overlay_zip(zip_path: Path, merged: Path, kinds: tuple[str, ...]) -> dict[str, int]:
    stats = {k: 0 for k in kinds}
    if not _is_pack_zip(zip_path):
        return stats
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            name = info.filename
            if name.endswith("/"):
                continue
            # Normalizar separadores
            rel = name.replace("\\", "/")
            # Saltar prefijos comunes dentro de zips (algunos vienen anidados)
            # pero mantener assets/data tal cual.
            parts = rel.split("/")
            idx = None
            for i, p in enumerate(parts):
                if p in kinds:
                    idx = i
                    break
            if idx is None:
                continue
            dest_rel = "/".join(parts[idx:])
            dest = merged / dest_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
            stats[parts[idx]] += 1
    return stats


def _copy_base_jar(jar_path: Path, merged: Path) -> dict[str, int]:
    stats = {"assets": 0, "data": 0}
    with zipfile.ZipFile(jar_path) as z:
        for info in z.infolist():
            name = info.filename
            if name.endswith("/"):
                continue
            if not (name.startswith("assets/") or name.startswith("data/")):
                continue
            dest = merged / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
            stats["assets" if name.startswith("assets/") else "data"] += 1
    return stats


def build_merged_source() -> Path:
    if MERGED_DIR.exists():
        shutil.rmtree(MERGED_DIR)
    (MERGED_DIR / "assets").mkdir(parents=True, exist_ok=True)
    (MERGED_DIR / "data").mkdir(parents=True, exist_ok=True)

    print(f"Base: {BASE_JAR}")
    base_stats = _copy_base_jar(BASE_JAR, MERGED_DIR)
    print(f"  [base] assets={base_stats['assets']} data={base_stats['data']}")

    rp_dir = PACK_DIR / "overrides" / "resourcepacks"
    print(f"\nResource packs (overlays): {rp_dir}")
    for name in RESOURCEPACK_ORDER:
        p = rp_dir / name
        if not p.exists():
            print(f"  [skip] {name} (no encontrado)")
            continue
        st = _extract_overlay_zip(p, MERGED_DIR, ("assets",))
        print(f"  [rp] {name}: assets={st.get('assets',0)}")

    dp_dir = PACK_DIR / "overrides" / "datapacks"
    print(f"\nDatapacks (overlays): {dp_dir}")
    for rel in DATAPACK_ORDER:
        p = dp_dir / rel
        if not p.exists():
            print(f"  [skip] {rel} (no encontrado)")
            continue
        st = _extract_overlay_zip(p, MERGED_DIR, ("data",))
        print(f"  [dp] {rel}: data={st.get('data',0)}")

    # Incluir cualquier RP/DP adicional no listado explícitamente (al final).
    for p in sorted(rp_dir.glob("*.zip")):
        if p.name in RESOURCEPACK_ORDER:
            continue
        st = _extract_overlay_zip(p, MERGED_DIR, ("assets",))
        if st.get("assets", 0):
            print(f"  [rp-extra] {p.name}: assets={st.get('assets',0)}")
    for p in sorted(dp_dir.rglob("*.zip")):
        rel = str(p.relative_to(dp_dir)).replace("\\", "/")
        if rel in DATAPACK_ORDER or p.name in DATAPACK_ORDER:
            continue
        st = _extract_overlay_zip(p, MERGED_DIR, ("data",))
        if st.get("data", 0):
            print(f"  [dp-extra] {rel}: data={st.get('data',0)}")

    # Metadatos explícitos para que BabelCraft detecte la identidad correcta
    # (el merge incluye datapacks de otros namespaces que pueden confundir la detección).
    try:
        idx = json.loads((PACK_DIR / "modrinth.index.json").read_text(encoding="utf-8"))
        version = idx.get("versionId") or "1.0.0"
    except Exception:
        version = "1.0.0"
    (MERGED_DIR / "fabric.mod.json").write_text(json.dumps({
        "schemaVersion": 1,
        "id": "cobblemon",
        "version": str(version),
        "name": "Cobbleverse",
        "description": "Merged Cobbleverse source (Cobblemon + overrides) for BabelCraft conversion",
        "environment": "*"
    }, indent=2), encoding="utf-8")

    (MERGED_DIR / "pack.mcmeta").write_text(json.dumps({
        "pack": {"pack_format": 34, "description": "Cobbleverse merged source for BabelCraft"}
    }, indent=2), encoding="utf-8")

    return MERGED_DIR


def main() -> int:
    if not BASE_JAR.exists():
        print(f"ERROR: no se encuentra jar base: {BASE_JAR}")
        return 1
    if not PACK_DIR.exists():
        print(f"ERROR: no se encuentra pack extraído: {PACK_DIR}")
        return 1

    merged = build_merged_source()
    print(f"\nFuente fusionada: {merged}")

    print("\nIniciando conversión con BabelCraft...")
    conv = babelcraft.convert(
        str(merged),
        str(OUT_DIR),
        # Priorizar fidelidad visual; usar atlas para entidades por rendimiento
        atlas=True,
        placeholders=False,
        thin=True,
        prune_bones=True,
        minify=True,
        report=str(OUT_DIR / "REPORT.md"),
    )

    print("\n=== RESUMEN ===")
    summary = conv.summary() if hasattr(conv, "summary") else {}
    for k, v in summary.items():
        print(f"{k}: {v}")
    print(f"addon: {getattr(conv, 'addon_path', '')}")
    print(f"report: {getattr(conv, 'report_path', '')}")
    errs = getattr(conv, 'errors', []) or []
    warns = getattr(conv, 'warnings', []) or []
    print(f"errors: {len(errs)} warnings: {len(warns)}")
    if errs:
        print("\nPrimeros errores:")
        for e in errs[:20]:
            try:
                print(f"- [{getattr(e,'code','')}] {getattr(e,'path','')}: {getattr(e,'message','')}")
            except Exception:
                print(f"- {e}")
    return 0 if not errs else 1


if __name__ == "__main__":
    raise SystemExit(main())
