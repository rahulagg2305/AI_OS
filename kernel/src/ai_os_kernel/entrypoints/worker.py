"""Worker process-role entrypoint — placeholder.

Started as::

    python -m ai_os_kernel.entrypoints.worker

See docs/11_deployment/deployment_architecture.md §2.

The worker role executes workflow steps via lease-based work distribution
(ADR-0011: ``SELECT ... FOR UPDATE SKIP LOCKED``). It has no
implementation yet — the Workflow Engine lands in Implementation Roadmap
Stage B. This stub exists so the documented entrypoint path is real and
importable rather than a dangling promise.
"""

import logging

logger = logging.getLogger("ai_os_kernel.entrypoints.worker")


def main() -> None:
    logging.basicConfig(level="INFO")
    logger.info("AI_OS worker role is not yet implemented (Implementation Roadmap Stage B).")


if __name__ == "__main__":
    main()
