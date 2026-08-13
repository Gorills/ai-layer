.PHONY: install upgrade check-dev-env dev-install dev-setup test lint format type architecture migrations fast-gate quality postgres-gate preflight preflight-ci release-gate release db-up db-down smoke

REPO_VENV_BIN := $(CURDIR)/.venv/bin
ifneq ($(wildcard $(REPO_VENV_BIN)/python),)
export PATH := $(REPO_VENV_BIN):$(PATH)
endif

PYTHON_312 ?= python3.12

install upgrade:
	./install.sh

check-dev-env:
	@test -x .venv/bin/python || { echo "ERROR: repository .venv is missing; run 'make dev-setup' first." >&2; exit 2; }
	@test "$$(.venv/bin/python -c 'import platform, sys; print(f"{platform.python_implementation()} {sys.version_info.major}.{sys.version_info.minor}")')" = "CPython 3.12" || { echo "ERROR: repository .venv must use CPython 3.12; replace it before rerunning 'make dev-setup'." >&2; exit 2; }

dev-install: check-dev-env
	.venv/bin/python -m pip install -e '.[dev]'

dev-setup:
	@test -x .venv/bin/python || $(PYTHON_312) -m venv .venv
	$(MAKE) dev-install
	chmod +x .githooks/pre-commit .githooks/pre-push
	git config core.hooksPath .githooks
	@test "$$(git config --get core.hooksPath)" = ".githooks"
	@echo "AI Layer development hooks enabled (.githooks)."

test:
	python -m pytest tests

format:
	ruff format --check .

lint:
	ruff check .

type:
	mypy src/ai_layer

architecture:
	python scripts/architecture_gate.py

migrations:
	python scripts/migration_gate.py

fast-gate: check-dev-env
	ruff format --check .
	ruff check .
	python scripts/architecture_gate.py

quality:
	python scripts/quality_gate.py --deterministic-wheel

postgres-gate:
	python scripts/postgres_gate.py

preflight-ci:
	$(MAKE) quality
	$(MAKE) postgres-gate

preflight: check-dev-env
	.venv/bin/python scripts/local_preflight.py

release-gate:
	python scripts/release_gate.py --check-deterministic-wheel

release:
	python scripts/build_release.py --output dist/ai-layer-release.zip

db-up:
	docker compose up -d

db-down:
	docker compose down

smoke:
	bash scripts/smoke.sh
