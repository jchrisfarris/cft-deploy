#!/usr/bin/env python

import boto3
from botocore.exceptions import ClientError
import os
import sys
import json
import yaml
import argparse
import time
from datetime import tzinfo
from difflib import unified_diff

from ._version import __version__, __version_info__
from .manifest import *
from .stack import *
from .template import *

import logging
logger = logging.getLogger('cft-deploy')


def cft_get_events():
    """Entrypoint to list events for a stack."""
    parser = argparse.ArgumentParser(description="List Stack Events")
    parser.add_argument("--stack-name", help="Stackname to search", required=True)
    args = do_args(parser)

    try:
        my_stack = CFStack(args.stack_name, args.region)
        my_stack.get()
    except CFStackDoesNotExistError as e:
        print("Failed to Find stack. Aborting....")
        exit(1)

    # Now display the events
    events = my_stack.get_stack_events()
    last_event = print_events(events, None)
    while my_stack.get_status() in StackTempStatus:
        time.sleep(2)
        events = my_stack.get_stack_events(last_event_id=last_event)
        print_events(events, last_event)

    status = my_stack.get_status()
    if status in StackGoodStatus:
        print(f"{my_manifest.stack_name} successfully deployed: \033[92m{status}\033[0m")
        exit(0)
    else:
        print(f"{my_manifest.stack_name} failed deployment: \033[91m{status}\033[0m")
        exit(1)


def cft_deploy():
    """Entrypoint to deploy the Cloudformation stack as specified by the manifest."""
    parser = argparse.ArgumentParser(description="Deploy a cft-tool manifest")
    parser.add_argument("-m", "--manifest", help="Manifest file to deploy", required=True)
    parser.add_argument("--template-url", help="Override the manifest with this Template URL")
    parser.add_argument("--override-region", help="Override the region defined in the manifest with this value")
    parser.add_argument("--force", help="Force the stack update even if the stack is in a non-normal state", action='store_true')
    parser.add_argument("--update-stack-policy", help="Override the existing stack policy for this update", action='store_true')
    parser.add_argument("--interactive", help="Create a change set and display it before executing the change", action='store_true')
    parser.add_argument("overrideparameters", help="Optional parameter override of the manifest", nargs='*')
    args = do_args(parser)
    logger.info(f"Deploying {args.manifest}")

    # Flag the non-implemented stuff
    if args.interactive or args.update_stack_policy:
        raise NotImplementedError

    try:
        if args.override_region:
            my_manifest = CFManifest(args.manifest, region=args.override_region)
        else:
            my_manifest = CFManifest(args.manifest)
    except Exception:
        exit(1)

    # TODO: Process override stuff
    if args.template_url:
        my_manifest.override_option("S3Template", args.template_url)

    override = process_override_params(args)

    # Now see if the stack exists, if it doesn't then create, otherwise update
    try:
        my_stack = CFStack(my_manifest.stack_name, my_manifest.document['Region'])
        stack_id = my_stack.get()
        if stack_id is None:
            print(f"Cannot find a stack named {my_manifest.stack_name}")
            exit(1)

        # Only if the stack is in a normal status (or --force is specified) do we update
        status = my_stack.get_status()
        if status not in StackGoodStatus and args.force is not True:
            print(f"Stack {my_stack.stack_name} is in status {status} and --force was not specified. Aborting....")
            exit(1)

        rc = my_stack.update(manifest=my_manifest, override=override)
        if rc is None:
            print("Failed to Find or Update stack. Aborting....")
            exit(1)
    except CFStackDoesNotExistError as e:
        logger.info(e)
        try:
            # Then we're creating the stack
            my_stack = my_manifest.create_stack(override=override)
            if my_stack is None:
                print("Failed to Create stack. Aborting....")
                exit(1)
            my_stack.get()
        except Exception as e:
            exit(1)

    # Now display the events
    events = my_stack.get_stack_events()
    last_event = print_events(events, None)
    while my_stack.get_status() in StackTempStatus:
        time.sleep(5)
        events = my_stack.get_stack_events(last_event_id=last_event)
        last_event = print_events(events, last_event)

    # Finish up with an status message and the appropriate exit code
    status = my_stack.get_status()
    if status in StackGoodStatus:
        print(f"{my_manifest.stack_name} successfully deployed: \033[92m{status}\033[0m")
        exit(0)
    else:
        print(f"{my_manifest.stack_name} failed deployment: \033[91m{status}\033[0m")
        exit(1)


