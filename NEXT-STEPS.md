# What to do next

**Written:** 2026-08-30 · **After:** M0 complete, M1 substantially complete (223 tests green)

Four things, in order. **Steps 1–3 are yours now and take about an hour total.**
Step 4 is the real work, and it is blocked on code I still have to write — do not
start it yet.

At each step there is a *what success looks like* line. If you hit something
different, paste the output back and I will pick it up from there.

---

## Step 1 — Prove the build runs on your machine (~20 min)

Right now the code has only ever run in my cloud container. Before anything else,
it needs to run on yours. If there is an environment problem, I would rather find
it now than during a paid GPU session.

### Do this in WSL2, not native Windows

The `Makefile`, `kind`, and the whole toolchain assume a Unix shell. You already
have Docker Desktop, which on Windows almost certainly runs on the WSL2 backend —
so WSL2 is where the rest of this project should live.

```bash
# In PowerShell, if you don't already have it:
wsl --install -d Ubuntu
```

Then, **inside the Ubuntu shell**:

```bash
# 1. Install uv (the Python toolchain — HLD §7.2)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# 2. Go to the repo. Your OneDrive folder is visible from WSL at /mnt/c/...
cd /mnt/c/Users/rosha/OneDrive/Documents/Code-Central/PROVENANCE

# 3. Install dependencies from the committed lockfile
uv sync

# 4. Run the gate
make check
```

**What success looks like:**

```
uv run ruff check .
All checks passed!
...
223 passed in ~30s
SKIP go-check: barrier/epp/go.sum absent (T-003 blocked — needs Go >= 1.26.6)
make check: PASS
```

Then the walking skeleton:

```bash
make attest-demo
```

**What success looks like:** it ends with `M0 walking skeleton: PASS`, having
produced a signed receipt, verified it (exit 0), tampered with it, and confirmed
the tamper produces exit code 3.

### A note on working from OneDrive

Building directly inside a OneDrive-synced folder can be slow and occasionally
flaky — sync locks files mid-write. If `uv sync` or `make check` behaves oddly,
clone into a native WSL path instead (`~/provenance`) and treat OneDrive as the
backup rather than the working copy. Once step 2 is done, GitHub is the source of
truth anyway.

---

## Step 2 — Put it on GitHub (~15 min)

Everything downstream wants this: CI cannot run, the cloud agents cannot fetch the
repo, and the project cannot become a portfolio piece until it has a remote.

The repo already has a git history — three commits with task IDs — but only in my
container. On your machine the folder is currently just files. So:

```bash
cd /mnt/c/Users/rosha/OneDrive/Documents/Code-Central/PROVENANCE

git init
git add -A
git commit -m "PROVENANCE: design phases 0-3 and milestone M0/M1"
```

Create the repo on GitHub — **private for now** (D-10 says private until the ATTEST
MVP lands), then:

```bash
git remote add origin git@github.com:<your-username>/provenance.git
git branch -M main
git push -u origin main
```

**What success looks like:** the push completes, and within a couple of minutes the
**Actions** tab shows two jobs — `make check` and `M0 walking skeleton` — both green.
That green badge is running the actual pipeline, not just a linter, which is the
whole point of NFR-12.

**If Actions fail:** send me the log. Most likely cause is the Go setup step, which
I marked `continue-on-error` precisely because of step 3.

---

## Step 3 — Install Go 1.26.6 (~15 min)

This unblocks **T-003**, which currently blocks **T-034** and **all of M4** — the
tenant-salt plugin, which is BARRIER's entire contribution. Nothing in BARRIER can
be built until this is done.

`llm-d-router` v0.10.0 declares `go 1.26.6` in its go.mod (ADR-008). Anything older
cannot even resolve the dependency.

In WSL2:

```bash
# Check what you have (Ubuntu's apt version will almost certainly be too old)
go version 2>/dev/null || echo "no go"

# Install the current toolchain
cd /tmp
curl -LO https://go.dev/dl/go1.26.6.linux-amd64.tar.gz
sudo rm -rf /usr/local/go && sudo tar -C /usr/local -xzf go1.26.6.linux-amd64.tar.gz
echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.bashrc
source ~/.bashrc

go version    # must report go1.26.6 or newer
```

