.PHONY: help test demo serve docs build clean

PYTHON ?= python3

help:
	@echo "LinkLab"
	@echo ""
	@echo "  make test    run the test suite"
	@echo "  make demo    print the example budgets from the command line"
	@echo "  make docs    build the example documentation into ./site"
	@echo "  make serve   run the web UI on the example project (port 8080)"
	@echo "  make build   build the distribution artifacts"

test:
	$(PYTHON) -m pytest

demo:
	$(PYTHON) -m linklab budget fiber --length 42 --fibre smf --tx 5 --rx -28 \
		--bitrate 10 --spectral-width 0.05 --splices 8 --connectors 6 --margin 3
	@echo
	$(PYTHON) -m linklab budget microwave --length 5 --freq 15 --tx 20 \
		--tx-gain 30 --rx-gain 30 --rx-threshold -80 --margin 10
	@echo
	$(PYTHON) -m linklab budget copper --length 105 --category cat6 --pairs 4 --application 10gbase-t

docs:
	$(PYTHON) -m linklab docs build examples/site-atlas-telecom/project.json --out site
	@echo "Open site/index.html"

serve:
	$(PYTHON) -m linklab serve examples/site-atlas-telecom/project.json --port 8080

build:
	$(PYTHON) -m pip install --upgrade build
	$(PYTHON) -m build

clean:
	rm -rf site dist build *.egg-info .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
