#!/usr/bin/env python3
"""Script de diagnóstico para analizar el JAR de Cobblemon."""
import sys
import zipfile
import time
from pathlib import Path
from collections import Counter

def analyze_jar():
    jar_path = Path("out/cobbleverse/Cobblemon-fabric-1.7.3+1.21.1.jar")
    
    print("=" * 70)
    print("DIAGNÓSTICO DE JAR COBBLEMON")
    print("=" * 70)
    
    print(f"\n[1/6] Abriendo JAR: {jar_path}")
    print(f"  Tamaño: {jar_path.stat().st_size / 1024 / 1024:.2f} MB")
    sys.stdout.flush()
    
    start = time.time()
    with zipfile.ZipFile(jar_path, 'r') as zf:
        files = zf.namelist()
        elapsed = time.time() - start
        print(f"  Archivos listados: {len(files)} en {elapsed:.2f}s")
    sys.stdout.flush()
    
    print(f"\n[2/6] Analizando tipos de archivos...")
    ext_counter = Counter()
    path_counter = Counter()
    
    for f in files:
        ext = Path(f).suffix
        ext_counter[ext] += 1
        
        # Contar por directorio principal
        parts = f.split('/')
        if len(parts) >= 2:
            path_counter[parts[0]] += 1
    
    print(f"  Extensiones más comunes:")
    for ext, count in ext_counter.most_common(15):
        print(f"    {ext:15s}: {count:6d}")
    
    print(f"\n  Directorios principales:")
    for path, count in path_counter.most_common(15):
        print(f"    {path:30s}: {count:6d}")
    sys.stdout.flush()
    
    print(f"\n[3/6] Analizando clases Java (.class)...")
    class_files = [f for f in files if f.endswith('.class')]
    print(f"  Total: {len(class_files)}")
    print(f"  Tamaño total: {sum(zf.getinfo(f).file_size for f in class_files) / 1024:.0f} KB")
    
    # Mostrar algunos ejemplos
    print(f"  Ejemplos:")
    for cf in class_files[:10]:
        print(f"    - {cf}")
    sys.stdout.flush()
    
    print(f"\n[4/6] Analizando texturas (.png)...")
    png_files = [f for f in files if f.endswith('.png')]
    print(f"  Total: {len(png_files)}")
    print(f"  Tamaño total: {sum(zf.getinfo(f).file_size for f in png_files) / 1024 / 1024:.2f} MB")
    
    # Distribución por directorio
    png_dirs = Counter()
    for f in png_files:
        parts = f.split('/')
        if len(parts) >= 3:
            png_dirs['/'.join(parts[:3])] += 1
    
    print(f"  Distribución por directorio:")
    for path, count in png_dirs.most_common(10):
        print(f"    {path:50s}: {count:6d}")
    sys.stdout.flush()
    
    print(f"\n[5/6] Analizando JSON...")
    json_files = [f for f in files if f.endswith('.json')]
    print(f"  Total: {len(json_files)}")
    print(f"  Tamaño total: {sum(zf.getinfo(f).file_size for f in json_files) / 1024:.0f} KB")
    
    # Categorizar JSON
    json_types = Counter()
    for f in json_files:
        if '/models/block/' in f:
            json_types['model/block'] += 1
        elif '/models/item/' in f:
            json_types['model/item'] += 1
        elif '/blockstates/' in f:
            json_types['blockstates'] += 1
        elif '/loot_tables/' in f:
            json_types['loot_tables'] += 1
        elif '/recipes/' in f:
            json_types['recipes'] += 1
        else:
            json_types['other'] += 1
    
    print(f"  Categorías:")
    for jtype, count in json_types.most_common():
        print(f"    {jtype:20s}: {count:6d}")
    sys.stdout.flush()
    
    print(f"\n[6/6] Probando lectura de archivos grandes...")
    # Encontrar los 5 archivos más grandes
    file_sizes = [(f, zf.getinfo(f).file_size) for f in files]
    file_sizes.sort(key=lambda x: x[1], reverse=True)
    
    print(f"  Archivos más grandes:")
    for fname, size in file_sizes[:5]:
        print(f"    {fname:60s}: {size / 1024 / 1024:.2f} MB")
    
    # Probar lectura del archivo más grande
    largest = file_sizes[0][0]
    print(f"\n  Probando lectura de: {largest}")
    start = time.time()
    data = zf.read(largest)
    elapsed = time.time() - start
    print(f"  Leído: {len(data) / 1024 / 1024:.2f} MB en {elapsed:.2f}s")
    sys.stdout.flush()
    
    print("\n" + "=" * 70)
    print("DIAGNÓSTICO COMPLETADO")
    print("=" * 70)

if __name__ == "__main__":
    sys.exit(analyze_jar())
