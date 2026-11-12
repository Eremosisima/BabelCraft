# BabelCraft Skill (Java → Bedrock Converter)

Use this skill/package to convert Minecraft **Java Edition** mods, datapacks, or resource packs into **Bedrock Edition** addons (`.mcaddon`).

## What it does
- Converts declarative content: blocks, items, recipes, loot tables, models/geometries, textures, animations (including GeckoLib-based assets), sounds, and language files.
- Generates RP/BP structures and a conversion report documenting converted/adapted/residue items.
- Follows a "never fake" principle: unsupported logic is reported as residue instead of invented behavior.

## How to use (CLI/scripts)
From the `BabelCraft/` directory:

```bash
# Install (optional)
pip install -e .

# Convert a mod/jar/zip/folder
python -m babelcraft convert <source.jar|source.zip|folder> -o <output_dir>

# Examples
python -m babelcraft convert MiMod.jar -o salida
python -m babelcraft convert MiMod.jar -o salida --variant mobile --placeholders
```

## Useful options
- `--variant mobile|desktop`: performance-oriented presets (atlas/despawn settings)
- `--max-texture PX`: downscale textures
- `--atlas` / `--no-atlas`: control entity texture atlas
- `--placeholders`: generate placeholder art when missing (otherwise residue)
- `--overrides overrides.json`: provide values not inferable from Java bytecode (food, hardness, health, etc.)
- `--report <path>`: custom report path

## Outputs
- `<output_dir>/<namespace>.mcaddon` (when packaging succeeds)
- `<output_dir>/REPORT.md` with per-file conversion status and reasons
- BP/RP folders with generated content

## For agents/automation
- Prefer running conversion via CLI and then inspect `REPORT.md` for errors/residues.
- Validate in Bedrock after import; use report + content logs to iterate on converter fixes.
- Extend mod-specific mechanics via `babelcraft.mechanics` (plugin/converter hooks) rather than hardcoding into base converters.

## Limitations
- Java bytecode/game logic is not automatically translated (combat systems, custom GUIs/AI/mechanics, complex worldgen, etc.).
- Complex mods may require manual follow-up or specialized mechanics converters.
