"""Fase textures: copia de PNGs + registro en los índices del juego.

Qué hace:
  - Descubre todas las texturas referenciadas (por modelos, item
    definitions y blockstates) y las copia a
    RP/textures/<ns>/{block,item,entity}/<nombre>.png.
  - Recorta el primer fotograma de las animadas (`.png.mcmeta`): Bedrock
    no soporta tiras verticales en items/bloques custom — sin recortar,
    la textura entera se muestra aplastada.
  - Reduce a `--max-texture` px por vecino más próximo (pixel art).
  - Registra shortnames en item_texture.json / terrain_texture.json: los
    índices que el juego EXIGE y que conectan items/bloques con sus PNG.

Los PNGs se leen con el códec propio (paletas de 1/2/4 bits incluidas)
para decidir render_method (opaque / alpha_test / blend) según el alfa
real del arte, no a ciegas.
"""

from __future__ import annotations

from ..model import Kind, Status
from ..mappings import namespace_of
from ..pngcodec import decode_png, downscale_png, encode_png
from .models import iter_model_texture_refs, resolve_model


def convert(ctx) -> None:
    mod, writer, result = ctx.mod, ctx.writer, ctx.result
    ns = ctx.ns

    # --- Recopilar ids de textura referenciados por el contenido.
    refs: set[str] = set()
    for path in mod.source.glob(f"assets/{ns}/models/"):
        if not path.endswith(".json"):
            continue
        model = resolve_model(ctx, path)
        if model:
            refs |= iter_model_texture_refs(model)
    for path in mod.source.glob(f"assets/{ns}/blockstates/"):
        if not path.endswith(".json"):
            continue
        data = mod.source.read_json_or(path) or {}
        refs |= _refs_from_blockstate(ctx, data)
    # 1.21.2+ movió los blockstates a assets/<ns>/blocks/ con la misma forma.
    for path in mod.source.glob(f"assets/{ns}/blocks/"):
        if not path.endswith(".json"):
            continue
        data = mod.source.read_json_or(path) or {}
        refs |= _refs_from_blockstate(ctx, data)

    if not refs:
        # Sin referencias: copiar en bloque (mods con arte suelto).
        for path in mod.source.glob(f"assets/{ns}/textures/"):
            if path.endswith(".png"):
                tex_id = _tex_id_from_path(path, ns)
                if tex_id:
                    refs.add(tex_id)

    for tex_id in sorted(refs):
        src_path = _texture_source_path(mod, tex_id)
        e = result.entry(src_path or tex_id, Kind.TEXTURE)
        if src_path is None or not mod.source.exists(src_path):
            e.status = Status.RESIDUE
            e.note(f"textura referenciada pero ausente: {tex_id}")
            continue

        raw = mod.source.read_bytes(src_path)
        notes: list[str] = []
        png = decode_png(raw)
        if png is None:
            # PNG que el códec no entiende (entrelazado, etc.): copia tal cual.
            writer.rp_blob(_rp_path(ns, tex_id), raw)
            e.status = Status.ADAPTED
            e.note("PNG no legible por el códec: se copia sin analizar (sin render_method derivado)")
            ctx.tex_rpaths[tex_id] = _rp_path(ns, tex_id)[:-4]
            ctx.tex_copied.add(tex_id)
            _register(writer, tex_id, _rp_path(ns, tex_id)[:-4])
            continue

        # Animada: recortar al primer fotograma.
        mcmeta = src_path + ".mcmeta"
        if mod.source.exists(mcmeta):
            if png.height > png.width:
                png = _first_frame(png)
                notes.append("textura animada: se usa solo el primer fotograma (Bedrock no soporta tiras aquí)")
            else:
                notes.append("textura animada (.mcmeta): revisa flipbook manual en terrain_texture.json")

        # Reducción.
        if ctx.opts.max_texture and max(png.width, png.height) > ctx.opts.max_texture:
            png = downscale_png(png, ctx.opts.max_texture)
            notes.append(f"reducida a {ctx.opts.max_texture}px de lado mayor")

        writer.rp_blob(_rp_path(ns, tex_id), encode_png(png.width, png.height, png.pixels))
        ctx.tex_rpaths[tex_id] = _rp_path(ns, tex_id)[:-4]  # sin extensión
        ctx.tex_copied.add(tex_id)
        ctx.tex_stats[tex_id] = _stats(png)
        _register(writer, tex_id, _rp_path(ns, tex_id)[:-4])

        e.status = Status.CONVERTED if not notes else Status.ADAPTED
        e.notes.extend(notes)


