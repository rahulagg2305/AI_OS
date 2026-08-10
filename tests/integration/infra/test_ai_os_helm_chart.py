"""Real, unmocked proof for the `ai-os` Helm chart (`P07-S01-M40-T01`,
`infra/kubernetes/helm/ai-os/`) — ADR-0020 / `deployment_architecture.md`
§6's own decided Kubernetes topology.

**`helm`/`kind` are not installed in CI** — these tests are skipped,
with a clear reason, exactly the same "opt-in, clearly skipped, not
silently ignored" shape `test_docker_sandbox_live.py` already
establishes for a missing Docker daemon (ADR-0015). Running this file
against a real `helm`/`kind`/Docker toolchain is the real, permanent
re-verification path for this chart, mirroring that file's own stated
purpose.

`test_the_rendered_manifests_are_genuinely_accepted_by_a_real_kubernetes_api_server`
is the deepest real proof available without a managed cluster: spins
up a real, temporary, single-node `kind` cluster (genuine Docker
containers, a genuine Kubernetes API server), applies the chart's own
real, rendered output against it for real (not `--dry-run`), confirms
every resource genuinely exists via a real `kubectl get`, then tears
the cluster down — leaving no persistent state. Pods are expected to
report `ErrImagePull` (no container registry has been decided anywhere
in this repo — a real, disclosed, separate gap, see the chart's own
README.md), which this test asserts explicitly rather than silently
ignoring, so a future change that makes the manifests themselves
genuinely invalid cannot hide behind that already-expected failure.
"""

from __future__ import annotations

import shutil
import subprocess
import time
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CHART_PATH = REPO_ROOT / "infra" / "kubernetes" / "helm" / "ai-os"
_RELEASE_NAME = "aios-test"
_SUBPROCESS_TIMEOUT_SECONDS = 60.0
_KIND_TIMEOUT_SECONDS = 180.0


