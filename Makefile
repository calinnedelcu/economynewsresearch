PY ?= python
PAPER_DIR := paper

.PHONY: validate tables figures paper appendix all-paper

validate:
	$(PY) validate_outputs.py

tables:
	$(PY) make_tables.py

figures:
	$(PY) make_figures.py

paper:
	cd $(PAPER_DIR) && pdflatex -interaction=nonstopmode -halt-on-error main.tex
	cd $(PAPER_DIR) && bibtex main
	cd $(PAPER_DIR) && pdflatex -interaction=nonstopmode -halt-on-error main.tex
	cd $(PAPER_DIR) && pdflatex -interaction=nonstopmode -halt-on-error main.tex

appendix:
	cd $(PAPER_DIR) && pdflatex -interaction=nonstopmode -halt-on-error online_appendix.tex
	cd $(PAPER_DIR) && bibtex online_appendix
	cd $(PAPER_DIR) && pdflatex -interaction=nonstopmode -halt-on-error online_appendix.tex
	cd $(PAPER_DIR) && pdflatex -interaction=nonstopmode -halt-on-error online_appendix.tex

all-paper: tables figures paper appendix
