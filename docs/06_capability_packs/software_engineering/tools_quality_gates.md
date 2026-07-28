# Software Engineering Pack – Tools & Quality Gates – AI_OS

**Project:** AI_OS (AI Operating System)  
**Document:** Software Engineering Pack – Tools & Quality Gates  
**Version:** 1.0  
**Status:** Approved  
**Last Updated:** 2026-07-25

---

## 1. Purpose

This document defines the Tools and Quality Gates that belong to (or are primarily contributed by) the **Software Engineering Capability Pack**.

Tools are the only approved way for agents to produce side effects. Quality Gates enforce the engineering standards of the pack and of the overall platform.

This document is subordinate to:

1. Capability Pack Contract  
2. Quality Gates Framework  
3. Software Engineering Pack – Overview  
4. Software Engineering Pack – Agents  
5. Software Engineering Pack – Workflows (`workflows.md`)  

---

## 2. Design Principles

- Agents never perform side effects directly; they call Tools.
- Tools must have clear contracts (inputs, outputs, permissions, error behaviour).
- Quality Gates must be objective and measurable.
- Both Tools and Quality Gates must be declared in the pack’s manifest.
- Prefer reuse of platform-level tools where they exist; pack-specific tools should be created only when necessary.

---

## 3. Core Tools (Initial Set)

The Software Engineering Pack is expected to provide or rely on tools in the following categories:

### 3.1 Source Code Tools
- Read / write / list files
- Apply patches
- Search code
- Parse syntax / AST utilities (language-specific as needed)

### 3.2 Build & Dependency Tools
- Install dependencies
- Build project
- Run package scripts

### 3.3 Test Tools
- Execute unit tests
- Execute integration tests
- Collect coverage reports

### 3.4 Static Analysis & Lint Tools
- Linters
- Type checkers
- Static security scanners

### 3.5 Git & Version Control Tools
- Status, diff, add, commit, branch, merge (with strict permission controls)
- Generate changelogs

### 3.6 Documentation Tools
- Generate or update Markdown / API docs
- Validate documentation structure

### 3.7 Container & Deployment Tools (via DevOps Agent)
- Build container images
- Validate deployment manifests
- Interact with CI configuration

### 3.8 Trust tiers — mandatory classification

Every tool declares a trust tier in the manifest, validated at pack load ([ADR-0016](../../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md)):

| Tool category | Tier |
|---|---|
| Build, test, coverage, dependency install, container build, static analysis on generated code | **`tier1_sandboxed`** — ephemeral container, no network by default, no secrets |
| File read/list/search within the workflow workspace, git metadata (status, diff, log), documentation validation | `tier2_trusted` — canonical-path allowlisted |
| Git mutating operations (commit, push, tag) | `tier2_trusted`, executed by the **Git Integration Service** which holds the credential; the sandbox never receives it |

Anything that executes a command string, compiles, runs tests, installs dependencies, or processes untrusted repository content is Tier 1. There is no discretion in this classification, and a mis-declared tool fails validation at install time.

Concrete tool IDs, schemas, and permission sets are declared in the pack manifest and validated against `platform_sdk/schemas/manifest.schema.json`.

---

## 4. Quality Gates (Initial Set)

The pack contributes and requires the following Quality Gates (aligned with the Quality Gates Framework):

### 4.1 Build Gates
- Build succeeds
- Dependencies resolve cleanly

### 4.2 Test Gates
- Unit tests pass
- Integration tests pass
- Minimum coverage threshold met

### 4.3 Static Analysis Gates
- Linting passes
- Type checking passes
- No critical static analysis findings

### 4.4 Security Gates
- No critical / high vulnerabilities
- Secrets detection passes
- Dependency vulnerability scan passes

### 4.5 Architecture & Standards Gates
- Coding standards compliance
- Architecture compliance (layering, dependency rules)
- Naming and structure conventions

### 4.6 Documentation Gates
- Required documentation exists and is up to date
- Public APIs are documented

### 4.7 Release Gates
- Versioning is correct
- Changelog is present
- Release readiness checklist passes

Gates may be marked as **blocking** or **warning** according to the Quality Gates Framework.

---

## 5. Integration Rules

- Tools are invoked only through the Tool Invoker (never directly by agents in an uncontrolled way).
- Quality Gates are executed by the Quality Gate Engine at points defined in workflows.
- Results of both tools and gates must be fully observable and available to the Evaluation Engine.
- Permissions for tools must be declared and granted explicitly.

---

## 6. Current Status

This document defines the initial set of Tools and Quality Gates for the Software Engineering Pack.

Concrete tool schemas, gate implementation details, and exact thresholds will be refined during pack development.

---

## 7. Final Authority

Order of precedence:

1. Capability Pack Contract  
2. Quality Gates Framework  
3. Software Engineering Pack – Overview  
4. Software Engineering Pack – Tools & Quality Gates  
5. Source Code
