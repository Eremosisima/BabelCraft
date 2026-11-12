#!/usr/bin/env python3
"""Test conversion script."""

import sys
import json
import zipfile
import tempfile
import os

sys.path.insert(0, '.')
sys.path.insert(0, 'tests')

from conftest import build_minimod
import babelcraft

files = build_minimod()
jar_path = os.path.join(tempfile.gettempdir(), 'minimod.jar')
with zipfile.ZipFile(jar_path, 'w') as z:
    for name, data in files.items():
        z.writestr(name, data)

out_dir = 'out'
conv = babelcraft.convert(jar_path, out_dir, variant='mobile')
s = conv.summary()
print("Addon:", s["addon"])
print("Errors:", len(conv.errors))
print("Warnings:", len(conv.warnings))
print("Residue:", s["residue"])
print("Converted:", s["converted"])
print("Adapted:", s["adapted"])