def print_events(events, last_event):
    # Events is structured as such:
    # [
    #     {
    #         'StackId': 'arn:aws:cloudformation:ap-southeast-1:123456789012:stack/CHANGEME1/87b04ec0-5a46-11e9-b6d5-0200beb62082',
    #         'EventId': '87b11210-5a46-11e9-b6d5-0200beb62082',
    #         'StackName': 'CHANGEME1',
    #         'LogicalResourceId': 'CHANGEME1',
    #         'PhysicalResourceId': 'arn:aws:cloudformation:ap-southeast-1:123456789012:stack/CHANGEME1/87b04ec0-5a46-11e9-b6d5-0200beb62082',
    #         'ResourceType': 'AWS::CloudFormation::Stack',
    #         'Timestamp': datetime.datetime(2019, 4, 8, 21, 37, 38, 284000, tzinfo=tzutc()),
    #         'ResourceStatus': 'CREATE_IN_PROGRESS',
    #         'ResourceStatusReason': 'User Initiated'
    #     }
    # ]
    if len(events) == 0:
        return(last_event)
    for e in events:
        # Colors!
        if e['ResourceStatus'] in ResourceTempStatus:
            status = f"\033[93m{e['ResourceStatus']}\033[0m"
        elif e['ResourceStatus'] in ResourceBadStatus:
            status = f"\033[91m{e['ResourceStatus']}\033[0m"
        elif e['ResourceStatus'] in ResourceGoodStatus:
            status = f"\033[92m{e['ResourceStatus']}\033[0m"
        else:
            status = e['ResourceStatus']

        if 'ResourceStatusReason' in e and e['ResourceStatusReason'] != "":
            reason = f": {e['ResourceStatusReason']}"
        else:
            reason = ""
        print(f"{e['Timestamp'].astimezone().strftime('%Y-%m-%d %H:%M:%S')} {e['LogicalResourceId']} ({e['ResourceType']}): {status} {reason}")
    return(e['EventId'])


def cft_get_resource():
    """Get a resource's physical ID. Can be specified multiple times."""
    parser = argparse.ArgumentParser(description="Get Resource IDs by Logical Id")
    parser.add_argument("--stack-name", help="Stackname to search", required=True)
    parser.add_argument("--logical-id", help="Logical ID(s) to find", required=True, nargs='+')
    args = do_args(parser)
    print(f"Looking for {args.logical_id} in {args.stack_name}")
    raise NotImplementedError
    exit(0)


def cft_get_output():
    """Get a resource's physical ID. Can be specified multiple times."""
    parser = argparse.ArgumentParser(description="Get Resource IDs by Logical Id")
    parser.add_argument("--stack-name", help="Stackname to search", required=True)
    parser.add_argument("--output-key", help="Stack Output to return", required=True)
    args = do_args(parser)
    logger.debug(f"Looking for {args.output_key} in {args.stack_name}")

    try:
        my_stack = CFStack(args.stack_name, args.region)
        my_stack.get()
        stack_outputs = my_stack.get_outputs()

        if args.output_key not in stack_outputs:
            logger.critical(f"Failed to find output {args.output_key} in stack {args.stack_name} in region {args.stack_name}.")
            exit(1)
        else:
            print(stack_outputs[args.output_key])
            exit(0)

    except CFStackDoesNotExistError as e:
        logger.critical(f"Failed to find stack {args.stack_name} in region {args.region}. Aborting....")
        exit(1)

    exit(0)


def cft_validate():
    """Entrypoint to Validate a Cloudformation Template File."""
    parser = argparse.ArgumentParser(description="Validate a Cloudformation Template File")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-t", "--template", help="CFT Filename to validate")
    group.add_argument("--s3-url", help="CFT S3 URL to validate")
    args = do_args(parser)

    if args.template:
        logger.debug(f"Validating {args.template}")
        my_template = CFTemplate.read(args.template, args.region)
    elif args.s3_url:
        logger.debug(f"Validating {args.s3_url}")
        (bucket, object_key) = CFTemplate.parse_s3_url(args.s3_url)
        logger.debug(f"Fetching {object_key} from {bucket}")
        my_template = CFTemplate.download(bucket, object_key, args.region)

    try:
        status = my_template.validate()
        if status is None:
            print("Error Validating Template")
            exit(1)
        else:
            print(f"Template {args.template} is valid")
            exit(0)
    except CFTemplateTooLargeError:
        parser.print_help()
        print(f"\n\nTemplate {args.template} exceeds the maximum length for local templates")
        print("Please upload the file to S3, then call cfg-validate with the --s3-url option")


