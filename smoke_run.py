"""Smoke run del pipeline sobre el minimod (script manual, no un test)."""

import json
import sys
import tempfile

sys.path.insert(0, ".")
sys.path.insert(0, "tests")

from conftest import build_minimod

import babelcraft

files = build_minimod()
with tempfile.TemporaryDirectory() as tmp:
    conv = babelcraft.convert(files, tmp)
    s = conv.summary()
    for k in sorted(s):
        print(f"{k}: {s[k]}")
    print()
    print("--- ERRORES ---")
    for f in conv.errors:
        print(f"[{f.code}] {f.path}: {f.message}")
    print("--- AVISOS ---")
    for f in conv.warnings:
        print(f"[{f.code}] {f.path}: {f.message}")
    print("--- FASES FALLIDAS ---")
    for f in conv.result.findings:
        if f.code.startswith("phase."):
            print(f"[{f.code}] {f.path}: {f.message}")
    print()
    print("--- BP ---")
    for k in sorted(conv.writer.bp):
        print(" ", k)
    print("--- RP ---")
    for k in sorted(conv.writer.rp):
        print(" ", k)
    print("--- RESIDUOS ---")
    for e in conv.result.entries:
        if e.status.value == "residue":
            print(f"  {e.path} ({e.kind.value}): {'; '.join(e.notes)}")
