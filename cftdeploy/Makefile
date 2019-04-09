# Static, not sure if needed??
PYTHON=python3
PIP=pip3

FILES=*.py __init__.py _version.py entry_points.py


test: $(FILES)
	for f in $^; do $(PYTHON) -m py_compile $$f; if [ $$? -ne 0 ] ; then echo "$$f FAILS" ; exit 1; fi done

pep8: $(FILES)
	pycodestyle $^