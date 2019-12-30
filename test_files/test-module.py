#!/usr/bin/env python3

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

from cftdeploy._version import __version__, __version_info__
from cftdeploy.manifest import *
from cftdeploy.stack import *
from cftdeploy.template import *



import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--stack-name", help="StackName to Create", required=True)
parser.add_argument("--vpc-stack-name", help="VPC StackName", required=True)
parser.add_argument("--region", help="AWS Region to run the test", required=True)
args = parser.parse_args()



stack_name = args.stack_name
region = args.region
template_file_name = "test_files/PythonTest-Template.yaml"

my_template = CFTemplate.read(template_file_name, region)

# Initalize a blank stack
mystack = CFStack(stack_name, region)

# Load the created VPC Stack
vpc_stack = CFStack(args.vpc_stack_name, region)
vpc_stack.get()
vpc_outputs = vpc_stack.get_outputs()

my_tags = [
    {
        "Key": "contact-email",
        "Value": "chris@chrisfarris.com"
    },
    {
        "Key": "environment",
        "Value": "testing"
    }
]

my_parms = {
    'pVpcId': vpc_outputs['VpcId'],
    'pOpenNetMask': "192.168.10.0/24"
}

stack_id = mystack.create(template=my_template, params=my_parms, tags=my_tags, OnFailure=None, TerminationProtection=False, TimeoutInMinutes=5)

if stack_id is None:
    print(f"Failed to create {stack_name}")
    exit(1)

# Get stack attributes
mystack.get()

print(f"Sleeping 30 for stack {stack_name}/{mystack.StackId} to create")
time.sleep(30)
mystack.get()
if mystack.StackStatus == "CREATE_COMPLETE":
    print("Stack Created Successfully")
else:
    print(f"Stack not created. Status: {mystack.StackStatus}")

print(f"Deleting {stack_name}/{mystack.StackId}")
mystack.delete()





