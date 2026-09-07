#!/usr/bin/env bash
#
# Bring up the BARRIER topology on kind — T-032/T-033.
#
# Self-contained and it records its own output, because nobody watches this run:
# an agent writes it, Roshan executes it, and the orchestrator reads the result
# without having been present (requirements §6.4). Every step therefore either
# succeeds loudly or fails loudly, and the transcript lands in bench/results/.
#
#   ./up.sh default     # the leaking configuration — the one under attack
#   ./up.sh hardened    # the mitigation
#
set -euo pipefail

PROFILE="${1:-default}"
CLUSTER="${CLUSTER:-provenance}"
NAMESPACE="${NAMESPACE:-provenance}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
LOG_DIR="${LOG_DIR:-$REPO_ROOT/bench/results/cluster-$PROFILE}"

case "$PROFILE" in
  default|hardened) ;;
  *) echo "profile must be 'default' or 'hardened', got '$PROFILE'" >&2; exit 2 ;;
esac

mkdir -p "$LOG_DIR"
exec > >(tee "$LOG_DIR/up.log") 2>&1

echo "=== PROVENANCE cluster bring-up ==="
echo "profile   : $PROFILE"
echo "cluster   : $CLUSTER"
echo "namespace : $NAMESPACE"
echo "started   : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo

# --- preflight ---------------------------------------------------------------
# Checked up front rather than failing halfway through a cluster build.
for tool in docker kind kubectl helm ko; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "MISSING: $tool is not on PATH." >&2
    case "$tool" in
      kind) echo "  go install sigs.k8s.io/kind@latest" >&2 ;;
      ko)   echo "  go install github.com/google/ko@latest" >&2 ;;
      helm) echo "  https://helm.sh/docs/intro/install/" >&2 ;;
    esac
    exit 3
  fi
done

if ! docker info >/dev/null 2>&1; then
  echo "MISSING: the Docker daemon is not reachable. Start Docker Desktop." >&2
  exit 3
fi

GO_VERSION="$(go version 2>/dev/null | awk '{print $3}' | sed 's/^go//')" || true
echo "go        : ${GO_VERSION:-not found}"
if [ -z "${GO_VERSION:-}" ]; then
  echo "MISSING: Go >= 1.26.6 is required to build the EPP image (ADR-008)." >&2
  exit 3
fi
echo "versions  : kind=$(kind version 2>/dev/null | head -1), helm=$(helm version --short 2>/dev/null)"
echo

# --- cluster -----------------------------------------------------------------
if kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; then
  echo "--> reusing existing kind cluster '$CLUSTER'"
else
  echo "--> creating kind cluster '$CLUSTER'"
  kind create cluster --name "$CLUSTER" --config "$HERE/kind-config.yaml"
fi
kubectl config use-context "kind-$CLUSTER"
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# --- EPP image ---------------------------------------------------------------
# Built from source every time. A stale image is the kind of thing that makes a
# hardened run silently behave like a default one.
echo
echo "--> building the custom EPP image (ADR-002: our plugin + upstream runner)"
pushd "$REPO_ROOT/barrier/epp" >/dev/null

# Built into the local Docker daemon (`ko.local`) and side-loaded with
# `kind load docker-image`, NOT with ko's own `kind.local` publisher.
#
# `kind.local` was the obvious choice and it does not work on a multi-node
# cluster here: ko loads the image, then runs `ctr images tag` on every node,
# and on this three-node config the tag step failed on `provenance-worker` with
# `image "kind.local:<digest>": not found` — the load had not reached that node.
# CI run #4 died there after 2m40s of cluster build (F-20). `kind load
# docker-image` is kind's own distribution path and handles every node.
#
# The tag is unique per run rather than a fixed `dev`. A mutable tag on a
# side-loaded image is exactly the hazard ADR-008 names: a hardened deploy that
# silently runs a stale default binary. With a tag nothing else can have
# produced, `imagePullPolicy: IfNotPresent` cannot resolve to yesterday's build.
EPP_TAG="epp-$(git rev-parse --short HEAD 2>/dev/null || echo nogit)-$(date -u +%s)"
export KO_DOCKER_REPO="ko.local"
ko build ./cmd/epp --bare --tags "$EPP_TAG" >/dev/null

