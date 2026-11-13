"""Genera grafos de cobertura y referencias para una conversión BabelCraft.

Uso:
  py generate_conversion_graphs.py --report out/cobbleverse_converted/REPORT.md --addon-dir out/cobbleverse_converted --out out/cobbleverse_converted/graphs

Produce archivos Markdown/JSON con:
- Cobertura por tipo/estado (desde REPORT.md)
- Referencias de assets en RP/BP (animaciones, geometrías, texturas, controllers)
- Resumen de issues de referencias detectadas
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path


def parse_coverage_table(report_text: str):
    rows = []
    in_table = False
    for line in report_text.splitlines():
        if line.strip().startswith("| Tipo | Convertido | Adaptado | Residuo | Total |"):
            in_table = True
            continue
        if in_table:
            if not line.strip().startswith("|"):
                break
            if line.strip().startswith("|---"):
                continue
            parts = [p.strip() for p in line.strip().strip("|").split("|")]
            if len(parts) != 5:
                continue
            tipo = parts[0].replace("**", "").strip()
            if tipo.lower() == "total":
                continue
            try:
                vals = [int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])]
            except Exception:
                continue
            rows.append({"tipo": tipo, "convertido": vals[0], "adaptado": vals[1], "residuo": vals[2], "total": vals[3]})
    return rows


def parse_verdict(report_text: str):
    m = re.search(r"\*\*(\d+)\s+error\(es\) del validador\*\*", report_text)
    errors = int(m.group(1)) if m else None
    m2 = re.search(r"\*\*(\d+)\s+aviso\(s\)\*\*", report_text)
    warnings = int(m2.group(1)) if m2 else None
    return {"errors": errors, "warnings": warnings}


def scan_references(addon_dir: Path):
    refs = {
        "animations_defined": set(),
        "animations_referenced": set(),
        "geometries_defined": set(),
        "geometries_referenced": set(),
        "textures_defined": set(),
        "textures_referenced": set(),
        "render_controllers_defined": set(),
        "render_controllers_referenced": set(),
        "animation_controllers_defined": set(),
        "animation_controllers_referenced": set(),
    }
    file_counts = Counter()

    def walk_json(root: Path):
        for p in root.rglob("*.json"):
            yield p

    # RP scan
    for rp in addon_dir.glob("RP_*"):
        for p in walk_json(rp):
            file_counts["rp_json"] += 1
            try:
                data = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue
            rel = str(p.relative_to(addon_dir)).replace("\\", "/")
            # animations
            if "/animations/" in rel:
                anims = data.get("animations", {}) if isinstance(data, dict) else {}
                if isinstance(anims, dict):
                    refs["animations_defined"].update([k for k in anims.keys() if isinstance(k, str)])
            # geometry files
            if "/models/" in rel and isinstance(data, dict):
                geos = data.get("minecraft:geometry")
                if isinstance(geos, list):
                    for g in geos:
                        if isinstance(g, dict):
                            desc = g.get("description", {})
                            if isinstance(desc, dict) and isinstance(desc.get("identifier"), str):
                                refs["geometries_defined"].add(desc["identifier"])
                elif isinstance(geos, dict):
                    desc = geos.get("description", {})
                    if isinstance(desc, dict) and isinstance(desc.get("identifier"), str):
                        refs["geometries_defined"].add(desc["identifier"])
            # render controllers
            if "/render_controllers/" in rel and isinstance(data, dict):
                rcs = data.get("render_controllers", {})
                if isinstance(rcs, dict):
                    refs["render_controllers_defined"].update([k for k in rcs.keys() if isinstance(k, str)])
            # animation controllers
            if "/animation_controllers/" in rel and isinstance(data, dict):
                acs = data.get("animation_controllers", {})
                if isinstance(acs, dict):
                    refs["animation_controllers_defined"].update([k for k in acs.keys() if isinstance(k, str)])

            # references in client entities / attachables
            if "/entity/" in rel or "/attachables/" in rel:
                txt = json.dumps(data, ensure_ascii=False)
                for m in re.finditer(r"\"(animation\.[^\"]+)\"", txt):
                    refs["animations_referenced"].add(m.group(1))
                for m in re.finditer(r"\"(controller\.animation\.[^\"]+)\"", txt):
                    refs["animation_controllers_referenced"].add(m.group(1))
                for m in re.finditer(r"\"(controller\.render\.[^\"]+)\"", txt):
                    refs["render_controllers_referenced"].add(m.group(1))
                for m in re.finditer(r"\"(geometry\.[^\"]+)\"", txt):
                    refs["geometries_referenced"].add(m.group(1))
                for m in re.finditer(r"\"(textures/[^\"]+)\"", txt):
                    refs["textures_referenced"].add(m.group(1))

        # texture files
        for p in rp.rglob("*.png"):
            rel = str(p.relative_to(rp)).replace("\\", "/")
            refs["textures_defined"].add(rel[:-4] if rel.endswith(".png") else rel)

    # BP scan for entity refs
    for bp in addon_dir.glob("BP_*"):
        for p in walk_json(bp):
            file_counts["bp_json"] += 1

    def diff(refd, defined):
        return sorted([x for x in refd if x not in defined])

    missing = {
        "animations": diff(refs["animations_referenced"], refs["animations_defined"]),
        "geometries": diff(refs["geometries_referenced"], refs["geometries_defined"]),
        "render_controllers": diff(refs["render_controllers_referenced"], refs["render_controllers_defined"]),
        "animation_controllers": diff(refs["animation_controllers_referenced"], refs["animation_controllers_defined"]),
    }
    # textures: referenced as textures/... (no ext) vs defined relative paths in RP
    tex_defined = set(refs["textures_defined"])
    tex_missing = sorted([t for t in refs["textures_referenced"] if t not in tex_defined and not t.endswith(".png")])
    missing["textures"] = tex_missing

    return refs, missing, file_counts


def write_outputs(out_dir: Path, coverage_rows, verdict, refs, missing, file_counts):
    out_dir.mkdir(parents=True, exist_ok=True)

    # coverage.json / md
    (out_dir / "coverage.json").write_text(json.dumps({"verdict": verdict, "rows": coverage_rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    cov_lines = ["# Grafo de cobertura", "", f"- Errores validador: {verdict.get('errors')}", f"- Avisos: {verdict.get('warnings')}", "", "| Tipo | Convertido | Adaptado | Residuo | Total |", "|---|---:|---:|---:|---:|"]
    totals = Counter()
    for r in coverage_rows:
        cov_lines.append(f"| {r['tipo']} | {r['convertido']} | {r['adaptado']} | {r['residuo']} | {r['total']} |")
        for k in ("convertido","adaptado","residuo","total"):
            totals[k] += r[k]
    cov_lines.append(f"| **Total** | **{totals['convertido']}** | **{totals['adaptado']}** | **{totals['residuo']}** | **{totals['total']}** |")
    (out_dir / "coverage.md").write_text("\n".join(cov_lines) + "\n", encoding="utf-8")

    # references
    ref_summary = {
        "counts": {k: (len(v) if isinstance(v, set) else v) for k, v in refs.items()},
        "missing_counts": {k: len(v) for k, v in missing.items()},
        "file_counts": dict(file_counts),
    }
    (out_dir / "references_summary.json").write_text(json.dumps(ref_summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "references_missing.json").write_text(json.dumps(missing, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# Grafo de referencias (resumen)", "", "## Conteos", ""]
    for k, v in ref_summary["counts"].items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Referencias faltantes (conteos)", ""]
    for k, v in ref_summary["missing_counts"].items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Muestras de faltantes", ""]
    for k, arr in missing.items():
        lines.append(f"### {k}")
        if not arr:
            lines.append("- (ninguna)")
        else:
            for item in arr[:30]:
                lines.append(f"- `{item}`")
            if len(arr) > 30:
                lines.append(f"- ... (+{len(arr)-30} más)")
        lines.append("")
    (out_dir / "references.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--addon-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    report_text = Path(args.report).read_text(encoding="utf-8", errors="ignore")
    coverage_rows = parse_coverage_table(report_text)
    verdict = parse_verdict(report_text)
    refs, missing, file_counts = scan_references(Path(args.addon_dir))
    write_outputs(Path(args.out), coverage_rows, verdict, refs, missing, file_counts)
    print(f"Wrote graphs to {args.out}")
    print(json.dumps({"coverage_rows": len(coverage_rows), "missing": {k: len(v) for k, v in missing.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
