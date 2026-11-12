"""Pipeline de conversión: fases deterministas + libro de cuentas.

Orden de las fases (las dependencias van de arriba abajo):

  1. lang      — tablas de idioma (nombres para todo lo demás)
  2. textures  — copia + registro de texturas en los índices del juego
  3. models    — modelos Java -> geometría Bedrock (+ attachables)
  4. loot      — loot tables ANTES de items/blocks: ambos enganchan su
                 componente `minecraft:loot` de `ctx.loot_paths`
  5. items     — ítems custom (evidencia + overrides)
  6. blocks    — bloques custom (blockstates -> traits + geometría)
  7. recipes   — recetas (shaped/shapeless/furnace/stonecutter)
  8. entities  — entidades (GeckoLib) con optimización RAM opcional
  9. sounds    — sound_definitions.json + archivos .ogg

Cada fase es una función pura `(ctx) -> None` que escribe en el addon y
cuenta en el resultado. Ninguna fase puede romper a las demás: capturan
sus errores y los apuntan como residuo con la razón.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..model import ConversionResult, Kind, Overrides, SourceMod
from ..pack import AddonWriter
from ..pngcodec import decode_png, texture_stats
from . import blocks, entities, items, lang, loot, models, recipes, sounds, textures

# Prefijos del jar que son "meta" del mod (licencia, manifest, bytecode
# de implementación) y no contenido convertible. No se cuentan como residuo.
_META_PREFIXES = (
    "META-INF/",
    "com/",               # bytecode Java
    "cobblemon-common.accesswidener",
    "common-common-refmap.json",
    "create_block_files.py",
    "architectury.common.json",
    "fabric.mod.json",
    "neoforge.mods.toml",
    "pack.mcmeta",
)
# Carpetas con assets opcionales dentro del jar que no son del mod en sí
# sino resourcepacks embebidos (por ejemplo "resourcepacks/regionbiasforms/").
# Se saltan para no contar dos veces el mismo asset.
_EMBEDDED_RP_PREFIX = "resourcepacks/"


def _kind_for_path(path: str) -> Kind:
    """Infiere el tipo de contenido de un fichero por su ruta."""
    low = path.lower()
    if low.endswith(".geo.json"):
        return Kind.GEOMETRY
    if low.endswith(".animation.json"):
        return Kind.ANIMATION
    if low.endswith(".animation_controllers.json"):
        return Kind.ANIMATION
    if low.endswith(".particle.json"):
        return Kind.OTHER
    if low.endswith(".class"):
        return Kind.BYTECODE
    if low.startswith("data/") and "/recipe/" in low:
        return Kind.RECIPE
    if low.startswith("data/") and "/loot_table/" in low:
        return Kind.LOOT_TABLE
    if low.startswith("data/") and ("/tags/" in low or low.endswith("/tags.json")):
        return Kind.TAG
    if low.startswith("data/") and "/advancement/" in low:
        return Kind.ADVANCEMENT
    if low.startswith("data/") and "/worldgen/" in low:
        return Kind.WORLDGEN
    if low.startswith("data/") and "/function/" in low:
        return Kind.FUNCTION
    if low.startswith("data/") and "/structure/" in low:
        return Kind.STRUCTURE
    if low.startswith("assets/") and low.endswith(".lang"):
        return Kind.LANG
    if low.endswith(".ogg"):
        return Kind.SOUND
    if low.endswith(".png"):
        return Kind.TEXTURE
    if low.endswith(".json"):
        return Kind.METADATA
    return Kind.OTHER


def _reason_for_kind(kind: Kind, path: str) -> str:
    reasons = {
        Kind.GEOMETRY: "geometría fuera del árbol descubierto por el conversor",
        Kind.ANIMATION: "animación fuera del árbol descubierto por el conversor",
        Kind.BYTECODE: "código Java: la lógica del mod vive en .class, no se puede portar",
        Kind.RECIPE: "receta sin equivalente directo en Bedrock",
        Kind.LOOT_TABLE: "loot table sin equivalente directo en Bedrock",
        Kind.TAG: "tag de ítems/bloques (se resuelve en código, no en datos Bedrock)",
        Kind.ADVANCEMENT: "logro/aventura (formato Java, no portable a Bedrock)",
        Kind.WORLDGEN: "worldgen de Java (formato incompatible con Bedrock)",
        Kind.FUNCTION: "función mcfunction (solo existe en Java)",
        Kind.STRUCTURE: "estructura (.nbt, solo Java)",
        Kind.SOUND: "sonido .ogg no referenciado por sounds.json",
        Kind.TEXTURE: "textura no asociada a ningún ítem/bloque/entidad emitidos",
        Kind.METADATA: "datos de configuración del mod, no contenido de juego",
        Kind.OTHER: "fichero sin equivalente directo en Bedrock",
    }
    return reasons.get(kind, "sin equivalente directo en Bedrock")


def _account_unconverted(mod, result) -> None:
    """Barrido final: cada fichero no contabilizado queda como residuo.

    Un mod real (Cobblemon: 45000+ ficheros) deja mucho sin convertir:
    bytecode, partículas, worldgen, advancements... Cada uno queda en el
    libro de cuentas con su tipo inferido y una razón genérica. Sin este
    barrido el informe miente por omisión.
    """
    accounted = {e.path for e in result.entries}
    for path in mod.source.walk():
        if path in accounted:
            continue
        if path.startswith(_EMBEDDED_RP_PREFIX):
            continue
        if any(path.startswith(p) for p in _META_PREFIXES):
            continue
        if path == "LICENSE" or path.endswith("/LICENSE"):
            continue
        kind = _kind_for_path(path)
        reason = _reason_for_kind(kind, path)
        result.residue(path, kind, reason)


@dataclass
class Options:
    """Opciones de línea de comandos."""

    max_texture: int = 0        # 0 = no reducir; 64 = ninguna mayor de 64px
    atlas: bool = False         # atlas de texturas de entidades (1 handle)
    atlas_cell: int = 0         # tamaño de celda (0 = auto)
    variant: str = ""           # "" | mobile | desktop
    minify: bool = True
    placeholders: bool = False   # generar placeholder cuando falte arte
    thin: bool = True            # adelgazar animaciones
    prune_bones: bool = True     # podar huesos muertos
    despawn_distance: int = 0    # 0 = sin despawn por distancia
    lang_out: str = "en_US"      # idioma principal de salida


@dataclass
class Ctx:
    """Estado compartido entre fases."""

    mod: SourceMod
    writer: AddonWriter
    result: ConversionResult
    overrides: Overrides
    opts: Options

    # Registros que van llenando las fases.
    lang_tables: dict = field(default_factory=dict)   # "en_us" -> {clave: valor}
    lang_files: list = field(default_factory=list)    # rutas de entrada
    model_cache: dict = field(default_factory=dict)   # ruta modelo -> resuelto
    tex_rpaths: dict = field(default_factory=dict)    # id java -> ruta RP
    tex_stats: dict = field(default_factory=dict)     # id java -> stats
    tex_copied: set = field(default_factory=set)
    item_ids: set = field(default_factory=set)         # "ns:name" emitidos
    block_ids: set = field(default_factory=set)
    entity_ids: set = field(default_factory=set)
    block_models: dict = field(default_factory=dict)   # "ns:name" -> geometría emitida
    loot_paths: dict = field(default_factory=dict)     # "ns:path" -> ruta BP
    entity_textures: list = field(default_factory=list)  # para el atlas
    attachable_icons: dict = field(default_factory=dict)  # "ns:name" -> textura del attachable
    
    # Cache de texturas disponibles (para _find_texture).
    # Se llena la primera vez que se necesita.
    _tex_cache: dict = field(default_factory=dict)  # stem -> [rutas]
    
    def get_texture_candidates(self) -> dict[str, list[str]]:
        """Devuelve un índice stem -> [rutas] de todas las texturas disponibles.
        
        El índice se construye una sola vez y se cachea. El stem es el nombre
        del fichero sin extensión (ej: "bulbasaur" -> [".../bulbasaur.png"]).
        """
        if self._tex_cache:
            return self._tex_cache
        
        # Agrupar todas las texturas por stem.
        for path in self.mod.source.walk():
            if not path.endswith(".png"):
                continue
            stem = path.rsplit("/", 1)[-1][:-4].lower()
            if stem not in self._tex_cache:
                self._tex_cache[stem] = []
            self._tex_cache[stem].append(path)
        
        return self._tex_cache

    @property
    def ns(self) -> str:
        return self.mod.namespace

    def name_for(self, kind: str, ident: str) -> str | None:
        """Nombre legible desde el lang de Java (item./block./entity.)."""
        table = self.lang_tables.get("en_us") or {}
        ns, _, name = ident.partition(":")
        for key in (f"{kind}.{ns}.{name}", f"{kind}.{ns}.{name}.name"):
            if key in table:
                return table[key]
        return None

    def texture_rpath(self, tex_id: str) -> str | None:
        """Ruta RP de una textura, registrada por la fase textures."""
        return self.tex_rpaths.get(tex_id)

    def stats_for(self, tex_id: str) -> dict:
        if tex_id not in self.tex_stats:
            rpath = self.tex_rpaths.get(tex_id)
            png = None
            if rpath:
                data = self.writer.rp.get(rpath + ".png")
                if data:
                    png = decode_png(data)
            self.tex_stats[tex_id] = texture_stats(png)
        return self.tex_stats[tex_id]


PHASES = [
    ("lang", lang.convert),
    ("textures", textures.convert),
    ("models", models.convert),
    ("loot", loot.convert),
    ("items", items.convert),
    ("blocks", blocks.convert),
    ("recipes", recipes.convert),
    ("entities", entities.convert),
    ("sounds", sounds.convert),
]


def run(mod: SourceMod, out_dir: str, opts: Options, overrides: Overrides) -> tuple[AddonWriter, ConversionResult]:
    """Ejecuta el pipeline completo. Devuelve (escritor, resultado)."""
    writer = AddonWriter(out_dir, mod.namespace, mod.name, mod.version, minify=opts.minify)
    result = ConversionResult()
    ctx = Ctx(mod=mod, writer=writer, result=result, overrides=overrides, opts=opts)

    if opts.variant == "mobile":
        # Perfil ligero (movil): atlas de celdas pequenas, despawn agresivo.
        opts.atlas = True
        opts.atlas_cell = opts.atlas_cell or 32
        opts.despawn_distance = opts.despawn_distance or 40
    elif opts.variant == "desktop":
        opts.atlas = True
        opts.atlas_cell = opts.atlas_cell or 64
        opts.despawn_distance = opts.despawn_distance or 64

    for name, phase in PHASES:
        try:
            phase(ctx)
        except Exception as e:  # noqa: BLE001 - una fase no tumba el resto
            result.error(f"phase.{name}", name, f"fase {name} falló: {e!r}")

    # Mecánicas específicas por mod (extensión opcional, post-pipeline).
    try:
        from ..mechanics import MechanicsContext, detect_mechanics

        mech_ctx = MechanicsContext(mod=mod, writer=writer, namespace=mod.namespace)
        for converter in detect_mechanics(mod):
            try:
                converter.convert(mech_ctx)
            except Exception as e:  # noqa: BLE001
                result.error(
                    f"mechanics.{getattr(converter, 'id', 'unknown')}",
                    "mechanics",
                    f"mecánica {getattr(converter, 'id', 'unknown')} falló: {e!r}",
                )
        for note in mech_ctx.notes:
            # Registro informativo como residuo/adaptación ligera en metadatos de resultado si aplica.
            # (no interrumpe conversión)
            pass
    except Exception as e:  # noqa: BLE001
        result.error("phase.mechanics", "mechanics", f"fase mechanics falló: {e!r}")

    # Barrido final: cada fichero no contabilizado queda como residuo.
    try:
        _account_unconverted(mod, result)
    except Exception as e:  # noqa: BLE001
        result.error("phase.account", "account", f"barrido final falló: {e!r}")

    writer.addon_path = writer.finalize(pack_mcaddon=True)
    return writer, result
