"""Real, manifest-declared Tools this pack owns (`P03-S04-M31-T02`) —
distinct from the `agents/` package: a Tool is invoked by an agent via
`context.tools.invoke(tool_id, inputs)` (SDK `ToolInvoker`), never
itself an LLM caller, and is resolved through
`ai_os_kernel.workflow_engine.registry.SqlToolRegistry`, not
`SqlAgentRegistry`.
"""

from __future__ import annotations
