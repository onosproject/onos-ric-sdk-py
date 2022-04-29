# onos-ric-sdk-py makefile
#
# SPDX-FileCopyrightText: © 2021 Open Networking Foundation <support@opennetworking.org>
# SPDX-License-Identifier: Apache-2.0

SHELL = bash -e -o pipefail

.DEFAULT_GOAL := help
.PHONY: test help

# all files with extensions
PYTHON_FILES      ?= $(wildcard onos_ric_sdk_py/*.py tests/*.py)

# tooling
VIRTUALENV        ?= python3 -m venv

# Create the virtualenv with distribution and additional testing tools installed
VENV_NAME = venv_orsp

build-tools:=$(shell if [ ! -d "./build/build-tools" ]; then mkdir -p build && cd build && git clone https://github.com/onosproject/build-tools.git; fi)
include ./build/build-tools/make/onf-common.mk

$(VENV_NAME): requirements.txt
	$(VIRTUALENV) $@ ;\
  source ./$@/bin/activate ; set -u ;\
  python -m pip install --upgrade pip;\
  python -m pip install -r requirements.txt black flake8 furo isort mypy pylint pytest pytest-aiohttp pytest-asyncio pytest-cov reuse sphinx sphinx-autodoc-typehints sphinxcontrib-openapi
	echo "To enter virtualenv, run 'source $@/bin/activate'"

dist: setup.py $(VENV_NAME) ## Create a source distribution
	rm -rf dist/
	source ./$(VENV_NAME)/bin/activate ; set -u ;\
	python ./$< sdist

docs: $(VENV_NAME) ## build docs with sphinx
	source ./$</bin/activate ; set -u ;\
	make -C docs html

lint: license black flake8 isort pylint mypy ## run static lint checks

test: $(VENV_NAME) ## run unit tests with pytest
	source ./$</bin/activate ; set -u ;\
	pytest --cov=onos_ric_sdk_py --junit-xml=junit-results.xml --cov-report=xml tests/

flake8: $(VENV_NAME) ## check python formatting with flake8
	source ./$</bin/activate ; set -u ;\
  	flake8 --version ;\
  	flake8 --max-line-length 119 $(PYTHON_FILES)

pylint: $(VENV_NAME) ## pylint check for python 3 compliance
	source ./$</bin/activate ; set -u ;\
  	pylint --version ;\
  	pylint --rcfile=pylint.ini $(PYTHON_FILES)

mypy: $(VENV_NAME) ## run mypy to typecheck
	source ./$</bin/activate ; set -u ;\
  	mypy --version ;\
  	mypy -p onos_ric_sdk_py

isort: $(VENV_NAME) ## run isort to typecheck
	source ./$</bin/activate ; set -u ;\
  	isort --version ;\
  	isort --profile black -m 3 -l 88 --lai 2 --ca --tc $(PYTHON_FILES)

black: $(VENV_NAME) ## run black on python files in check mode
	source ./$</bin/activate ; set -u ;\
  	black --version ;\
  	black --check $(PYTHON_FILES)

blacken: $(VENV_NAME) ## run black on python files to reformat
	source ./$</bin/activate ; set -u ;\
  	black --version ;\
  	black $(PYTHON_FILES)

clean::  ## Remove build/test temp files
	rm -rf dist docs/_build junit-results.xml .coverage coverage.xml .mypy_cache .pytest_cache onos_ric_sdk_python.egg-info

clean-all: clean ## clean + remove virtualenv
	rm -rf $(VENV_NAME)

publish: twine # @HELP publish version on github and PyPI
	BASEDIR=. PYPI_INDEX=pypi ./../build-tools/publish-python-version
	./../build-tools/publish-version ${VERSION}

jenkins-publish: # @HELP Jenkins calls this to publish artifacts
	../build-tools/release-merge-commit