Then resolve the module:

```bash
cd /mnt/c/Users/rosha/OneDrive/Documents/Code-Central/PROVENANCE/barrier/epp
GOFLAGS=-mod=mod go mod tidy
go build ./...
```

**What success looks like:** `go.sum` appears, `go build` succeeds silently, and
back at the repo root `make check` no longer prints the SKIP line — it runs the Go
gates for real.

**Send me back:** the `go version` output and whether `go mod tidy` succeeded. That
is what lets me mark T-003 done and start T-034.

> You will also want `golangci-lint` eventually, but `make check` degrades
> gracefully without it. Not urgent.

---

## Step 4 — The cluster work · **NOT YET — blocked on me**

This is where BARRIER actually begins, and it is the part only you can run, because
no agent can reach a Kubernetes cluster. But **the scripts do not exist yet.**

What I still have to write first:

| Task | What it is |
|---|---|
| T-032 | kind cluster wrapper over upstream's `Makefile.kind.mk` |
| T-033 | Two-tenant topology — llm-d Router + 2 simulator pods, Helm values |
| T-034 | The custom EPP image (needs Go from step 3) |
| T-035 | **The S-02 spike** — the script whose output decides BARRIER's shape |

When those land, your job will be to run them and send back the output directory.
The packs are written so each is a self-contained script that records its own
results into `bench/results/` — you run one command, and I read the evidence
without having watched the run.

**Why S-02 matters more than the others.** It answers whether an ordinary tenant
caller can observe *anything* that reveals routing on the simulator. I already know
from source that the obvious signal is closed off —
`x-gateway-destination-endpoint-served` is stripped from responses. If nothing else
is observable, FR-B-03 changes from an attacker-run oracle to an
operator-instrumented demonstration, and the attacker-observable version moves to
real vLLM on the GPU. That is a scope change, not a failure, and the decision rule
is already written down in LLD §7 so it cannot be rationalised after we see the
result.

**Prerequisite you can check now** (one command, no commitment):

```bash
docker info | head -5      # in WSL2 — should show Docker Desktop's engine
```

If that works, kind will work.

---

## Step 5 — The GPU session · later

Not until T-018 (real vLLM process lifecycle) is written, which is my next ATTEST
task. When it is ready:

1. Rent one L4 or A10 (compute capability ≥ 8.0 — an A100 also works, an AMD card
   does not).
2. `make attest-stage1 ENGINE_URL=http://<host>:8000` — the ~90-minute divergence
   hunt, cheapest configurations first. It stops the moment it finds divergence.
3. **You make a decision here.** Stage 1 prints where divergence appeared. You pick
   the model, `max_tokens` and concurrency for stage 2 from that evidence. This is
   deliberately not automated: if divergence never appears, that becomes the
   published result and ATTEST's centre of gravity shifts.
4. `make attest-stage2 ENGINE_URL=... MODEL=... MAX_TOKENS=...` — the ~2.5-hour
   measured sweep.

If the session drops, re-run the same command with `--resume <run-id>`. Completed
cells are skipped entirely — that is the property FR-A-09 exists for, and it is
tested.

---

## Summary

| # | What | Time | Blocked? |
|---|---|---|---|
| 1 | `uv sync && make check && make attest-demo` in WSL2 | ~20 min | **do now** |
| 2 | git init, push to a private GitHub repo, confirm Actions green | ~15 min | **do now** |
| 3 | Install Go 1.26.6, `go mod tidy` in `barrier/epp` | ~15 min | **do now** |
| 4 | Cluster bring-up + S-02 spike | — | blocked on me (T-032/033/034/035) |
| 5 | GPU session | 4–6 h | blocked on me (T-018) |

Steps 1–3 are independent of each other; do them in any order. What I need back is
short: whether `make check` passed, whether Actions went green, and what
`go version` reports.

While you do those, I will write T-018 and the M3 cluster tasks.
