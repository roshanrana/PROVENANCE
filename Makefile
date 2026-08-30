#  PROVENANCE
#
#  One entry point for validation. Agents, humans, pre-commit and CI all speak
#  this vocabulary — nobody maintains a parallel list of "the real checks", and
#  CI is a mirror of `make check`, never a superset. If it passes here and fails
#  there, that divergence is the bug.

SHELL := /bin/bash
.DEFAULT_GOAL := help
UV ?= uv
GO ?= go
EPP_DIR := barrier/epp

.PHONY: help bootstrap check check-full check-ship fmt lint typecheck test \
        go-check attest-demo attest-stage1 attest-stage2 \
        barrier-up barrier-spike barrier-diff barrier-down clean

help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

bootstrap: ## Install dependencies from the lockfile
	$(UV) sync

# --------------------------------------------------------------------------- gates

fmt: ## Auto-fix formatting and lint findings
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

lint: ## Lint (no fixes) + format check
	$(UV) run ruff check .
	$(UV) run ruff format --check .

typecheck: ## Static types — strict on common/ and attest/receipt (HLD §7.3)
	$(UV) run mypy .

test: ## Unit + integration tests
	$(UV) run pytest

go-check: ## Go gates. Skipped with a warning if the toolchain is too old — see T-003.
	@if [ ! -f $(EPP_DIR)/go.sum ]; then \
	  echo "SKIP go-check: $(EPP_DIR)/go.sum absent (T-003 blocked — needs Go >= 1.26.6)"; \
	else \
	  cd $(EPP_DIR) && $(GO) build ./... && $(GO) vet ./... && \
	  test -z "$$($(GO)fmt -l .)" && golangci-lint run; \
	fi

check: lint typecheck test go-check ## The gate. Green is required before any task is done.
	@echo "make check: PASS"

check-full: check ## check + coverage against the NFR-13 target
	$(UV) run pytest --cov --cov-report=term-missing --cov-report=xml

check-ship: check-full ## check-full + dependency, secrets and vulnerability scans
	$(UV) run pip-audit || true
	@command -v gitleaks >/dev/null && gitleaks detect --no-banner || \
	  echo "SKIP secrets scan: gitleaks not installed"
	@if [ -f $(EPP_DIR)/go.sum ]; then cd $(EPP_DIR) && govulncheck ./...; fi

# --------------------------------------------------------------------------- demos

attest-demo: ## M0 walking skeleton — full pipeline, stub engine, no GPU
	$(UV) run python scripts/attest_demo.py

attest-stage1: ## Stage 1 divergence hunt. Needs ENGINE_URL (a real vLLM on a GPU).
	@test -n "$(ENGINE_URL)" || { echo "set ENGINE_URL=http://host:8000"; exit 2; }
	$(UV) run python -m attest.harness.run --engine-url $(ENGINE_URL) --stage 1 \
	  --seed $${SEED:-0} --trials $${TRIALS:-32}

attest-stage2: ## Stage 2 measured matrix. Needs ENGINE_URL, MODEL, MAX_TOKENS.
	@test -n "$(ENGINE_URL)" -a -n "$(MODEL)" -a -n "$(MAX_TOKENS)" || \
	  { echo "set ENGINE_URL, MODEL and MAX_TOKENS (chosen from stage 1 evidence)"; exit 2; }
	$(UV) run python -m attest.harness.run --engine-url $(ENGINE_URL) --stage 2 \
	  --model $(MODEL) --max-tokens $(MAX_TOKENS) --seed $${SEED:-0} --trials $${TRIALS:-128}

# --------------------------------------------------------------------------- barrier

barrier-up: ## Bring up the kind topology. PROFILE=default|hardened
	chmod +x barrier/deploy/kind/up.sh
	barrier/deploy/kind/up.sh $${PROFILE:-default}

barrier-spike: ## Run the S-02 spike. Needs the gateway port-forwarded to :8080.
	$(UV) run python -m barrier.attack.spike_s02 --gateway $${GATEWAY:-http://localhost:8080}

barrier-diff: ## The mitigation, as a diff. This is the deliverable (ADR-004).
	@diff -u barrier/deploy/values-default.yaml barrier/deploy/values-hardened.yaml || true

barrier-down: ## Delete the kind cluster
	kind delete cluster --name $${CLUSTER:-provenance}

clean: ## Remove caches and demo artefacts
	rm -rf .mypy_cache .pytest_cache .ruff_cache .coverage coverage.xml htmlcov
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
