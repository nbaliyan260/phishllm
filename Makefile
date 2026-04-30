PY ?= python3
SRC := src/phishllm_search
PY_RUN := PYTHONPATH=src $(PY)
DATA_DIR ?= data
RUNS_DIR ?= runs
ART_DIR ?= artifacts
PROPOSER ?= heuristic   # heuristic | llm
ROUNDS ?= 4
SEED ?= 7

.PHONY: help install dev-install dataset eval-baseline search demo report test clean reset

help:
	@echo "Common targets:"
	@echo "  make install          install runtime dependencies"
	@echo "  make dev-install      install runtime + dev dependencies"
	@echo "  make dataset          regenerate the synthetic evaluation dataset"
	@echo "  make eval-baseline    evaluate the baseline candidate end-to-end"
	@echo "  make search           run the AI-driven search loop ($(ROUNDS) rounds)"
	@echo "  make report           build all plots and summary tables"
	@echo "  make demo             dataset + baseline + 1 search round + report"
	@echo "  make test             run the unit-test suite"
	@echo "  make reset            clear runs/ and artifacts/ outputs"

install:
	$(PY) -m pip install -r requirements.txt

dev-install:
	$(PY) -m pip install -r requirements-dev.txt

dataset:
	$(PY_RUN) -m phishllm_search.cli genset --out_dir $(DATA_DIR) --seed $(SEED)

eval-baseline:
	$(PY_RUN) -m phishllm_search.cli eval \
	  --candidate configs/candidates/seed_baseline.json \
	  --dataset $(DATA_DIR) \
	  --out_dir $(RUNS_DIR)/baseline

search:
	$(PY_RUN) -m phishllm_search.cli search \
	  --dataset $(DATA_DIR) \
	  --candidate_dir configs/candidates \
	  --out_dir $(RUNS_DIR)/search \
	  --rounds $(ROUNDS) \
	  --proposer $(PROPOSER) \
	  --seed $(SEED)

report:
	$(PY_RUN) -m phishllm_search.cli report \
	  --search_dir $(RUNS_DIR)/search \
	  --baseline_dir $(RUNS_DIR)/baseline \
	  --dataset $(DATA_DIR) \
	  --out_dir $(ART_DIR)

demo: dataset eval-baseline
	$(PY_RUN) -m phishllm_search.cli search \
	  --dataset $(DATA_DIR) \
	  --candidate_dir configs/candidates \
	  --out_dir $(RUNS_DIR)/search \
	  --rounds 1 \
	  --proposer heuristic \
	  --seed $(SEED)
	$(MAKE) report

test:
	$(PY_RUN) -m pytest tests/ -q

reset:
	rm -rf $(RUNS_DIR)/* $(ART_DIR)/plots/* $(ART_DIR)/tables/* $(ART_DIR)/logs/*
	@touch $(RUNS_DIR)/.gitkeep $(ART_DIR)/plots/.gitkeep $(ART_DIR)/tables/.gitkeep $(ART_DIR)/logs/.gitkeep

clean: reset
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache build dist *.egg-info