# ---------------------------------------------------------------------------


def shortname_for(tex_id: str) -> str:
    """`ns:item/ruby` -> shortname seguro para los índices (`ns_item_ruby`)."""
    from ..model import slug

    ref = tex_id.split(":", 1)[1] if ":" in tex_id else tex_id
    ns = tex_id.split(":", 1)[0] if ":" in tex_id else "babelcraft"
    return f"{ns}_{slug(ref.replace('/', '_'))}"


def _register(writer, tex_id: str, rpath_noext: str) -> None:
    """Registra la textura en el índice que el juego exige según su carpeta."""
    ref = tex_id.split(":", 1)[1] if ":" in tex_id else tex_id
    short = shortname_for(tex_id)
    if ref.startswith("item/"):
        writer.add_item_texture(short, rpath_noext)
    elif ref.startswith("block/"):
        writer.add_terrain_texture(short, rpath_noext)


def _stats(png):
    from ..pngcodec import texture_stats

    return texture_stats(png)


def _first_frame(png):
    from ..pngcodec import Png

    w = png.width
    px = png.pixels[: w * w * 4]
    return Png(w, w, px)


def _tex_id_from_path(path: str, ns: str) -> str | None:
    """`assets/ns/textures/block/ruby.png` -> `ns:block/ruby`."""
    rest = path[len(f"assets/{ns}/textures/") :]
    if rest.endswith(".png"):
        rest = rest[:-4]
    if not rest:
        return None
    return f"{ns}:{rest}"


def _rp_path(ns: str, tex_id: str) -> str:
    """`ns:block/ruby` -> `textures/<ns>/block/ruby.png` (ruta RP)."""
    ref = tex_id.split(":", 1)[1] if ":" in tex_id else tex_id
    return f"textures/{ns}/{ref}.png"


def _texture_source_path(mod, tex_id: str) -> str | None:
    """Ruta real del PNG dentro del jar. Busca en su namespace y en el nuestro."""
    ns = namespace_of(tex_id)
    ref = tex_id.split(":", 1)[1] if ":" in tex_id else tex_id
    for candidate_ns in (ns, mod.namespace):
        p = f"assets/{candidate_ns}/textures/{ref}.png"
        if mod.source.exists(p):
            return p
    # textura vanilla referenciada: no está en el jar
    return None


def _refs_from_blockstate(ctx, data) -> set[str]:
    refs: set[str] = set()
    if isinstance(data, dict):
        variants = data.get("variants")
        if isinstance(variants, dict):
            for v in variants.values():
                for entry in _as_list(v):
                    model = entry.get("model") if isinstance(entry, dict) else None
                    if model:
                        refs |= _model_refs(ctx, model)
        for part in _as_list(data.get("multipart")):
            if isinstance(part, dict):
                for entry in _as_list(part.get("apply")):
                    model = entry.get("model") if isinstance(entry, dict) else None
                    if model:
                        refs |= _model_refs(ctx, model)
    return refs


def _model_refs(ctx, model_id: str) -> set[str]:
    """Refs de textura de un modelo referenciado por un blockstate."""
    ns, _, ref = model_id.partition(":")
    path = f"assets/{ns or ctx.ns}/models/{ref}.json"
    if not ctx.mod.source.exists(path):
        return set()
    model = resolve_model(ctx, path)
    return iter_model_texture_refs(model) if model else set()


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]
