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

$(VENV_NAME): requirements.txt
	$(VIRTUALENV) $@ ;\
  source ./$@/bin/activate ; set -u ;\
  python -m pip install --upgrade pip;\
  python -m pip install -r requirements.txt tox black pylint flake8 mypy reuse
	echo "To enter virtualenv, run 'source $@/bin/activate'"

dist: setup.py $(VENV_NAME) ## Create a source distribution
	rm -rf dist/
	source ./$(VENV_NAME)/bin/activate ; set -u ;\
	python ./$< sdist

lint: license black pylint flake8 mypy ## run static lint checks

test: $(VENV_NAME) ## run unit tests with tox
	source ./$</bin/activate ; set -u ;\
	tox

license: $(VENV_NAME) ## Check license with the reuse tool
	source ./$</bin/activate ; set -u ;\
  reuse --version ;\
  reuse --root . lint

flake8: $(VENV_NAME) ## check python formatting with flake8
	source ./$</bin/activate ; set -u ;\
  flake8 --version ;\
  flake8 --max-line-length 119 $(PYTHON_FILES)

pylint: $(VENV_NAME) ## pylint check for python 3 compliance
	source ./$</bin/activate ; set -u ;\
  pylint --version ;\
  pylint --py3k $(PYTHON_FILES)

mypy: $(VENV_NAME) ## run mypy to typecheck
	source ./$</bin/activate ; set -u ;\
  mypy --version ;\
  mypy -p onos_ric_sdk_py

black: $(VENV_NAME) ## run black on python files in check mode
	source ./$</bin/activate ; set -u ;\
  black --version ;\
  black --check $(PYTHON_FILES)

blacken: $(VENV_NAME) ## run black on python files to reformat
	source ./$</bin/activate ; set -u ;\
  black --version ;\
  black $(PYTHON_FILES)

twine: # @HELP install twine if not present
	python -m pip install --upgrade twine

build-tools: # @HELP install the ONOS build tools if needed
	@if [ ! -d "../build-tools" ]; then cd .. && git clone https://github.com/onosproject/build-tools.git; fi

clean:  ## Remove build/test temp files
	rm -rf dist junit-results.xml .coverage coverage.xml onos_ric_sdk_python.egg-info .tox

clean-all: clean ## clean + remove virtualenv
	rm -rf $(VENV_NAME)

publish: twine # @HELP publish version on github and PyPI
	BASEDIR=. PYPI_INDEX=pypi ./../build-tools/publish-python-version
	./../build-tools/publish-version ${VERSION}

jenkins-publish: build-tools # @HELP Jenkins calls this to publish artifacts
	../build-tools/release-merge-commit

help: ## Print help for each target
	@echo  onos-ric-sdk-py make targets
	@echo
	@grep '^[[:alnum:]_-]*:.* ##' $(MAKEFILE_LIST) \
    | sort | awk 'BEGIN {FS=":.* ## "}; {printf "%-25s %s\n", $$1, $$2};'
