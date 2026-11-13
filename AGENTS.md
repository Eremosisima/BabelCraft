# Agent Instructions (BabelCraft)

## Project goal
BabelCraft converts Minecraft Java Edition content (mods, resource packs, datapacks, and modpacks like Cobbleverse) into Bedrock addons (`.mcaddon`) with a "never fake" policy.

## Key paths
- Converter core: `babelcraft/` (pipeline in `babelcraft/converters/`, mechanics hooks in `babelcraft/mechanics/`)
- Cobbleverse workflow: `convert_cobbleverse.py`, `download_cobbleverse_assets.py`, `COBBLEVERSE_DEPENDENCY_TREE.md`
- Reports/outputs: `out/*` (generated artifacts, usually gitignored)
- Tests: `tests/` (`py -m pytest tests -q`)

## Working conventions
- Prefer deterministic, inspectable conversions; document adapted/residual content and reasons.
- Do not invent unsupported Java logic/mechanics; implement approximations only when explicit and safe, and record limitations.
- Preserve/validate Bedrock format details (BP `entities/`, RP `entity/`, texture indices, geometry/material refs, animation refs).
- Sanitize animations/Molang defensively; drop or safely degrade invalid constructs to avoid runtime errors.
- For modpacks, keep provenance and overlay order explicit (base + overrides + verified downloads).

## Validation
- Run tests after converter changes: `cd BabelCraft; py -m pytest tests -q`
- Regenerate target addon(s) and inspect `REPORT.md` and Bedrock content logs for runtime issues.

## Knowledge artifacts
- Migration learnings: `docs/MIGRATION_LEARNINGS.md`
- Migration skill: `.agents/skills/java-to-bedrock-migration/SKILL.md`
- Migration agent spec: `.agents/agents/java-to-bedrock-migration.md`
- Cobbleverse graph/provenance: `COBBLEVERSE_DEPENDENCY_TREE.md`
