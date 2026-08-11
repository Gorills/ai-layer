.PHONY: install upgrade dev-install dev-setup test lint format type architecture migrations fast-gate quality postgres-gate preflight preflight-ci release-gate release db-up db-down smoke

LOCAL_POSTGRES_URL ?= postgresql+psycopg://ai_layer:ai_layer@127.0.0.1:54329/ai_layer

install upgrade:
	./install.sh

dev-install:
	python -m pip install -e '.[dev]'

dev-setup: dev-install
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

fast-gate:
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

preflight:
	docker compose up -d --wait postgres
	AI_LAYER_TEST_POSTGRES_URL="$(LOCAL_POSTGRES_URL)" $(MAKE) preflight-ci

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
