#!/usr/bin/env python3
"""Test script para validar el addon de prueba."""

import sys
import json
import zipfile
import tempfile
import os

sys.path.insert(0, '.')
sys.path.insert(0, 'tests')

from conftest import build_minimod
import babelcraft

# Build minimod
files = build_minimod()
jar_path = os.path.join(tempfile.gettempdir(), 'minimod.jar')
with zipfile.ZipFile(jar_path, 'w') as z:
    for name, data in files.items():
        z.writestr(name, data)

out_dir = 'out'
print('Iniciando conversion...')
conv = babelcraft.convert(jar_path, out_dir, variant='mobile')
s = conv.summary()

print(f'\n=== RESULTADO ===')
print(f'Addon: {s["addon"]}')
print(f'Errores: {len(conv.errors)}')
print(f'Warnings: {len(conv.warnings)}')
print(f'Residuos: {s["residue"]}')
print(f'Convertidos: {s["converted"]}')
print(f'Adaptados: {s["adapted"]}')

if conv.errors:
    print('\n=== ERRORES ===')
    for err in conv.errors[:10]:
        print(f'  - {err}')

print('\n=== ARCHIVOS GENERADOS ===')
addon_path = s["addon"]
if addon_path and os.path.exists(addon_path):
    with zipfile.ZipFile(addon_path, 'r') as zf:
        for name in sorted(zf.namelist())[:30]:
            print(f'  {name}')
        if len(zf.namelist()) > 30:
            print(f'  ... y {len(zf.namelist()) - 30} mas')
