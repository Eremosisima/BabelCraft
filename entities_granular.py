#!/usr/bin/env python3
"""Diagnóstico granular de la fase entities para identificar cuelgues."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def main():
    print("=" * 70)
    print("DIAGNÓSTICO GRANULAR DE ENTITIES")
    print("=" * 70, flush=True)
    
    # Cargar mod
    print("\n[1] Cargando mod...", flush=True)
    t0 = time.time()
    from babelcraft.source import load_mod
    mod = load_mod("out/cobbleverse/Cobblemon-fabric-1.7.3+1.21.1.jar")
    print(f"  Completado en {time.time()-t0:.1f}s", flush=True)
    
    # Crear contexto
    print("\n[2] Creando contexto...", flush=True)
    from babelcraft.converters import Ctx, Options
    from babelcraft.model import ConversionResult, Overrides
    from babelcraft.pack import AddonWriter
    
    output_dir = Path("out/cobblemon_entities_granular")
    output_dir.mkdir(parents=True, exist_ok=True)
    writer = AddonWriter(str(output_dir), mod.namespace, mod.name, mod.version)
    result = ConversionResult()
    opts = Options()
    overrides = Overrides()
    ctx = Ctx(mod, writer, result, overrides, opts)
    
    # Ejecutar fases previas
    print("\n[3] Ejecutando fases previas...", flush=True)
    from babelcraft.converters import lang, textures, models, loot, items, blocks, recipes
    
    for name, module in [
        ("lang", lang),
        ("textures", textures),
        ("models", models),
        ("loot", loot),
        ("items", items),
        ("blocks", blocks),
        ("recipes", recipes),
    ]:
        t0 = time.time()
        print(f"  {name}...", end=" ", flush=True)
        module.convert(ctx)
        print(f"{time.time()-t0:.1f}s", flush=True)
    
    # Ahora diagnosticar entities con progreso detallado
    print("\n[4] Diagnóstico granular de entities...", flush=True)
    from babelcraft.converters import entities
    
    ns = mod.namespace
    
    # Contar geometrías
    print("  Contando geometrías...", flush=True)
    geo_files = []
    cobblemon_prefix = entities._COBBLEMON_LAYOUT.format(ns) + "/"
    for path in mod.source.glob(cobblemon_prefix):
        if path.endswith(".geo.json") and "/models/" in path:
            geo_files.append(path)
    
    print(f"  Total de geometrías: {len(geo_files)}", flush=True)
    
    # Procesar solo las primeras 5 con diagnóstico detallado
    print("\n  Procesando primeras 5 geometrías...", flush=True)
    seen = set()
    count = 0
    
    for i, path in enumerate(geo_files[:10]):
        if count >= 5:
            break
        
        if not path.endswith(".json"):
            continue
        
        name = entities._geo_name(path)
        if not name or name in seen:
            continue
        seen.add(name)
        
        print(f"\n  [{count+1}/5] {name}", flush=True)
        t_entity = time.time()
        
        # Llamar a _build_entity con timeout
        print(f"    Llamando _build_entity...", flush=True)
        t0 = time.time()
        
        # Usar threading para implementar timeout
        import threading
        import queue
        
        result_queue = queue.Queue()
        
        def build_with_timeout():
            try:
                rec = entities._build_entity(ctx, path, name)
                result_queue.put(("OK", rec, None))
            except Exception as e:
                result_queue.put(("ERROR", None, e))
        
        thread = threading.Thread(target=build_with_timeout)
        thread.daemon = True
        thread.start()
        
        try:
            status, rec, error = result_queue.get(timeout=30)
            elapsed = time.time() - t0
            
            if status == "OK":
                print(f"    _build_entity OK en {elapsed:.1f}s", flush=True)
                if rec:
                    print(f"      Tiene textura: {rec.get('texture_path') is not None}", flush=True)
                    print(f"      Tiene animaciones: {rec.get('anims_doc') is not None}", flush=True)
                else:
                    print(f"      rec es None (entidad omitida)", flush=True)
            else:
                print(f"    _build_entity ERROR en {elapsed:.1f}s: {error}", flush=True)
                
        except queue.Empty:
            elapsed = time.time() - t0
            print(f"    _build_entity TIMEOUT después de {elapsed:.1f}s", flush=True)
            print(f"    Interrumpiendo...", flush=True)
            break
        
        count += 1
    
    print(f"\n  Procesadas: {count} entidades", flush=True)
    print(f"  Total entradas en result: {len(ctx.result.entries)}", flush=True)
    
    print("\n" + "=" * 70)
    print("DIAGNÓSTICO COMPLETADO")
    print("=" * 70, flush=True)

if __name__ == "__main__":
    main()
