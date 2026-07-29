# 026 — Platform SDK Growth Gate and Documentation Audit Completion

**Date:** 2026-07-28 · **Type:** Docs only, no code changes

Two product-owner-directed pieces of work, closing out the documentation-first phase before Platform SDK design begins as its own dedicated step.

## Part 1 — Platform SDK growth gate recorded as a hard blocker

The direct-Kernel-import exception documented in `capability_pack_contract.md` (Software Engineering pack importing `ai_os_kernel` internals directly, in the absence of a real `ai-os-sdk` package) previously carried only a soft "temporary"/"dated exception" framing with no firm deadline. The product owner decided this needed a firm, non-negotiable boundary: **no new agent may be added to any Capability Pack, and no new Capability Pack may be added, until the Platform SDK exists.**

Recorded in exactly four places, as directed:

- `docs/03_architecture/capability_framework/capability_pack_contract.md` (v1.2 → v1.3) — the exception note itself rewritten to state the gate explicitly, bounded to the pack surface that already exists; the five existing SE-pack agents grandfathered.
- `docs/19_roadmap/implementation_status.md` — a new blockquote in §2, a new first-position bullet in §4 Current Blockers, and a fully rewritten §6 recommending the Platform SDK build as the next step's own dedicated scope (not started by this step).
- `docs/19_roadmap/feature_inventory.md` — module 27 (Platform SDK) row rewritten to state the gate; module 29 (SE Pack — Agents) noted as frozen at 5; modules 32/33/34 (the three not-yet-started packs) each noted as blocked by name.
- `docs/process/standing_rules.md` — a new top-level section, `## 🛑 Capability Pack growth gate`, placed immediately after the intro, ahead of Scope discipline, so no future step can miss it.

`CLAUDE.md`'s existing Platform SDK bullet was also updated to reference the gate, for a reader who never opens `standing_rules.md`.

## Part 2 — Remaining documentation audit closed (16 documents)

`025_documentation_consolidation_audit.md` left ~20 documents un-audited because 3 of 4 parallel subagents hit a session resource limit mid-run. This step completed all of them individually — read in full, every claim checked against real source (grep/read against `kernel/src/ai_os_kernel/`, `capability_packs/software-engineering/`, `.github/workflows/ci.yml`, Alembic migrations), an `## Implementation Status (2026-07-28)` section added, and a `## Related Documents` section added or extended with verified relative links:

1. `docs/03_architecture/workflow/workflow_architecture.md`
2. `docs/03_architecture/workflow/state_management.md`
3. `docs/03_architecture/workflow/error_handling_retry.md`
4. `docs/03_architecture/agents/agent_communication.md`
5. `docs/03_architecture/kernel/workflow_engine.md`
6. `docs/03_architecture/services/configuration_management.md`
7. `docs/06_capability_packs/capability_pack_development_guide.md`
8. `docs/06_capability_packs/software_engineering/agents.md` (Related Documents only — Implementation Status already present from an earlier step)
9. `docs/06_capability_packs/software_engineering/overview.md`
10. `docs/06_capability_packs/software_engineering/workflows.md` (Related Documents only — Implementation Status already present)
11. `docs/08_database/data_model.md`
12. `docs/09_security/authentication_authorization.md`
13. `docs/09_security/secrets_management.md`
14. `docs/09_security/security_architecture.md`
15. `docs/20_glossary/glossary.md` (lighter treatment — a definitional document, not a build spec)
16. `docs/21_templates/CODING_STANDARDS_AND_BEST_PRACTICES.md`

### Newly discovered gaps (not previously documented anywhere)

- **Workflow Engine:** only 3 of 9 declared `WorkflowInstanceStatus` values are ever written (`created`, `running`, `completed`); only 2 of 7 declared step types (`agent`, `tool`) route to a real executor, the other 5 fall through to `NoOpStepExecutor`; `RetryPolicy` is validated at load but never read by any runtime path; of §4's 13 named components, only 4 exist as real classes.
- **Authorization:** the monotonic-narrowing chain (`principal ∩ workflow ∩ agent ∩ tool`) that both `security_architecture.md` §9 and `authentication_authorization.md` §4.4 present as an already-enforced control only computes the first term — `security_manager/models.py`'s own docstring discloses that the workflow/agent/tool intersection is not implemented, since nothing reads manifest-declared permissions at authorization time yet.
- **Prompt injection defence:** the Context Manager's `ContextItem`/`SourceRef` has no `trust` field at all — the `trusted`/`untrusted` provenance tagging §6 of `security_architecture.md` names as a primary T2 control does not exist in code. Currently low-risk only because no content-ingesting resolver exists yet either.
- **Security test coverage:** `tests/security/` exists as a directory but contains zero files, contradicting `security_architecture.md` §15's claim that tests exist per numbered threat.
- **Secrets backend:** only the `env` backend (`EnvSecretProvider`) is implemented; `file`/`vault`/`aws`/`gcp`/`azure` do not exist, and no factory reads `AIOS_SECRET_BACKEND` to select among them despite `configuration_management.md` §3.3 listing it as a real, working environment variable.
- **CI enforcement gap:** the Forbidden Practices list in `CODING_STANDARDS_AND_BEST_PRACTICES.md` marks "a Capability Pack importing `ai_os_kernel`" as `[CI]`-enforced; no such check exists anywhere in `.github/workflows/ci.yml`, and the one real pack does this extensively today under the (now hard-gated) documented exception. `mypy --strict` also does not cover `platform_sdk/` or any Capability Pack, contrary to the same document's stated CI scope.
- **Data model:** `knowledge` is the newest real schema (migration `0029`, 2026-07-27) — tables only, with a write path for 2 of 4 tables (`documents`, `chunks`) and none for `embeddings`/`memory_items`. §13's SQLite development mode is entirely aspirational — zero references to SQLite exist anywhere in `kernel/`.
- **Git safety:** no Git Integration Service and no `git.*` tool exist anywhere in the Kernel or the Software Engineering pack — every Git-safety control in `security_architecture.md` §14 (force-push prohibition, protected-branch policy, mutation audit) has nothing to enforce it, though the exposure is currently latent since no workflow performs a Git write yet.

### Corrections made during writing (caught before commit)

An early draft of `security_architecture.md`'s Implementation Status section incorrectly asserted `ContextItem.trust` provenance tagging was real; a direct read of `context_manager/models.py` showed no `trust` field exists at all. Corrected before commit — see the "Prompt injection defence" gap above, which is the accurate version of that finding.

## Link validation

Every relative markdown link added or touched across all 20 files changed in this step was checked to resolve to a real file (scripted check, zero broken links found).

## Result

**Documentation is now 100% audited** — every document flagged as outstanding after `025` has an Implementation Status and Related Documents section, verified against source, with zero remaining unreviewed files.

## Next step

Scope the Platform SDK v1.0.0 build as its own dedicated step. This step deliberately does not begin that design — see `implementation_status.md` §6 for what that scoping should decide.
