---
slug: godot
description: Godot-specific scene, resource, input, physics, save, and export discipline.
kind: stack
keywords:
- godot
- gdscript
- scene
- resource
- autoload
- signal
- physics
- scene tree
- inputmap
- physics process
- export preset
---
# Godot Skill

## Apply when
The project uses Godot and scenes/nodes/resources, GDScript, input, physics, save data, tools, or export behavior change.

## Mandatory rules
- Use the project-pinned Godot version, renderer, scripting language, import settings, and export presets as source of truth.
- Keep scene ownership/lifecycle explicit; use signals/interfaces/groups rather than brittle deep tree paths when appropriate.
- Use InputMap actions, `delta`/fixed physics semantics correctly, and avoid frame-rate-dependent gameplay.
- Prefer Resources/data assets for reusable configuration; do not make autoloads the default state container.
- Avoid committing generated `.godot` import cache as authored source and avoid runtime asset loading on hot paths.

## Decision rules
- Put canonical gameplay state in the owner system/model, not simultaneously in UI nodes.
- Use `_physics_process` for fixed-step physics behavior and `_process` for frame presentation/update semantics as appropriate.
- Version save formats and resource contracts when persisted content must survive releases.

## Failure modes
Deep `get_node()` coupling, global singleton sprawl, editor-only assumptions, synchronous hot-path loads, invalid signal lifecycle, frame-dependent timers/movement, and save data tied directly to transient node structure.

## Quality gates
Run representative scenes/flows plus configured tests/static checks; verify save/load, input devices, export/build, or performance when touched.
