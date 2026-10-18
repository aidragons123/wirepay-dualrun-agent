.PHONY: setup single bulk bulk-fixed ui test clean
PYTHON ?= python3

setup:
	$(PYTHON) -m pip install --break-system-packages -r requirements.txt
	@which javac >/dev/null 2>&1 || (apt-get update -qq && apt-get install -y default-jdk)

# One request to both implementations:  make single SCENARIO="Bad IBAN checksum"
single:
	$(PYTHON) run_dualrun.py single --scenario "$(if $(SCENARIO),$(SCENARIO),Clean USD payment)" --no-fail

# 1,000 requests to both implementations, compared, reports in out/
bulk:
	$(PYTHON) run_dualrun.py bulk --n $(if $(N),$(N),1000)

# Same, with the stand-in's planted parity gaps fixed: should be 0 mismatches.
bulk-fixed:
	$(PYTHON) run_dualrun.py bulk --parity-fix --no-fail

ui:
	$(PYTHON) -m streamlit run streamlit_app.py

test:
	$(PYTHON) -m pytest tests -v

clean:
	rm -rf build out .pytest_cache
	find . -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
