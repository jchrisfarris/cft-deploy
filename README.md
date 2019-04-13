# cft-deploy
Python module & scripts for managing AWS CloudFormation Stacks

## Rationale

CloudFormation is a valuable tool, but it has some short-comings with the management of stacks via the CLI.

* The number of options and parameters that the `aws cloudformation create-stack` command is pretty large, and when using CLI/SDK you need a consistent way to manage that. Here are the options in the AWS CLI:

```Bash
--stack-name
[--template-body ]
[--template-url ]
[--parameters ]
[--disable-rollback | --no-disable-rollback]
[--timeout-in-minutes ]
[--notification-arns ]
[--capabilities ]
[--resource-types ]
[--role-arn ]
[--on-failure ]
[--stack-policy-body ]
[--stack-policy-url ]
[--tags ]
```

* While stacks can export a value, the exported value's key must be unique in the region. Furthermore you cannot provide the corresponding imported value's key as a parameter. It must be hard-coded in the CFT. As a result you cannot have a single template that works for dev, test & prod that leverages different exported values.
* If a stack exports a value, you are significantly impaired from modifying that stack. AWS puts these protections in place for your own protection, however in some cases you might not want to have to delete a dependent stack before modifying the exporting stack.
* ```aws cloudformation create-stack``` is something of a fire & forget operation. Yes, you can use the CLI to setup a waiter. But lets face it, that's pretty complex.


cft-deploy is designed to help with some of these issues.

* cft-deploy uses the concept of a **manifest file** to store all of the parameters and stack options. These manifest files are in yaml and can be kept in revision control
* cft-deploy can go lookup parameters from another stack's parameters, resources or outputs. This is useful for example, if you have a template that deploys a VPC and you need to reference the vpcId, subnetIds and security groups in a template that deploys an instance or rds.
* cft-deploy's parameter lookup doesn't require regionally scoped global variables. The manifest file can contain the name of the stack you want to reference
* cft-deploy will display the status of the stack creation & update similar to how the progress is displayed in the AWS console.
* cft-deploy supports [stack policies](http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/protect-stack-resources.html#stack-policy-reference) in the manifest file.
* cft-deploy can generate manifest files from templates (and in the future will generate manifest files from existing stacks)


## Installation

For testing, the install process is
```bash
pip install -e .
```

For production usage, you can install cft-deploy from PyPi. (Not implemented just yet)

## Usage

### Manifest Files

### Scripts

* **cft-validate** - Will validate a template with the AWS CloudFormation service
* **cft-upload** - Will upload a CFT to S3, which is required if the template is over a certian size
* **cft-generate-manifest** - Will take a local or s3-hosted template, and generate a manifest file
* **cft-validate-manifest** - Will perform all of the parameter substitutions and validate that dependencies exist
* **cft-deploy** - Will take the manifest (and optional command-line params) and create or update the stack (providing a tail -f like experience of the events)
* **cft-delete** - Will delete the specified stack (providing a tail -f like experience of the deletion events)


### Python Module

The Python Modules consists of three main classes. All the classes support a Session being passed in which would support cross-account role assumption (among other things).

All modules use the python logger for debug and informational events. These can be overridden as needed.

#### CFTemplate
CFTemplate represents a CloudFormation Template

    class CFTemplate(builtins.object)
     |  CFTemplate(template_body, filename=None, s3url=None, session=None)
     |
     |  Class to represent a CloudFormation Template
     |
     |  Methods defined here:
     |
     |  __init__(self, template_body, filename=None, s3url=None, session=None)
     |      Constructs a CFTemplate from the template_body (json or yaml).
     |
     |  diff(self, other_template)
     |      prints out the differences between this template and another one.
     |
     |  generate_manifest(self, manifest_file_name, substitutions=None)
     |      Generates a stub manifest file for this template and writes it to manifest_file_name.
     |      If substitutions are specified, these are populated into the stub manifest file.
     |
     |  upload(self, bucket, object_key)
     |      Upload the template to S3.
     |
     |  validate(self)
     |      Validate the template's syntax by sending to CloudFormation Service. Returns json from AWS.
     |
     |  ----------------------------------------------------------------------
     |  Class methods defined here:
     |
     |  download(bucket, object_key, session=None)
     |      Downloads the template from S3 and then initialize.
     |
     |  parse_s3_url(s3url)
     |      Parse an s3url (s3://bucket/object_key) and return the bucket and object_key
     |
     |  read(filename, session=None)
     |      Read the template from filename and then initialize.

The exception *CFTemplateTooLargeError* is defined where the template must be uploaded to S3 before the AWS CloudFormation service can use it.

#### CFManifest

    class CFManifest(builtins.object)
     |  CFManifest(manifest_filename, session=None)
     |
     |  Class to represent a CloudFormation Template
     |
     |  Methods defined here:
     |
     |  __init__(self, manifest_filename, session=None)
     |      Constructs a CFManifest from the manifest file.
     |
     |  build_cft_payload(self)
     |      Generate the CFT Payload
     |
     |  create_stack(self, override=None)
     |      Creates a Stack based on this manifest.
     |
     |  estimate_cost(self)
     |      Return a url to the simple monthly cost estimator for this template / parameter set.
     |
     |  fetch_parameters(self, override=None)
     |      Based on the manifest's Sourced Parameters, find all the parameters and populate them.
     |
     |  override_option(self, key, value)
     |      If options are passed in on he command line, these will override the manifest file's value
     |
     |  validate(self, override=None)
     |      Validate the template's syntax by sending to CloudFormation Service. Returns json from AWS.

#### CFStack

    class CFStack(builtins.object)
     |  CFStack(stack_name, region, session=None)
     |
     |  Class to represent a CloudFormation Template
     |
     |  Methods defined here:
     |
     |  __init__(self, stack_name, region, session=None)
     |      Constructs a CFTemplate from the template_body (json or yaml).
     |
     |  create_changeset(self, changeset_name)
     |      Trigger the creation of the changeset.
     |
     |  delete(self)
     |      Deletes this stack.
     |
     |  describe_changeset(self, changeset_name)
     |      Get the details of changes from a previously created changeset.
     |
     |  detect_drift(self)
     |      Triggers Drift Detection for this stack.
     |
     |  get(self)
     |      Fetch the latest set of data for this stack from AWS and update properties of the instance.
     |
     |  get_outputs(self)
     |      Return a dict of each output of this stack.
     |
     |  get_parameters(self)
     |      Return a dict of each parameter to this stack.
     |
     |  get_resources(self)
     |      Return all the PhysicalResourceIds for each LogicalId in the template
     |
     |  get_stack_events(self, last_event_id=None)
     |      Return all stack events since last_event_id.
     |
     |  get_status(self)
     |      Fetch the value of StackStatus from AWS CF API for this stack
     |
     |  get_template(self)
     |      Return as a CFTemplate the current template for this stack.
     |
     |  list_changesets(self)
     |      List all active changesets for this stack.
     |
     |  update(self, manifest)
     |      Updates a Stack based on this manifest.

Exceptions defined for this class are
* *CFStackDoesNotExistError* - which has an attribute of stackname

## Roadmap

1. Support for CloudFormation Changesets, so you can see what an update will do to the stack before you execute it.
3. Support for CloudFormation drift detection.
4. Support for generating a unix-like diff of an existing stack's template and a proposed update to the template.
2. Support for generating Manifest files from existing stacks.