# The daemon is asked what ko named the image rather than the name being
# predicted from the flags. ko's repository naming depends on --bare vs
# --preserve-import-paths vs the ko.local defaults, and on stdout it prints a
# *digest* reference, which `kind load docker-image` cannot take. The tag is
# ours and unique, so looking it up is exact — and it fails here, with the
# daemon's own list in the log, rather than five minutes later as an
# ImagePullBackOff.
# `|| true` because no match is a `grep` exit 1, and under `set -e` that would
# abort here with no message — the empty-string check below is the diagnosis.
EPP_IMAGE="$( { docker images --format '{{.Repository}}:{{.Tag}}' | grep -F ":$EPP_TAG" || true; } | sed -n 1p)"
if [ -z "$EPP_IMAGE" ]; then
  echo "MISSING: ko produced no image tagged '$EPP_TAG' in the local daemon." >&2
  echo "  images the daemon holds under ko.local:" >&2
  docker images --format '  {{.Repository}}:{{.Tag}}' | grep -i '^  *ko' >&2 || true
  exit 4
fi
popd >/dev/null

echo "    built: $EPP_IMAGE"
echo "--> side-loading it into every node of '$CLUSTER'"
kind load docker-image "$EPP_IMAGE" --name "$CLUSTER"

# --- secrets -----------------------------------------------------------------
# Generated locally, gitignored, never printed. The salt secret in particular:
# anyone holding it can derive every tenant's salt, which restores the forgery
# attack the plugin exists to close.
echo
echo "--> generating tenant credentials and the salt secret"
# Written to disk as well as to the cluster, because the attack client has to
# authenticate as a tenant and nothing else can tell it the key.
#
# NOT under bench/results/: that directory is uploaded wholesale as a CI
# artifact, and .gitignore keeps a file out of git, not out of an artifact. A
# tenant key published beside the evidence would make every isolation claim in
# this repository void.
KEY_DIR="${KEY_DIR:-$REPO_ROOT/.secrets/tenant-keys}"
mkdir -p "$KEY_DIR"
chmod 700 "$KEY_DIR"
for tenant in tenant-a tenant-b; do
  key="$(openssl rand -hex 16)"
  kubectl -n "$NAMESPACE" create secret generic "${tenant}-key" \
    --from-literal=key="$key" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  printf '%s' "$key" > "$KEY_DIR/$tenant"
  chmod 600 "$KEY_DIR/$tenant"
  unset key
done
kubectl -n "$NAMESPACE" create secret generic provenance-salt \
  --from-literal=secret="$(openssl rand -hex 32)" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null
echo "    secrets applied (values not logged); keys for the client in $KEY_DIR"

# --- deploy ------------------------------------------------------------------
VALUES="$REPO_ROOT/barrier/deploy/values-$PROFILE.yaml"
echo
echo "--> deploying with $(basename "$VALUES")"

# The rendered manifests are committed alongside results. Helm templating is
# opaque when debugging, and a reader should be able to see exactly what ran
# rather than re-deriving it from values plus a chart version (ADR-004).
# --set overrides the chart default with what ko actually built. The rendered
# manifests are committed, so the image a reader sees is the image that ran.
helm template provenance "$HERE/../chart" \
  --namespace "$NAMESPACE" \
  --values "$VALUES" \
  --set epp.image="$EPP_IMAGE" > "$LOG_DIR/rendered.yaml"
echo "    rendered manifests: $LOG_DIR/rendered.yaml"

kubectl apply -n "$NAMESPACE" -f "$LOG_DIR/rendered.yaml"

echo
echo "--> waiting for rollout"
kubectl -n "$NAMESPACE" rollout status deployment/provenance-epp --timeout=300s
kubectl -n "$NAMESPACE" rollout status deployment/provenance-sim --timeout=300s

# --- evidence ----------------------------------------------------------------
{
  echo "{"
  echo "  \"profile\": \"$PROFILE\","
  echo "  \"cluster\": \"$CLUSTER\","
  echo "  \"namespace\": \"$NAMESPACE\","
  echo "  \"go_version\": \"${GO_VERSION}\","
  echo "  \"finished_utc\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
  echo "  \"values_sha256\": \"$(sha256sum "$VALUES" | cut -d' ' -f1)\","
  echo "  \"rendered_sha256\": \"$(sha256sum "$LOG_DIR/rendered.yaml" | cut -d' ' -f1)\""
  echo "}"
} > "$LOG_DIR/manifest.json"

kubectl -n "$NAMESPACE" get pods -o wide > "$LOG_DIR/pods.txt"

echo
echo "=== UP ($PROFILE) ==="
echo "evidence  : $LOG_DIR"
echo "gateway   : kubectl -n $NAMESPACE port-forward svc/provenance-gateway 8080:80"
echo
echo "Then run the S-02 spike:"
echo "  uv run python -m barrier.attack.spike_s02 --gateway http://localhost:8080"
