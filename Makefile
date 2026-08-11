.PHONY: install upgrade dev-install test lint format type architecture migrations quality release-gate release db-up db-down smoke

install upgrade:
	./install.sh

dev-install:
	python -m pip install -e '.[dev]'

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

quality:
	python scripts/quality_gate.py

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
