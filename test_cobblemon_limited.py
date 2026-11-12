#!/usr/bin/env python3
"""Conversión de Cobblemon con límite de entidades para testing."""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def main():
    print("=" * 70)
    print("CONVERSIÓN COBBLEMON - MODO TEST (10 entidades)")
    print("=" * 70)
    
    # Cargar mod
    print("\n[1/3] Cargando mod...")
    from babelcraft.source import load_mod
    mod = load_mod("out/cobbleverse/Cobblemon-fabric-1.7.3+1.21.1.jar")
    print(f"  Namespace: {mod.namespace}")
    print(f"  Loader: {mod.loader}")
    
    # Crear contexto
    print("\n[2/3] Creando contexto...")
    output_dir = Path("out/cobblemon_test_10")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    from babelcraft.converters import Ctx, Options
    from babelcraft.model import ConversionResult, Overrides
    from babelcraft.pack import AddonWriter
    
    writer = AddonWriter(str(output_dir), mod.namespace, mod.name, mod.version)
    result = ConversionResult()
    opts = Options()
    overrides = Overrides()
    ctx = Ctx(mod, writer, result, overrides, opts)
    
    # Ejecutar fases previas
    print("\n[3/3] Ejecutando fases previas...")
    from babelcraft.converters.lang import convert as lang_convert
    from babelcraft.converters.textures import convert as textures_convert
    from babelcraft.converters.models import convert as models_convert
    from babelcraft.converters.loot import convert as loot_convert
    from babelcraft.converters.items import convert as items_convert
    from babelcraft.converters.blocks import convert as blocks_convert
    from babelcraft.converters.recipes import convert as recipes_convert
    
    phases = [
        ("lang", lang_convert),
        ("textures", textures_convert),
        ("models", models_convert),
        ("loot", loot_convert),
        ("items", items_convert),
        ("blocks", blocks_convert),
        ("recipes", recipes_convert),
    ]
    
    for name, phase in phases:
        try:
            print(f"  Ejecutando {name}...", end=" ")
            phase(ctx)
            print("OK")
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
    
    # Ejecutar entities con límite
    print("\n[4/4] Ejecutando fase entities (limitado a 10)...")
    try:
        # Modificar temporalmente la función de descubrimiento de entidades
        import babelcraft.converters.entities as entities_module
        
        original_discover = entities_module.discover_entities
        call_count = [0]
        MAX_ENTITIES = 10
        
        def limited_discover(ctx):
            """Wrapper que limita el número de entidades."""
            entities = original_discover(ctx)
            limited = entities[:MAX_ENTITIES]
            print(f"    Limitado de {len(entities)} a {len(limited)} entidades")
            return limited
        
        entities_module.discover_entities = limited_discover
        
        from babelcraft.converters.entities import convert as entities_convert
        entities_convert(ctx)
        
        # Restaurar
        entities_module.discover_entities = original_discover
        
        print(f"\n  [OK] Fase entities completada")
        print(f"  Entidades procesadas: {len(ctx.entity_ids)}")
        
        if ctx.entity_ids:
            print(f"  Ejemplos: {', '.join(list(ctx.entity_ids)[:5])}")
        
    except Exception as e:
        print(f"\n  [ERROR] Excepción en fase entities:")
        print(f"  Tipo: {type(e).__name__}")
        print(f"  Mensaje: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Generar addon
    print("\n[5/5] Generando addon...")
    try:
        addon_path = writer.finalize(pack_mcaddon=True)
        print(f"  [OK] Addon generado: {addon_path}")
        
        if Path(addon_path).exists():
            size_mb = Path(addon_path).stat().st_size / (1024 * 1024)
            print(f"  Tamaño: {size_mb:.2f} MB")
        
    except Exception as e:
        print(f"  [ERROR] No se pudo generar addon: {e}")
        import traceback
        traceback.print_exc()
    
    # Resumen final
    print("\n" + "=" * 70)
    print("RESUMEN:")
    print(f"  Archivos BP: {len(writer.bp)}")
    print(f"  Archivos RP: {len(writer.rp)}")
    print(f"  Entidades: {len(ctx.entity_ids)}")
    print(f"  Entradas totales: {len(result.entries)}")
    print("=" * 70)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
