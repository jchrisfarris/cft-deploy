

# Static, not sure if needed??
PYTHON=python3
PIP=pip3

FILES=setup.py

## Testing Stuff
export BUCKET=cft-deploy-ap-southeast-1
export TEST_REGION=ap-southeast-1

ifndef STACK_NAME
$(error STACK_NAME is not set)
endif

ifndef version
	export version := $(shell date +%Y%b%d-%H%M)
endif

ifndef verbose
	export verbose := -s
endif


# The full name of the stack in Cloudformation. This must match the manifest file
export FULL_STACK_NAME=$(STACK_NAME)-$(version)

export MANIFEST?=test_files/$(FULL_STACK_NAME)-Manifest.yaml
export STACK_TEMPLATE=test_files/$(STACK_NAME)-Template.yaml

# For uploading CFT to S3
export TEMPLATE_KEY ?= test-templates/$(STACK_NAME)-Template-$(version).yaml
export TEMPLATE_URL ?= https://s3.amazonaws.com/$(BUCKET)/$(TEMPLATE_KEY)
export TEMPLATE_S3URL ?= s3://$(BUCKET)/$(TEMPLATE_KEY)


clean:
	rm -rf __pycache__ *.zip *.dist-info *.egg-info

test:
	cd cftdeploy && $(MAKE) test
	for f in $(FILES); do $(PYTHON) -m py_compile $$f; if [ $$? -ne 0 ] ; then echo "$$f FAILS" ; exit 1; fi done

pep8:
	cd cftdeploy && $(MAKE) pep8

deps:
	$(PIP) install -r requirements.txt -t . --upgrade


## Testing Targets

test-validate:
	cft-validate -t $(STACK_TEMPLATE) $(verbose)

test-upload:
	cft-upload -t $(STACK_TEMPLATE) -b $(BUCKET) -o $(TEMPLATE_KEY) $(verbose)

test-s3-validate:
	cft-validate --s3-url $(TEMPLATE_S3URL) $(verbose)

# Generate a manifest, then set is aside to use a completed one
test-manifest:
	cft-generate-manifest -m $(MANIFEST) -t $(STACK_TEMPLATE) --stack-name $(FULL_STACK_NAME) --region $(TEST_REGION) $(verbose)
	cp $(MANIFEST) $(MANIFEST)-Preserved.yaml
	sed s/CHANGEME/$(FULL_STACK_NAME)/g test_files/$(STACK_NAME)-Manifest-Complete.yaml > $(MANIFEST)

test-manifest-validate:
	cft-validate-manifest -m $(MANIFEST)

test-deploy:
	cft-deploy -m $(MANIFEST)

test-delete:
	cft-delete --stack-name $(FULL_STACK_NAME)

test-everything: test test-validate test-upload test-s3-validate test-manifest test-manifest-validate test-deploy test-delete