.PHONY: help install dev init-db seed generate eval bench lint format test smoke clean

# Default target
help:
	@echo "card-pack-agent — common commands"
	@echo ""
	@echo "  make install        Install runtime deps"
	@echo "  make dev            Install dev deps (pytest, ruff, mypy)"
	@echo "  make init-db        Initialize Postgres schema + Qdrant collections"
	@echo "  make seed           Seed synthetic bootstrap data (zero-data cold start)"
	@echo "  make generate TOPIC='中秋节' CATEGORY=festival"
	@echo "                      Generate a pack for a given topic"
	@echo "  make eval           Run all eval runners (A/B/C/D)"
	@echo "  make bench PROVIDERS=mock,flux_pro N=5"
	@echo "                      Benchmark image providers side-by-side"
	@echo "  make smoke          Quick smoke tests (mock mode, no network)"
	@echo "  make lint           Ruff check"
	@echo "  make format         Ruff format"
	@echo "  make test           Run pytest"
	@echo "  make clean          Remove caches and build artifacts"

install:
	pip install -e .

dev:
	pip install -e ".[dev]"
	pre-commit install || true

init-db:
	python scripts/init_db.py

seed:
	python scripts/seed_synthetic.py --category festival

generate:
	python scripts/generate_pack.py --topic "$(TOPIC)" --category "$(CATEGORY)"

eval:
	python scripts/run_eval.py --all

bench:
	python scripts/bench_image_providers.py \
		--providers $${PROVIDERS:-mock} \
		--n $${N:-3}

smoke:
	APP_MODE=mock pytest tests/ -v -m smoke

lint:
	ruff check src tests eval scripts

format:
	ruff format src tests eval scripts

test:
	pytest tests/ -v

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
