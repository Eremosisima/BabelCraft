"""Script de diagnóstico para entender por qué no se generan entidades."""
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from babelcraft.source import Source
from babelcraft.converters.entities import _find_texture, _build_entity

# Abrir el jar
jar_path = "out/cobbleverse/Cobblemon-fabric-1.7.3+1.21.1.jar"
print(f"Abriendo {jar_path}...")

# Crear un contexto mínimo
class MinimalCtx:
    def __init__(self, mod):
        self.mod = mod
        self.ns = "cobblemon"
        self._tex_cache = {}
        self.result = type('obj', (object,), {'entries': []})()
    
    def get_texture_candidates(self):
        """Devuelve un índice stem -> [rutas] de todas las texturas disponibles."""
        if self._tex_cache:
            return self._tex_cache
        
        for path in self.mod.walk():
            if not path.endswith(".png"):
                continue
            stem = path.rsplit("/", 1)[-1][:-4].lower()
            if stem not in self._tex_cache:
                self._tex_cache[stem] = []
            self._tex_cache[stem].append(path)
        
        return self._tex_cache

# Cargar el mod
mod = Source(jar_path)
ctx = MinimalCtx(mod)

# Construir el índice de texturas
idx = ctx.get_texture_candidates()
print(f"\nTotal de texturas indexadas: {sum(len(v) for v in idx.values())}")
print(f"Stems únicos: {len(idx.keys())}")

# Buscar bulbasaur específicamente
print("\n=== Búsqueda de bulbasaur ===")
if "bulbasaur" in idx:
    print(f"[OK] Encontradas {len(idx['bulbasaur'])} texturas para 'bulbasaur':")
    for path in idx['bulbasaur'][:5]:
        print(f"  - {path}")
else:
    print("[ERROR] No se encontraron texturas para 'bulbasaur'")

# Probar _find_texture con un modelo de ejemplo
print("\n=== Prueba de _find_texture ===")
geo_path = "assets/cobblemon/bedrock/pokemon/models/0001_bulbasaur/bulbasaur.geo.json"
if mod.exists(geo_path):
    print(f"[OK] Modelo encontrado: {geo_path}")
    
    # Leer la geometría
    import json
    geo_data = json.loads(mod.read_bytes(geo_path))
    
    # Buscar textura
    tex_path = _find_texture(ctx, "bulbasaur", geo_data)
    if tex_path:
        print(f"[OK] Textura encontrada: {tex_path}")
    else:
        print("[ERROR] No se encontró textura para bulbasaur")
        print("\n=== Debug: Patrones de búsqueda ===")
        print("Patrones estándar:")
        for pattern in [
            f"assets/{ctx.ns}/textures/entity/bulbasaur.png",
            f"assets/{ctx.ns}/textures/entity/bulbasaur/bulbasaur.png",
            f"assets/{ctx.ns}/textures/models/entity/bulbasaur.png",
            f"assets/{ctx.ns}/textures/entity/bulbasaur.png",
        ]:
            exists = mod.exists(pattern)
            print(f"  {pattern}: {'[OK]' if exists else '[X]'}")
else:
    print(f"[ERROR] Modelo no encontrado: {geo_path}")

print("\n=== Resumen ===")
print(f"Texturas en índice: {len(idx)}")
print(f"¿'bulbasaur' en índice?: {'bulbasaur' in idx}")
if "bulbasaur" in idx:
    print(f"Rutas de bulbasaur: {idx['bulbasaur']}")
