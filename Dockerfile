# AI_OS Kernel runtime image — one image, two process roles (ADR-0020).
# See docs/11_deployment/deployment_architecture.md §2-3 for the design
# this Dockerfile implements: multi-stage build, digest-pinned runtime
# base, non-root user, no build toolchain or package manager at runtime,
# no secrets baked into any layer.

ARG PYTHON_BASE=python:3.12-slim
ARG PYTHON_RUNTIME_DIGEST=python@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de

# --- Stage 1: builder --------------------------------------------------
# Not digest-pinned (a builder stage ships nothing to production and is
# never run as a container) — only the runtime base below is.
FROM ${PYTHON_BASE} AS builder

RUN pip install --no-cache-dir uv==0.12.0

WORKDIR /app

# The whole workspace (uv.lock decides exact versions; --frozen below
# fails the build outright if it is stale, so an image can never contain
# unlocked dependencies). .dockerignore trims dev-only content (tests,
# docs, caches) out of this context.
COPY . .

RUN uv sync --frozen --no-dev

# --- Stage 2: runtime ----------------------------------------------------
FROM ${PYTHON_RUNTIME_DIGEST} AS runtime

# Set by CI (docs/11_deployment/deployment_architecture.md §3: "Image is
# labelled with the Git SHA and semantic version"). Never a secret;
# real values are supplied per build via --build-arg, never hardcoded.
ARG GIT_SHA=unknown
ARG VERSION=0.0.0
LABEL org.opencontainers.image.revision=${GIT_SHA} \
      org.opencontainers.image.version=${VERSION} \
      org.opencontainers.image.title="ai-os-kernel"

# uid 10001, per the documented hardening target — never root.
RUN groupadd --gid 10001 aios \
    && useradd --uid 10001 --gid aios --create-home --shell /usr/sbin/nologin aios

WORKDIR /app

# The venv the builder stage produced — real, installed dependencies,
# never rebuilt here (no uv, no pip, no build toolchain in this stage).
COPY --from=builder --chown=aios:aios /app/.venv /app/.venv
# The workspace members' own source — uv sync installs each workspace
# member editable (ADR-0009: a monorepo, not published packages), so the
# venv alone cannot import them without their source alongside it.
COPY --from=builder --chown=aios:aios /app/kernel/src /app/kernel/src
COPY --from=builder --chown=aios:aios /app/platform_sdk/src /app/platform_sdk/src
COPY --from=builder --chown=aios:aios /app/platform_sdk/schemas /app/platform_sdk/schemas
COPY --from=builder --chown=aios:aios /app/capability_packs/software-engineering/src /app/capability_packs/software-engineering/src
COPY --from=builder --chown=aios:aios /app/capability_packs/software-engineering/manifest.yaml /app/capability_packs/software-engineering/manifest.yaml
COPY --from=builder --chown=aios:aios /app/capability_packs/software-engineering/workflows /app/capability_packs/software-engineering/workflows
COPY --from=builder --chown=aios:aios /app/capability_packs/software-engineering/prompts /app/capability_packs/software-engineering/prompts
# Real, repo-relative config the Configuration Manager reads by path at
# startup (configuration_management.md §3.3) — never packaged into a
# wheel, so it must be copied alongside the venv explicitly.
COPY --from=builder --chown=aios:aios /app/config /app/config
COPY --from=builder --chown=aios:aios /app/infra/environments /app/infra/environments
# Alembic migrations run as a separate command against this same image
# (deployment_architecture.md's own "migration-as-Job principle"), never
# automatically on container start.
COPY --from=builder --chown=aios:aios /app/alembic.ini /app/alembic.ini
COPY --from=builder --chown=aios:aios /app/kernel/alembic /app/kernel/alembic
COPY --chown=aios:aios deploy/entrypoint.sh /app/deploy/entrypoint.sh
COPY --chown=aios:aios deploy/healthcheck.py /app/deploy/healthcheck.py

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN chmod +x /app/deploy/entrypoint.sh

USER aios

EXPOSE 8000

# Liveness-only: /health/live never depends on an external service
# (health.py's own docstring), so this check is meaningful even before
# Postgres is reachable. A no-op (always healthy) for the worker role,
# which has no HTTP server to probe — deployment_architecture.md §3
# documents this HEALTHCHECK for the api role specifically.
HEALTHCHECK --interval=15s --timeout=3s --start-period=15s --retries=3 \
    CMD ["python", "/app/deploy/healthcheck.py"]

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