def cft_validate_manifest():
    """Entrypoint to Validate a Cloudformation Template File."""
    parser = argparse.ArgumentParser(description="Validate a Cloudformation Template File and its associated Manifest")
    parser.add_argument("--price", help="Return a link for a simple calculator pricing worksheet", action='store_true')
    parser.add_argument("--template-url", help="Override the manifest with this Template URL")
    parser.add_argument("--override-region", help="Override the region defined in the manifest with this value")
    parser.add_argument("-m", "--manifest", help="Manifest file to deploy", required=True)
    parser.add_argument("overrideparameters", help="Optional parameter override of the manifest", nargs='*')
    args = do_args(parser)
    logger.debug(f"Validating {args.manifest}")

    if args.override_region:
        my_manifest = CFManifest(args.manifest, region=args.override_region)
    else:
        my_manifest = CFManifest(args.manifest)

    override = process_override_params(args)

    if args.template_url:
        my_manifest.override_option("S3Template", args.template_url)

    if args.price:
        url = my_manifest.estimate_cost()
        print(f"Cost Estimate URL: {url}")
        exit(0)

    try:
        status = my_manifest.validate(override=override)
        if status is False:
            print("Error Validating Manifest")
            exit(1)
        else:
            if args.json:
                print(json.dumps(status, sort_keys=True, indent=2))
            else:
                print(f"Manifest {args.manifest} is valid")
                print(f"Stack Name: {my_manifest.stack_name} in region {my_manifest.region}")
                print("Resolved Parameters:")
                for p in my_manifest.params:
                    print(f"\t{p['ParameterKey']}: {p['ParameterValue']}")
            exit(0)
    except CFStackDoesNotExistError as e:
        print(f"Stack {e.stackname} doesn't exist. Unable to validate manifest.")
        exit(1)
    except StackLookupException as e:
        exit(1)

def cft_upload():
    """Entrypoint to upload a Cloudformation Template File to s3."""
    parser = argparse.ArgumentParser(description="Upload a Cloudformation Template File")
    parser.add_argument("-t", "--template", help="CFT Filename to upload", required=True)
    parser.add_argument("-b", "--bucket", help="Bucket to upload to", required=True)
    parser.add_argument("-o", "--object-key", help="object key to upload as", required=True)
    args = do_args(parser)
    logger.info(f"Uploading {args.template} to s3://{args.bucket}/{args.object_key}")
    my_template = CFTemplate.read(args.template, args.region)
    try:
        status = my_template.upload(args.bucket, args.object_key)
        print(f"Template {args.template} uploaded to {status}")
        exit(0)
    except ClientError as e:
        print(f"Failed to upload Template {args.template}: {e}")
        exit(1)


def cft_generate_manifest():
    """Entrypoint to generate manifest file based on the CloudFormation Template."""
    parser = argparse.ArgumentParser(description="Generate Manifest file")
    parser.add_argument("-m", "--manifest", help="Manifest file to output", required=True)
    parser.add_argument("--stack-name", help="Set the stackname to this in the Manifest File")
    parser.add_argument("--termination-protection", help="Set termination protection to true in the Manifest File", action='store_true')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-t", "--template", help="CFT Filename to validate")
    group.add_argument("--s3-url", help="CFT S3 URL to validate")
    args = do_args(parser)
    logger.info(f"Generating {args.manifest} from {args.template}")

    if args.template:
        logger.info(f"Generating Manifest file {args.manifest} from {args.template}")
        source = args.template
        my_template = CFTemplate.read(args.template, args.region)
    elif args.s3_url:
        logger.info(f"Generating Manifest file {args.manifest} from {args.s3_url}")
        source = args.s3_url
        (bucket, object_key) = CFTemplate.parse_s3_url(args.s3_url)
        if bucket == None or object_key == None:
            logger.critical(f"Invalid S3 URL. Cannot extract bucket or object. Aborting")
            exit(1)
        logger.debug(f"Fetching {object_key} from {bucket}")
        my_template = CFTemplate.download(bucket, object_key, args.region)

    subsitutions = {}
    if args.stack_name:
        subsitutions['stack_name'] = args.stack_name
    if args.termination_protection:
        subsitutions['termination_protection'] = args.termination_protection
    if args.region:
        subsitutions['region'] = args.region

    try:
        foo = my_template.generate_manifest(args.manifest, substitutions=subsitutions)
        print(f"Generated Manifest file {args.manifest} from {source}")
        exit(0)
    except CFTemplateTooLargeError:
        parser.print_help()
        print(f"\n\nTemplate {args.template} exceeds the maximum length for local templates")
        print("Please upload the file to S3, then call cfg-generate-manifest with the --s3-url option")
    except yaml.scanner.ScannerError as e:
        print("CFT Default Params have an invalid yaml value. Double check quoting before deploying")


