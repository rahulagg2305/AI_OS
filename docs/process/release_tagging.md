# Release Tagging Convention

**Status:** Active · **Introduced:** Phase R2 (2026-07-31)

The platform is pre-1.0 and not deployable (no image, no Kubernetes
manifests — module M40). Tags therefore mark **rollback points**, not
shipped releases.

## Format

```
v<major>.<minor>.<patch>[-<marker>]
```

- `v0.x.y` — pre-v1. `major` stays `0` until the v1 boundary in
  `functional_requirements.md` §10 is genuinely met.
- `-<marker>` — a short, stable label for *why* this point exists,
  lowercase, hyphenated: `-r1-complete`, `-p02-s01-complete`.

## When a tag is cut

1. **Phase or Stage completion** — every Task in the Stage is `done` or
   an explicitly-accepted `partial`, and the Stage's acceptance demo
   (`docs/process/acceptance_checkpoints.md`) has been run.
2. **A known-good rollback point** before a structurally risky change.
3. **Never** mid-step, and never on a red suite.

## Rules

- Tags are **annotated** (`git tag -a`), never lightweight — the message
  records what is real at that point.
- A tag is **immutable**: never moved, never deleted, never reused.
- The tag message states the real suite result and the real known-broken
  items. A tag that overstates readiness is worse than no tag.
- `patch` increments for a fix-only rollback point; `minor` for a Stage
  or Phase boundary.

## Baseline

`v0.1.0-r1-complete` — cut 2026-07-31, the first real rollback point.
Marks: Phase R1 audit accepted, CI genuinely executing for the first
time (6 of 8 jobs green), 1010 tests passing locally, Platform SDK
v1.0.0 complete. Known-broken at that point: CI integration job on Linux
(R-003).
