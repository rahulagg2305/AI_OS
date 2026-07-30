# Platform SDK v1.0.0 — Scope and Build Sequence

**Project:** AI_OS (AI Operating System)
**Document:** Platform SDK v1.0.0 Scope and Build Sequence
**Version:** 2.18 (closed)
**Status:** ✅ **Complete and closed out (2026-07-30).** All 18 steps (plus two inserted fix steps, 9a and 12a) are done. This document is now a short, permanent summary — the full, dated, step-by-step record (§2 through §6s of the original) is archived verbatim at `docs/19_roadmap/history/027_platform_sdk_v1_scope_plan.md`.
**Last Updated:** 2026-07-30 (condensed per the new file-splitting standing rule — `docs/process/standing_rules.md` — since the full document exceeded the 500-line threshold and is a closed plan, not an actively growing one. Nothing was deleted; see the archive link above.)

---

## 1. Purpose

This document scoped the Platform SDK v1.0.0 build (`ai-os-sdk`, `platform_sdk/`) as its own dedicated plan, answering: which documented Protocol interfaces the one real pack actually needed, whether/when the 5 real agents migrate onto the SDK, whether `pack_contract_suite` ships with the SDK or after, what goes in `platform_sdk/`'s subdirectories, the ordered build sequence, and what v1.0.0 deliberately does not do.

It is subordinate to: 1) Project Constitution, 2) `platform_sdk.md` (the specification this plan sequenced the build of), 3) `capability_pack_contract.md` (the growth gate this build closed), 4) `docs/process/standing_rules.md` (the growth gate and scope-discipline rules).

For the full 18-step (+2 inserted) narrative — every step's decisions, real bugs found and fixed, and evidence — see the archive: `docs/19_roadmap/history/027_platform_sdk_v1_scope_plan.md` §2–§6s.

---

## 7. Explicit non-goals for v1.0.0 (deliberately deferred)

- 10 documented Protocol interfaces with no implementation and no consumer (`RetrievalService`, `MemoryService`, `EventBus`, `ConfigService`, `StorageService`, `WorkspaceService`, `Telemetry`, `TraceabilityService`, `QualityGateRegistry`, `SpeechGateway`) — each sits on a 0%-built or docstring-only Kernel subsystem.
- `SecretResolver` — dropped in the 18-step revision; the real pack declares no secret permission, and step 6b's injection mechanism removed the need.
- SDK semantic-versioning enforcement in the Manifest Loader — needs a second real SDK version to exist first.
- `platform_sdk/prompts/` — purpose undocumented anywhere in the source spec; left untouched pending a product-owner decision.
- Consolidating the Kernel's two partial `TraceContext` classes onto the SDK's canonical one — a real Kernel change with its own regression surface, not smuggled into a model-definition step.

## 8. Final Authority

Order of precedence: 1) Project Constitution, 2) AI Governance Framework, 3) `platform_sdk.md`, 4) `capability_pack_contract.md`, 5) This document, 6) Source Code.

## 9. Related Documents

- [`platform_sdk.md`](platform_sdk.md) — the specification this plan sequenced the build of
- [`../capability_framework/capability_pack_contract.md`](../capability_framework/capability_pack_contract.md) — the growth gate this build closed
- [`../../process/standing_rules.md`](../../process/standing_rules.md) — the growth gate and scope-discipline rules this plan satisfied
- [`../../19_roadmap/implementation_status.md`](../../19_roadmap/implementation_status.md) §6 — the handoff this document answered
- [`../../19_roadmap/feature_inventory.md`](../../19_roadmap/feature_inventory.md) — module 27 (Platform SDK), module 29 (SE Pack — Agents)
- [`../../19_roadmap/history/027_platform_sdk_v1_scope_plan.md`](../../19_roadmap/history/027_platform_sdk_v1_scope_plan.md) — the full, archived, step-by-step record (§2–§6s of the original document)
- [`../../../capability_packs/software-engineering/`](../../../capability_packs/software-engineering/) — the one real pack this plan migrated

## 10. v1.0.0 Closeout — what this plan actually delivered, and what remains deferred

**All 18 steps (plus the two inserted fix steps, 9a and 12a) are complete as of step 15 (2026-07-30).**

### What v1.0.0 delivers

- A real, installable `ai-os-sdk` package (`platform_sdk/`), a genuine workspace member, built and installable as a standalone wheel.
- Three real Protocols with real, proven Kernel-side implementations: `LLMGateway`, `PromptRegistry`, `ToolInvoker`. Two further Protocols carry real, proven structural conformance without a dedicated adapter: `Agent`/`Tool` and `CapabilityPack`/`PackContext`/`PackRegistration`/`HealthReport`.
- The real Kernel-side adapters (`kernel/src/ai_os_kernel/sdk_adapters/`) plus `PackContextReceiver`/`bind_pack_context()`, the injection mechanism that closes the `EntrypointLoader` zero-argument-construction gap without changing `EntrypointLoader` itself.
- One fully migrated Capability Pack — Software Engineering — with **zero `ai_os_kernel` imports anywhere in its own source tree**: all 5 real agents plus `pack.py` itself depend solely on `ai_os_sdk` types, proven zero-behavior-change at every migration step.
- A genuinely enforced, unconditional `pack_contract_suite` — all 9 checks, proven against the real, fully-migrated pack with zero waivers.
- `PLATFORM_PYTHON_INTERPRETER` — a small but load-bearing fix (step 12a) restoring a real pre-migration guarantee the generic `ToolInvoker` Protocol could not otherwise express.
- The Capability Pack growth gate, lifted (step 14, `docs/process/standing_rules.md`) — a real, dated, explicit product-owner decision.

### What remains deferred, deliberately

- 10 of the 15 documented Protocol interfaces have no implementation and no consumer (same list as §7).
- `SecretResolver` — dropped (§7).
- The `evaluation.llm_calls` observability gap — all 4 LLM-calling agents no longer have real completions recorded, since v1.0.0 defines no `Telemetry`/`TraceabilityService` surface. Tracked in `feature_inventory.md` §6a "Known Regressions," expected to stay open until a real SDK Telemetry surface exists.
- `LLMGateway.stream()`/`.embed()`/`.count_tokens()` — not defined anywhere in v1.0.0.
- `Agent`/`Tool`'s documented request/response envelope shapes (`AgentRequest`/`AgentResult`, `ToolRequest`) — v1.0.0 kept the narrower, dict-based shape; adopting the documented envelope is a future major SDK version change.
- SDK semantic-versioning enforcement in the Manifest Loader.
- `platform_sdk/prompts/` — undocumented purpose, left untouched.
- Consolidating the Kernel's two partial `TraceContext` classes.
- A second real pack, or a 6th Software Engineering agent — no longer blocked, but new feature work this plan does not itself schedule.

### Is the codebase ready to resume normal feature development?

**Yes.** The SDK exists, is genuinely depended on, and the one real pack is fully migrated and passes an unconditional, 9-check compliance suite with zero exceptions. The growth gate is lifted.