def _run(command: list[str], *, timeout: float = _SUBPROCESS_TIMEOUT_SECONDS) -> str:
    """Every ``command`` is a fixed-shape argv built from a
    ``shutil.which``-resolved binary path plus literal flag strings —
    never raw, untrusted, or shell input."""
    result = subprocess.run(  # noqa: S603 — argv is fixed-shape, no shell, see this fn's own docstring
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{' '.join(command)} exited {result.returncode}:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


@pytest.fixture(scope="module")
def helm_binary() -> str:
    binary = shutil.which("helm")
    if binary is None:
        pytest.skip("helm is not on PATH — this chart's own opt-in real-tool suite")
    return binary


@pytest.fixture(scope="module")
def kind_binary() -> str:
    binary = shutil.which("kind")
    if binary is None:
        pytest.skip("kind is not on PATH — this chart's own opt-in real-cluster suite")
    return binary


@pytest.fixture(scope="module")
def kubectl_binary() -> str:
    binary = shutil.which("kubectl")
    if binary is None:
        pytest.skip("kubectl is not on PATH — this chart's own opt-in real-cluster suite")
    return binary


def test_the_real_chart_lints_cleanly(helm_binary: str) -> None:
    """`helm lint` — real, structural Helm-chart validation, not a
    hand-rolled substitute."""
    output = _run([helm_binary, "lint", str(CHART_PATH)])
    assert "0 chart(s) failed" in output


def test_the_real_chart_renders_every_documented_resource(helm_binary: str) -> None:
    """`helm template` — a real Go-template render (not a fake
    hand-substitution), confirming every documented, real resource this
    chart's own README.md claims to build actually appears in the
    output."""
    rendered = _run([helm_binary, "template", _RELEASE_NAME, str(CHART_PATH)])
    documents = [doc for doc in yaml.safe_load_all(rendered) if doc is not None]
    kinds_and_names = {(doc["kind"], doc["metadata"]["name"]) for doc in documents}

    assert ("Deployment", f"{_RELEASE_NAME}-api") in kinds_and_names
    assert ("Deployment", f"{_RELEASE_NAME}-worker") in kinds_and_names
    assert ("Service", f"{_RELEASE_NAME}-api") in kinds_and_names
    assert ("ConfigMap", f"{_RELEASE_NAME}-config") in kinds_and_names
    assert ("ServiceAccount", "aios") in kinds_and_names
    assert ("PodDisruptionBudget", f"{_RELEASE_NAME}-api") in kinds_and_names
    assert ("PodDisruptionBudget", f"{_RELEASE_NAME}-worker") in kinds_and_names
    assert ("HorizontalPodAutoscaler", f"{_RELEASE_NAME}-worker") in kinds_and_names


def test_the_network_policy_is_absent_by_default(helm_binary: str) -> None:
    """``P07-S01-M40-T02`` — opt-in, product-owner decision: a default
    render (no ``--set``) must not create a ``NetworkPolicy`` at all,
    the real proof that this ticket changed nothing about a default
    install (zero regression)."""
    rendered = _run([helm_binary, "template", _RELEASE_NAME, str(CHART_PATH)])
    documents = [doc for doc in yaml.safe_load_all(rendered) if doc is not None]

    assert not any(doc["kind"] == "NetworkPolicy" for doc in documents)


def test_the_network_policy_when_enabled_has_the_real_baseline_and_operator_rules(
    helm_binary: str,
) -> None:
    """When explicitly enabled, the real DNS + same-namespace baseline
    is always present, and an operator-supplied
    ``additionalRules`` entry (a real, literal
    ``NetworkPolicyEgressRule`` — Postgres on a real CIDR, the exact
    shape values.yaml's own comment documents) renders through
    unchanged."""
    rendered = _run(
        [
            helm_binary,
            "template",
            _RELEASE_NAME,
            str(CHART_PATH),
            "--set",
            "networkPolicy.enabled=true",
            "--set",
            "networkPolicy.egress.additionalRules[0].to[0].ipBlock.cidr=10.0.0.0/24",
            "--set",
            "networkPolicy.egress.additionalRules[0].ports[0].protocol=TCP",
            "--set",
            "networkPolicy.egress.additionalRules[0].ports[0].port=5432",
        ]
    )
    documents = [doc for doc in yaml.safe_load_all(rendered) if doc is not None]
    policy = next(doc for doc in documents if doc["kind"] == "NetworkPolicy")

    assert policy["spec"]["podSelector"]["matchLabels"] == {
        "app.kubernetes.io/name": "ai-os",
        "app.kubernetes.io/instance": _RELEASE_NAME,
    }
    egress_rules = policy["spec"]["egress"]

    dns_rule = egress_rules[0]
    assert dns_rule["to"][0]["podSelector"]["matchLabels"] == {"k8s-app": "kube-dns"}
    assert {p["port"] for p in dns_rule["ports"]} == {53}

    same_namespace_rule = egress_rules[1]
    assert same_namespace_rule["to"] == [{"podSelector": {}}]

    operator_rule = egress_rules[2]
    assert operator_rule["to"][0]["ipBlock"]["cidr"] == "10.0.0.0/24"
    assert operator_rule["ports"][0]["port"] == 5432


def test_the_worker_deployment_declares_no_http_probes(helm_binary: str) -> None:
    """The chart's own disclosed, deliberate gap, proven rather than
    merely claimed in a comment: the worker Deployment's container spec
    genuinely has no `livenessProbe`/`readinessProbe`/`startupProbe`
    key at all — the real entry point it runs has no HTTP server to
    probe (see `deployment-worker.yaml`'s own docstring)."""
    rendered = _run([helm_binary, "template", _RELEASE_NAME, str(CHART_PATH)])
    documents = [doc for doc in yaml.safe_load_all(rendered) if doc is not None]
    worker_deployment = next(
        doc
        for doc in documents
        if doc["kind"] == "Deployment" and doc["metadata"]["name"] == f"{_RELEASE_NAME}-worker"
    )
    container = worker_deployment["spec"]["template"]["spec"]["containers"][0]
    assert "livenessProbe" not in container
    assert "readinessProbe" not in container
    assert "startupProbe" not in container


def test_the_api_deployment_probes_the_real_verified_health_paths(helm_binary: str) -> None:
    """The real, verified paths — `routes/health.py`'s own
    `APIRouter(prefix="/api/v1", ...)`, matching
    `deployment_architecture.md` §6's own table exactly (see
    values.yaml's own `probes` comment)."""
    rendered = _run([helm_binary, "template", _RELEASE_NAME, str(CHART_PATH)])
    documents = [doc for doc in yaml.safe_load_all(rendered) if doc is not None]
    api_deployment = next(
        doc
        for doc in documents
        if doc["kind"] == "Deployment" and doc["metadata"]["name"] == f"{_RELEASE_NAME}-api"
    )
    container = api_deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["livenessProbe"]["httpGet"]["path"] == "/api/v1/health/live"
    assert container["readinessProbe"]["httpGet"]["path"] == "/api/v1/health/ready"
    assert container["startupProbe"]["httpGet"]["path"] == "/api/v1/health/live"


@pytest.fixture(scope="module")
def rendered_manifests_path(helm_binary: str, tmp_path_factory: pytest.TempPathFactory) -> Path:
    rendered = _run([helm_binary, "template", _RELEASE_NAME, str(CHART_PATH)])
    path = tmp_path_factory.mktemp("ai-os-helm") / "rendered.yaml"
    path.write_text(rendered, encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def rendered_manifests_with_network_policy_path(
    helm_binary: str, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    """The identical render, with the opt-in NetworkPolicy switched on
    — a real, non-dry-run apply of this against a genuine API server is
    the strongest available proof that ``policy/v1`` egress rules this
    codebase invented for the baseline (DNS, same-namespace) are
    genuinely well-formed, not merely "renders without a YAML error"."""
    rendered = _run(
        [
            helm_binary,
            "template",
            _RELEASE_NAME,
            str(CHART_PATH),
            "--set",
            "networkPolicy.enabled=true",
        ]
    )
    path = tmp_path_factory.mktemp("ai-os-helm-netpol") / "rendered.yaml"
    path.write_text(rendered, encoding="utf-8")
    return path


def test_the_sandbox_sidecar_is_absent_by_default(helm_binary: str) -> None:
    """``P07-S01-M40-T01`` — opt-in, matching ``networkPolicy.enabled``'s
    own precedent: a default render (no ``--set``) must declare exactly
    one container on the worker Deployment and no ``fsGroup``/extra
    volume at all — zero regression for a default install."""
    rendered = _run([helm_binary, "template", _RELEASE_NAME, str(CHART_PATH)])
    documents = [doc for doc in yaml.safe_load_all(rendered) if doc is not None]
    worker_deployment = next(
        doc
        for doc in documents
        if doc["kind"] == "Deployment" and doc["metadata"]["name"] == f"{_RELEASE_NAME}-worker"
    )
    pod_spec = worker_deployment["spec"]["template"]["spec"]
    assert len(pod_spec["containers"]) == 1
    assert "securityContext" not in pod_spec
    assert "volumes" not in pod_spec


def test_the_sandbox_sidecar_when_enabled_has_the_real_verified_security_shape(
    helm_binary: str,
) -> None:
    """When explicitly enabled, the rendered worker Deployment has
    exactly the two real, verified-against-a-live-Docker-daemon
    properties this pattern needs (see ``values.yaml``'s own
    docstring): the sidecar runs non-root with `SYS_ADMIN` (and nothing
    else) plus `Unconfined` seccomp, and never anything this chart
    already refuses (`privileged`, `hostPath`, `hostNetwork`,
    `hostPID`) — asserted explicitly, not merely absent by omission."""
    rendered = _run(
        [
            helm_binary,
            "template",
            _RELEASE_NAME,
            str(CHART_PATH),
            "--set",
            "sandboxSidecar.enabled=true",
        ]
    )
    documents = [doc for doc in yaml.safe_load_all(rendered) if doc is not None]
    worker_deployment = next(
        doc
        for doc in documents
        if doc["kind"] == "Deployment" and doc["metadata"]["name"] == f"{_RELEASE_NAME}-worker"
    )
    pod_spec = worker_deployment["spec"]["template"]["spec"]
    assert pod_spec["securityContext"]["fsGroup"] == 1000
    assert "hostPID" not in pod_spec
    assert "hostNetwork" not in pod_spec
    assert all("hostPath" not in v for v in pod_spec["volumes"])
    assert pod_spec["volumes"] == [{"name": "sandbox-socket", "emptyDir": {}}]

    containers = {c["name"]: c for c in pod_spec["containers"]}
    assert containers["worker"]["env"][-1] == {
        "name": "DOCKER_HOST",
        "value": "unix:///run/podman/podman.sock",
    }

    sidecar = containers["podman-sidecar"]
    assert sidecar["image"] == "quay.io/podman/stable:v5.6.2"
    assert "--storage-driver" in sidecar["args"] and "vfs" in sidecar["args"]
    sidecar_security = sidecar["securityContext"]
    assert sidecar_security["runAsNonRoot"] is True
    assert sidecar_security.get("privileged") is not True
    assert sidecar_security["capabilities"]["add"] == ["SYS_ADMIN"]
    assert sidecar_security["capabilities"]["drop"] == ["ALL"]
    assert sidecar_security["seccompProfile"]["type"] == "Unconfined"


@pytest.fixture(scope="module")
def real_kind_cluster(
    kind_binary: str, kubectl_binary: str, helm_binary: str
) -> Generator[str, None, None]:
    """A real, temporary, single-node Kubernetes cluster (genuine Docker
    containers, a genuine control plane) — created fresh, destroyed at
    the end of this module, leaving no persistent state. A genuinely
    unreachable Docker daemon skips this whole suite cleanly, the same
    ADR-0015 shape `test_docker_sandbox_live.py`'s own `docker_available`
    fixture already establishes."""
    cluster_name = f"aios-test-{uuid.uuid4().hex[:8]}"
    try:
        _run(
            [kind_binary, "create", "cluster", "--name", cluster_name],
            timeout=_KIND_TIMEOUT_SECONDS,
        )
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"kind could not create a real cluster — Docker is likely unreachable: {exc}")
        return
    try:
        yield f"kind-{cluster_name}"
    finally:
        subprocess.run(  # noqa: S603 — argv is fixed-shape, no shell; see `_run`'s own docstring
            [kind_binary, "delete", "cluster", "--name", cluster_name],
            capture_output=True,
            text=True,
            timeout=_KIND_TIMEOUT_SECONDS,
            check=False,
        )


def test_the_rendered_manifests_are_genuinely_accepted_by_a_real_kubernetes_api_server(
    rendered_manifests_path: Path,
    real_kind_cluster: str,
    kubectl_binary: str,
) -> None:
    """The deepest real proof available without a managed cluster — see
    this module's own docstring."""
    context = ["--context", real_kind_cluster]

    # Real server-side dry-run: the live API server's own admission
    # chain validates every resource without persisting anything.
    _run(
        [kubectl_binary, *context, "apply", "--dry-run=server", "-f", str(rendered_manifests_path)]
    )

    # A real, non-dry-run apply — every resource genuinely persists in
    # this real (if temporary) cluster's own etcd.
    _run([kubectl_binary, *context, "apply", "-f", str(rendered_manifests_path)])

    deployments = yaml.safe_load(
        _run([kubectl_binary, *context, "get", "deployments", "-o", "yaml"])
    )
    names = {item["metadata"]["name"] for item in deployments["items"]}
    assert {"aios-test-api", "aios-test-worker"} <= names

    api_deployment = next(
        item for item in deployments["items"] if item["metadata"]["name"] == "aios-test-api"
    )
    assert api_deployment["spec"]["replicas"] == 2
    worker_deployment = next(
        item for item in deployments["items"] if item["metadata"]["name"] == "aios-test-worker"
    )
    assert worker_deployment["spec"]["replicas"] == 3

    # The one real, expected, disclosed failure mode: no container
    # registry has been decided anywhere in this repo, so the real
    # cluster genuinely cannot pull `ai-os:0.1.0` — asserted explicitly,
    # not silently tolerated, so a *different* pod failure would still
    # fail this test. `containerStatuses` is only populated once the
    # kubelet has genuinely attempted the pull — a real, brief
    # eventual-consistency window, not a fake wait; polled rather than
    # slept-once.
    _expected_reasons = {"ErrImagePull", "ImagePullBackOff"}

    def _reached_expected_state(loaded: dict[str, Any]) -> bool:
        pods_seen = loaded["items"]
        if len(pods_seen) != 5:  # 2 api + 3 worker — a real, awaited pod count, not vacuous
            return False
        for pod in pods_seen:
            statuses = pod["status"].get("containerStatuses", [])
            if not statuses:
                return False
            if statuses[0]["state"].get("waiting", {}).get("reason") not in _expected_reasons:
                return False
        return True

    pods: dict[str, Any] = {}
    for _ in range(60):
        pods = yaml.safe_load(_run([kubectl_binary, *context, "get", "pods", "-o", "yaml"]))
        if _reached_expected_state(pods):
            break
        time.sleep(1.0)

    items = pods["items"]
    assert len(items) == 5  # 2 api + 3 worker
    for pod in items:
        statuses = pod["status"].get("containerStatuses", [])
        assert statuses, f"pod {pod['metadata']['name']} has no container status after polling"
        waiting = statuses[0]["state"].get("waiting", {})
        assert waiting.get("reason") in {"ErrImagePull", "ImagePullBackOff"}, (
            f"pod {pod['metadata']['name']} failed for an unexpected reason: {statuses[0]['state']}"
        )


def test_the_network_policy_is_genuinely_accepted_by_a_real_kubernetes_api_server(
    rendered_manifests_with_network_policy_path: Path,
    real_kind_cluster: str,
    kubectl_binary: str,
) -> None:
    """``P07-S01-M40-T02`` — the same real-cluster proof shape the base
    chart already gets, for the opt-in ``NetworkPolicy`` specifically.
    Reuses the shared ``real_kind_cluster`` (module-scoped) the base
    chart's own test already applies to — a real, idempotent
    ``apply`` of this superset (identical Deployments/Service/etc. plus
    the new ``NetworkPolicy``) against the same live API server, not a
    second, throwaway cluster."""
    context = ["--context", real_kind_cluster]

    _run(
        [
            kubectl_binary,
            *context,
            "apply",
            "--dry-run=server",
            "-f",
            str(rendered_manifests_with_network_policy_path),
        ]
    )
    _run(
        [kubectl_binary, *context, "apply", "-f", str(rendered_manifests_with_network_policy_path)]
    )

    policies = yaml.safe_load(
        _run([kubectl_binary, *context, "get", "networkpolicies", "-o", "yaml"])
    )
    names = {item["metadata"]["name"] for item in policies["items"]}
    assert f"{_RELEASE_NAME}-egress" in names

    policy = next(
        item for item in policies["items"] if item["metadata"]["name"] == f"{_RELEASE_NAME}-egress"
    )
    assert policy["spec"]["policyTypes"] == ["Egress"]
    assert len(policy["spec"]["egress"]) == 2  # the real DNS + same-namespace baseline only


@pytest.fixture(scope="module")
def rendered_manifests_with_sandbox_sidecar_path(
    helm_binary: str, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    """The identical render, with the opt-in Podman sidecar switched on
    — see ``test_the_sandbox_sidecar_is_genuinely_accepted_but_cannot_yet_start_rootless_podman``'s
    own docstring for why a real cluster apply is the strongest
    available proof here."""
    rendered = _run(
        [
            helm_binary,
            "template",
            _RELEASE_NAME,
            str(CHART_PATH),
            "--set",
            "sandboxSidecar.enabled=true",
        ]
    )
    path = tmp_path_factory.mktemp("ai-os-helm-sandbox") / "rendered.yaml"
    path.write_text(rendered, encoding="utf-8")
    return path


def test_the_sandbox_sidecar_is_genuinely_accepted_but_cannot_yet_start_rootless_podman(
    rendered_manifests_with_sandbox_sidecar_path: Path,
    real_kind_cluster: str,
    kubectl_binary: str,
) -> None:
    """The honest, real state of `P07-S01-M40-T01`'s own "Podman
    sidecar" pattern against an *actual* kind cluster (containerd CRI),
    not merely a standalone `docker run` reproduction — proven real,
    not fabricated, in both directions.

    The manifest itself is genuinely accepted by a live API server (the
    identical proof `test_the_rendered_manifests_are_genuinely_accepted_
    by_a_real_kubernetes_api_server` already establishes for the base
    chart), and `quay.io/podman/stable` — a real, publicly pullable
    image, unlike `ai-os:0.1.0` — genuinely gets pulled and started.

    **A second, deeper real limitation was found here, beyond the
    fuse/hostPath one `values.yaml`'s own docstring already documents:
    Podman's own rootless user-namespace remapping calls the setuid
    helper `newuidmap`, which fails with "operation not permitted"
    under this cluster's own containerd CRI runtime — confirmed
    unaffected by `SYS_ADMIN`, `seccomp: Unconfined`, or
    `allowPrivilegeEscalation: true`, all three already set. This looks
    like a `nosuid` container-filesystem mount, a CRI-runtime-level
    default no Pod-level `securityContext` field can override — a real,
    separate, deeper gap than the fuse one, found only by testing
    against a genuine cluster rather than a bare `docker run`.**

    This test asserts that *exact*, real, current failure explicitly
    (the same "assert the real expected failure, do not silently
    tolerate a different one" discipline the base chart's own
    `ErrImagePull` assertion already established) — so a future
    environment change that resolves this (a different CRI runtime, a
    cluster-level mount-flag change, a newer Podman release) makes this
    test fail loudly, prompting it to be strengthened into the full,
    genuine nested-execution proof this pattern still needs, rather
    than silently leaving a stale, over-broad assertion in place.
    """
    context = ["--context", real_kind_cluster]

    _run(
        [
            kubectl_binary,
            *context,
            "apply",
            "--dry-run=server",
            "-f",
            str(rendered_manifests_with_sandbox_sidecar_path),
        ]
    )
    _run(
        [kubectl_binary, *context, "apply", "-f", str(rendered_manifests_with_sandbox_sidecar_path)]
    )

    def _sidecar_container_status(pod: dict[str, Any]) -> dict[str, Any] | None:
        statuses: list[dict[str, Any]] = pod["status"].get("containerStatuses", [])
        for status in statuses:
            if status["name"] == "podman-sidecar":
                return status
        return None

    def _a_sidecar_that_has_genuinely_attempted_to_start() -> tuple[str, dict[str, Any]] | None:
        pods = yaml.safe_load(
            _run([kubectl_binary, *context, "get", "pods", "-l", "aios.role=worker", "-o", "yaml"])
        )
        for pod in pods["items"]:
            status = _sidecar_container_status(pod)
            if status is None:
                continue
            # A real attempt genuinely happened once either state is
            # populated — `waiting` alone (e.g. still `ContainerCreating`)
            # is not yet a real attempt to report on.
            terminated = status.get("state", {}).get("terminated") or status.get(
                "lastState", {}
            ).get("terminated")
            if terminated is not None:
                return pod["metadata"]["name"], terminated
        return None

    found: tuple[str, dict[str, Any]] | None = None
    for _ in range(90):
        found = _a_sidecar_that_has_genuinely_attempted_to_start()
        if found is not None:
            break
        time.sleep(1.0)

    assert found is not None, (
        "no worker pod's own podman-sidecar container ever genuinely attempted to "
        "start (no terminated state observed after polling) — see this test's own "
        "docstring for the real failure this was expected to reach instead"
    )
    pod_name, terminated = found
    assert terminated["exitCode"] == 125  # Podman's own real CLI-usage-error exit code

    logs = _run(
        [kubectl_binary, *context, "logs", pod_name, "-c", "podman-sidecar", "--tail", "20"]
    )
    assert "newuidmap" in logs
    assert "operation not permitted" in logs
