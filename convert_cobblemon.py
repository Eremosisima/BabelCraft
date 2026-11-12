#!/usr/bin/env python3
"""Conversor BabelCraft para Cobblemon."""
import sys
import os
from pathlib import Path

# Asegurar que babelcraft esté en el path
sys.path.insert(0, str(Path(__file__).parent))

from babelcraft import convert

def main():
    jar_path = Path("out/cobbleverse/Cobblemon-fabric-1.7.3+1.21.1.jar")
    output_dir = Path("out/cobblemon")
    
    print(f"[1/3] Convirtiendo {jar_path}...")
    
    try:
        conversion = convert(str(jar_path), str(output_dir))
        print(f"[2/3] Conversión completada")
        print(f"  - Addon: {conversion.addon_path}")
        print(f"  - Report: {conversion.report_path}")
        
        # Resumen
        summary = conversion.summary()
        print(f"[3/3] Resumen:")
        print(f"  - Namespace: {summary.get('namespace', 'N/A')}")
        print(f"  - Loader: {summary.get('loader', 'N/A')}")
        print(f"  - Name: {summary.get('name', 'N/A')}")
        print(f"  - BP files: {summary.get('bp_files', 0)}")
        print(f"  - RP files: {summary.get('rp_files', 0)}")
        print(f"  - Errors: {len(conversion.errors)}")
        print(f"  - Warnings: {len(conversion.warnings)}")
        
        if conversion.errors:
            print("\nErrores encontrados:")
            for err in conversion.errors[:10]:  # Solo primeros 10
                print(f"  - {err}")
        
        return 0
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
