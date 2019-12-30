

# Static, not sure if needed??
PYTHON=python3
PIP=pip3

FILES=setup.py

## Testing Stuff
export BUCKET=cft-deploy-ap-southeast-1
export TEST_REGION=ap-southeast-1

ifndef version
	export version := $(shell date +%Y%b%d-%H%M)
endif

ifndef verbose
	export verbose := -s
endif

STACK_NAME=VPCTest
STACK_NAME2=SGTest


# The full name of the stack in Cloudformation. This must match the manifest file
export FULL_STACK_NAME=$(STACK_NAME)-$(version)
export MANIFEST?=test_files/$(FULL_STACK_NAME)-Manifest.yaml
export STACK_TEMPLATE=test_files/$(STACK_NAME)-Template.yaml

# This is the second stack which references the first
export FULL_STACK_NAME2=$(STACK_NAME2)-$(version)
export MANIFEST2?=test_files/$(FULL_STACK_NAME2)-Manifest.yaml
export STACK_TEMPLATE2=test_files/$(STACK_NAME2)-Template.yaml

# For uploading CFT to S3
export TEMPLATE_KEY ?= test-templates/$(STACK_NAME)-Template-$(version).yaml
export TEMPLATE_URL ?= https://s3.amazonaws.com/$(BUCKET)/$(TEMPLATE_KEY)
export TEMPLATE_S3URL ?= s3://$(BUCKET)/$(TEMPLATE_KEY)


clean:
	rm -rf __pycache__ *.zip *.dist-info *.egg-info cftdeploy/__pycache__ test_files/*Manifest.yaml

test:
	cd cftdeploy && $(MAKE) test
	for f in $(FILES); do $(PYTHON) -m py_compile $$f; if [ $$? -ne 0 ] ; then echo "$$f FAILS" ; exit 1; fi done

pep8:
	cd cftdeploy && $(MAKE) pep8

deps:
	$(PIP) install -r requirements.txt -t . --upgrade


## Testing Targets

test-validate:
	cft-validate -t $(STACK_TEMPLATE) $(verbose) --region $(TEST_REGION)
	cft-validate -t $(STACK_TEMPLATE2) $(verbose) --region $(TEST_REGION)

test-upload:
	cft-upload -t $(STACK_TEMPLATE) -b $(BUCKET) -o $(TEMPLATE_KEY) $(verbose)

test-s3-validate:
	cft-validate --s3-url $(TEMPLATE_S3URL) $(verbose) --region $(TEST_REGION)

# Generate a manifest, then set is aside to use a completed one
test-manifest:
	cft-generate-manifest -m $(MANIFEST) -t $(STACK_TEMPLATE) --stack-name $(FULL_STACK_NAME) --region $(TEST_REGION) $(verbose)
	cp $(MANIFEST) $(MANIFEST)-Preserved.yaml
	sed s/CHANGEME/$(FULL_STACK_NAME)/g test_files/$(STACK_NAME)-Manifest-Complete.yaml > $(MANIFEST)

test-manifest-validate:
	cft-validate-manifest -m $(MANIFEST)

test-deploy:
	cft-deploy -m $(MANIFEST) --template-url $(TEMPLATE_S3URL)

test-manifest2-validate:
	sed s/CHANGEME/$(FULL_STACK_NAME2)/g test_files/$(STACK_NAME2)-Manifest-Complete.yaml | sed s/FULL_STACK_NAME/$(FULL_STACK_NAME)/g > $(MANIFEST2)
	cft-validate-manifest -m $(MANIFEST2)

test-python-create:
	./test_files/test-module.py --vpc-stack-name $(FULL_STACK_NAME) --stack-name python-$(version) --region $(TEST_REGION)

test-deploy2:
	cft-deploy -m $(MANIFEST2)

test-update:
	sed s/CHANGEME/$(FULL_STACK_NAME)/g test_files/$(STACK_NAME)-Manifest-Update.yaml > $(MANIFEST)-Update
	cft-deploy -m $(MANIFEST)-Update
	rm $(MANIFEST)-Update

test-delete:
	cft-delete --stack-name $(FULL_STACK_NAME2) --region $(TEST_REGION)
	cft-delete --stack-name $(FULL_STACK_NAME) --region $(TEST_REGION)

test-clean:
	rm -f test_files/*Manifest.yaml test_files/*Manifest.yaml-Preserved.yaml

test-stack1: test test-validate test-upload test-s3-validate test-manifest test-manifest-validate test-deploy

test-stack2: test-manifest2-validate test-deploy2

test-everything: test-stack1 test-python-create test-stack2 test-delete test-clean


## PyPi Build & Release
build-deps:
	$(PYTHON) -m pip install --user --upgrade setuptools wheel twine

build:
	$(PYTHON) setup.py sdist bdist_wheel

dist-clean:
	rm -rf dist build

# Twine usage: https://github.com/pypa/twine
dist-upload: dist-clean build
	$(PYTHON) -m twine check dist/*
	$(PYTHON) -m twine upload dist/* --verbose