def cft_delete():
    """Delete --stack-name."""
    parser = argparse.ArgumentParser(description="Delete a stack")
    parser.add_argument("--stack-name", help="Stackname to Delete", required=True)
    parser.add_argument("--no-status", help="Don't display the progress of the delete", action='store_true')
    args = do_args(parser)
    print(f"Deleting {args.stack_name}")
    try:
        my_stack = CFStack(args.stack_name, args.region)
        my_stack.get()
    except CFStackDoesNotExistError as e:
        print("Failed to Find stack. Aborting....")
        exit(1)

    my_stack.delete()
    if args.no_status:
        exit(0)

    # Now display the events
    events = my_stack.get_stack_events()
    last_event = print_events(events, None)
    while my_stack.get_status() in StackTempStatus:
        time.sleep(5)
        events = my_stack.get_stack_events(last_event_id=last_event)
        last_event = print_events(events, last_event)

    status = my_stack.get_status()
    if status in ["DELETE_COMPLETE"]:
        print(f"{args.stack_name} successfully deleted: \033[92m{status}\033[0m")
        exit(0)
    else:
        print(f"{args.stack_name} failed to delete: \033[91m{status}\033[0m")
        exit(1)


def cft_diff():
    """Delete --stack-name."""
    parser = argparse.ArgumentParser(description="Compare new Template to existing template from a stack")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-t", "--template", help="CFT Filename to validate")
    group.add_argument("--s3-url", help="CFT S3 URL to validate")
    parser.add_argument("--stack-name", help="Stackname to search", required=True)
    args = do_args(parser)

    if args.template:
        template_1 = CFTemplate.read(args.template, args.region)
    elif args.s3_url:
        (bucket, object_key) = CFTemplate.parse_s3_url(args.s3_url)
        template_1 = CFTemplate.download(bucket, object_key, args.region)

    try:
        my_stack = CFStack(args.stack_name, args.region)
        my_stack.get()
    except CFStackDoesNotExistError as e:
        print("Failed to Find stack. Aborting....")
        exit(1)

    print(f"comparing stack: {my_stack.stack_name} and template {template_1}")
    template_2 = my_stack.get_template()

    s1 = template_1.template_body.split('\n')
    s2 = template_2.template_body.split('\n')

    for line in unified_diff(s1, s2, fromfile=my_stack.stack_name, tofile=str(template_1)):
        sys.stdout.write(line + "\n")

    exit(1)


def version():
    print(__version__)
    exit(0)


def do_args(parser):

    parser.add_argument("--debug", help="print debugging info", action='store_true')
    parser.add_argument("-s", "--silent", help="Be Silent. Print error info only", action='store_true')
    parser.add_argument("--json", help="Return Data in json format", action='store_true')
    parser.add_argument("--env", help="Return data in bash env format", action='store_true')
    parser.add_argument("--version", help="print cft-deploy version", action='store_true')
    parser.add_argument("--region", help="AWS Region", default=os.environ['AWS_DEFAULT_REGION'])
    args = parser.parse_args()

    if args.version:
        version()

    # Logging idea stolen from: https://docs.python.org/3/howto/logging.html#configuring-logging
    # create console handler and set level to debug
    ch = logging.StreamHandler()
    if args.debug:
        logger.setLevel(logging.DEBUG)
    elif args.silent:
        logger.setLevel(logging.ERROR)
    else:
        logger.setLevel(logging.INFO)
    # create formatter
    # formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
    # add formatter to ch
    ch.setFormatter(formatter)
    # add ch to logger
    logger.addHandler(ch)

    logger.setLevel(logging.INFO)
    # Quiet Boto3
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('boto3').setLevel(logging.WARNING)

    return(args)


def process_override_params(args):
    params = {}
    if not args.overrideparameters:
        return(None)

    for p in args.overrideparameters:
        k, v = p.split("=")
        params[k] = v

    return(params)
