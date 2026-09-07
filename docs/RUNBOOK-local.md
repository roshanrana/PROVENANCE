# Local runbook — everything that does not need a GPU

Two jobs run entirely on a workstation with Docker. Between them they cover most
of what was previously blocked on hardware this project does not have.

Both are read-only with respect to your system: everything happens in
containers, and nothing is installed on the host beyond the tools named below.

---

## 1. The CPU dress rehearsal (~20 min, mostly downloads)

### What it is for

Every ATTEST test so far runs against `tests/support/stub_engine.py` — a server
this project wrote, which therefore **agrees with this project by
construction**. A fixture that cannot disagree cannot find a bug.

This runs the same harness against real vLLM on CPU. It **measures nothing**:
batch invariance requires an NVIDIA GPU of compute capability ≥ 8.0 and is
unsupported on CPU, so the flag is not even set. What it proves is that the
plumbing is right — argv, readiness, configuration readback, wire format —
while that is still free to discover rather than discovered on rented hardware.

It has already paid for itself three times over. Writing it surfaced:

1. **`return_token_ids` was never sent.** vLLM declares
   `CompletionResponseChoice.token_ids` as `list[int] | None = None` and
   populates it only for a request that opts in. The receipt's subject digest is
   computed over token ids, so every receipt from a real engine would have had
   nothing to bind.
2. **The readback endpoint was wrong twice over.** It is `/server_info`, not
   `/v1/server_info` (upstream attaches the router with no prefix), and it is
   registered **only under `VLLM_SERVER_DEV_MODE`**. Without that variable the
   endpoint 404s, the readback silently degrades, and the receipt records what
   we asked for instead of what the engine resolved — a D-08 violation inside a
   receipt that still looks perfectly well-formed.
3. **`VLLM_BATCH_INVARIANT` is nested under `vllm_env`**, not at the top level.
   The old code looked only at the top level, so `_observed_batch_invariance`
   would have returned `None` on every real engine — meaning **the refusal the
   entire design leans on ("engine reports X but the run requested Y — refusing
   to measure") would never once have fired.**

All three are fixed. The rehearsal is what keeps them fixed.

### Run it

```bash
./scripts/rehearse-cpu.sh
```

From PowerShell, run it inside WSL:

```powershell
wsl bash -lc "cd /mnt/c/Users/rosha/OneDrive/Documents/Code-Central/PROVENANCE && ./scripts/rehearse-cpu.sh"
```

Output lands in `bench/results/rehearsal-cpu/` — `findings.json` plus the raw
JSON of every endpoint, kept verbatim so a field name that moves upstream is
visible rather than inferred.

**Exit 0 means the harness talks to a real engine correctly.** It says nothing
about determinism, and the script says so in its own output so the file cannot
later be mistaken for evidence.

Useful knobs: `KEEP_ENGINE=1` leaves the container up to poke at,
`VLLM_CPU_KVCACHE_SPACE=8` gives it more KV space, `MODEL=...` swaps the model.

---

## 2. The BARRIER cluster (~30 min first time)

Entirely CPU. The model-server pods are `llm-d-inference-sim` simulators, not
real engines — no GPU is involved at any point.

### Prerequisites

Docker Desktop with the WSL2 backend, plus four tools inside WSL:

```bash
# kubectl
curl -Lo /tmp/kubectl "https://dl.k8s.io/release/$(curl -Ls https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -m 0755 /tmp/kubectl /usr/local/bin/kubectl

# helm
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# go 1.26.6+ (kind and ko are installed with it)
# https://go.dev/dl/  — then:
go install sigs.k8s.io/kind@latest
go install github.com/google/ko@latest
export PATH="$PATH:$(go env GOPATH)/bin"
```

Give Docker Desktop at least 8 GB of RAM (Settings → Resources). With 64 GB on
the host that is not a constraint, but the default allocation can be lower.

### Run it

```bash
cd barrier/deploy/kind
./up.sh default      # the leaking configuration — the one under attack
./up.sh hardened     # the mitigation
```

`up.sh` is self-contained and writes its own transcript to
`bench/results/cluster-<profile>/up.log`. It was written on the assumption that
nobody is watching it, so every step either succeeds loudly or fails loudly.

### Then the spike that is actually blocking BARRIER

**S-02** asks whether an ordinary API caller can observe *anything* that
distinguishes a cache hit from a miss. Its decision rule was fixed in advance
(LLD §7) and travels inside the evidence file, so the result cannot be
rationalised after the fact:

```bash
uv run python -m barrier.attack.spike_s02 --base-url http://localhost:8080
```

Both outcomes are publishable. If no client-observable signal exists on the
simulator, that rescopes FR-B-03 to an instrumented demonstration — a finding,
not a failure. **Its verdict must reach `docs/design/decisions.md` before any
oracle code is written**, the same discipline as S-03 and the pre-registered
statistics.

---

## What still needs a GPU, and only this

| | Why |
|---|---|
| ATTEST divergence + invariance | Batch-invariant kernels are CUDA/Triton; CPU unsupported |
| The cost-of-determinism numbers | Same |
| A-03's caching × determinism 2×2 | Same, plus SGLang's deterministic backends are all GPU |

Everything else on this page runs on your desk for nothing.

One caveat carried forward: on an Ampere or Ada card (A10, L4, A40, 4090)
SGLang must use `--attention-backend triton`, because FA3 is Hopper-only. Triton
is in the harness's radix-safe set, so the determinism-with-caching cell still
works — but the receipt records the backend, so the write-up has to say Triton.
