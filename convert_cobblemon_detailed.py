#!/usr/bin/env python3
"""Conversor BabelCraft para Cobblemon con logging detallado."""
import sys
import os
import traceback
from pathlib import Path

# Forzar UTF-8 para output
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

print("=" * 80)
print("CONVERSIÓN COBBLEMON CON LOGGING DETALLADO")
print("=" * 80)
sys.stdout.flush()

# Asegurar que babelcraft esté en el path
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))
print(f"[DEBUG] Python path actualizado: {script_dir}")
sys.stdout.flush()

# Verificar que el JAR existe
jar_path = Path("out/cobbleverse/Cobblemon-fabric-1.7.3+1.21.1.jar")
output_dir = Path("out/cobblemon")

print(f"[DEBUG] JAR path: {jar_path}")
print(f"[DEBUG] JAR existe: {jar_path.exists()}")
print(f"[DEBUG] JAR tamaño: {jar_path.stat().st_size if jar_path.exists() else 'N/A'} bytes")
print(f"[DEBUG] Output dir: {output_dir}")
sys.stdout.flush()

if not jar_path.exists():
    print(f"[ERROR] JAR no encontrado: {jar_path}")
    sys.exit(1)

print(f"[1/4] Importando babelcraft...")
sys.stdout.flush()

try:
    from babelcraft import convert
    print(f"[OK] babelcraft importado correctamente")
except Exception as e:
    print(f"[ERROR] No se pudo importar babelcraft: {e}")
    traceback.print_exc()
    sys.exit(1)

sys.stdout.flush()

print(f"[2/4] Iniciando conversión...")
print(f"  Entrada: {jar_path}")
print(f"  Salida: {output_dir}")
sys.stdout.flush()

try:
    conversion = convert(str(jar_path), str(output_dir))
    print(f"[3/4] Conversión completada exitosamente")
    print(f"  - Addon: {conversion.addon_path}")
    print(f"  - Report: {conversion.report_path}")
    
    # Resumen
    summary = conversion.summary()
    print(f"[4/4] Resumen de conversión:")
    print(f"  - Namespace: {summary.get('namespace', 'N/A')}")
    print(f"  - Loader: {summary.get('loader', 'N/A')}")
    print(f"  - Name: {summary.get('name', 'N/A')}")
    print(f"  - BP files: {summary.get('bp_files', 0)}")
    print(f"  - RP files: {summary.get('rp_files', 0)}")
    print(f"  - Errors: {len(conversion.errors)}")
    print(f"  - Warnings: {len(conversion.warnings)}")
    
    if conversion.errors:
        print(f"\n[ERRORES] ({len(conversion.errors)} total):")
        for i, err in enumerate(conversion.errors[:20], 1):
            print(f"  {i}. {err}")
        if len(conversion.errors) > 20:
            print(f"  ... y {len(conversion.errors) - 20} errores más")
    
    if conversion.warnings:
        print(f"\n[WARNINGS] ({len(conversion.warnings)} total, mostrando primeros 10):")
        for i, warn in enumerate(conversion.warnings[:10], 1):
            print(f"  {i}. {warn}")
    
    # Verificar que se generaron archivos
    print(f"\n[VERIFICACIÓN] Archivos generados:")
    if output_dir.exists():
        files = list(output_dir.iterdir())
        print(f"  - Directorio existe: {output_dir}")
        print(f"  - Archivos: {len(files)}")
        for f in files[:10]:
            print(f"    - {f.name}")
    else:
        print(f"  [ERROR] Directorio de salida NO existe: {output_dir}")
    
    print(f"\n[COMPLETADO] Conversión finalizada")
    sys.exit(0)
    
except Exception as e:
    print(f"\n[ERROR FATAL] Excepción durante la conversión:")
    print(f"  Tipo: {type(e).__name__}")
    print(f"  Mensaje: {e}")
    print(f"\n[TRACEBACK]:")
    traceback.print_exc()
    sys.exit(1)
