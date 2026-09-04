# StoreTrack Codex skills

This directory mirrors the repository prompt skills under `.claude/skills/` so
Codex workflows in the app, CLI, and VS Code/IDE extension have an explicit
project-local skill library.

The root `AGENTS.md` is the Codex entry point. It tells Codex when to load these
`SKILL.md` files. Keep corresponding `.claude/skills/<name>/SKILL.md` and
`.codex/skills/<name>/SKILL.md` files synchronized when editing a skill.
