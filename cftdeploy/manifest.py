from .template import *
from .stack import *

import boto3
from botocore.exceptions import ClientError
import os
import sys
import json
import yaml
import re

import logging
logger = logging.getLogger('cft-deploy.manifest')


class CFManifest(object):
    """Class to represent a CloudFormation Template"""

    def __init__(self, manifest_filename, session=None, region=None):
        """Constructs a CFManifest from the manifest file."""
        self.manifest_filename = manifest_filename

        if session is None:
            self.session = boto3.session.Session()
        else:
            self.session = session

        # Read the file
        try:
            with open(manifest_filename, 'r') as stream:
                self.document = yaml.safe_load(stream)
        except yaml.YAMLError as e:
            logger.critical(f"Unable to parse manifest file {manifest_filename}: {e}. Aborting....")
            raise
        except FileNotFoundError as e:
            logger.critical(f"Unable to fine manifest file {manifest_filename}: {e}. Aborting...")
            raise

        self.stack_name = self.document['StackName']
        if region is None:
            self.region = self.document['Region']
        else:
            self.region = region
            self.document['Region'] = region

        # create a CF Client in the correct region
        self.cf_client = self.session.client('cloudformation', region_name=self.region)

        if 'LocalTemplate' in self.document:
            self.template = CFTemplate.read(self.document['LocalTemplate'], self.region)
        else:
            self.template = None

    def override_option(self, key, value):
        """If options are passed in on he command line, these will override the manifest file's value"""
        self.document[key] = value

    def create_stack(self, override=None):
        """ Creates a Stack based on this manifest."""
        logger.info(f"Creating Stack {self.stack_name} in {self.region}")
        try:
            self.fetch_parameters(override=override)
            payload = self.build_cft_payload()
            stack_response = self.cf_client.create_stack(**payload)
            if 'StackId' not in stack_response:
                logger.error("Unable to create stack")
                return(None)
            else:
                my_new_stack = CFStack(self.stack_name, self.region, self.session)
                return(my_new_stack)
        except CFStackDoesNotExistError as e:
            logger.error(f"Could not find new stack {self.stack_name} in {self.region}: {e}")
            return(None)
        except ClientError as e:
            logger.error(f"Error attempting to create {self.stack_name} in {self.region}: {e}")
            return(None)

    def validate(self, override=None):
        """Validate the template's syntax by sending to CloudFormation Service. Returns json from AWS."""

        # These are mutually exclusive
        if 'LocalTemplate' in self.document and 'S3Template' in self.document:
            logger.critical("Manifest contains both 'LocalTemplate' and 'S3Template'")
            return(False)

        self.fetch_parameters(override=override)
        payload = self.build_cft_payload()
        return(payload)

    def fetch_parameters(self, override=None):
        """Based on the manifest's Sourced Parameters, find all the parameters and populate them."""

        param_dict = {}  # we add all the parameters to this dictionary to de-dupe them
        stack_map = {}

        if self.document['Parameters'] is not None:
            # Start with the regular parameters from the Manifest
            for k, v in self.document['Parameters'].items():
                if v is None:
                    logger.warning(f"Parameter {k} has a null value in the manifest file and will be ignored!")
                else:
                    # Python doesn't convert a boolean to a lowercase string which is expected by the CF Service when the template
                    # contains boolean values.
                    if isinstance(v, bool):
                        strv = str(v).lower()
                    elif isinstance(v, list):
                        strv = json.dumps(v)
                    else:
                        strv = str(v)
                    param_dict[k] = {'ParameterKey': k, 'ParameterValue': strv, 'UsePreviousValue': False}

        # This is a legacy hold-over from deploy-stack.rb. If encountered, I'd rather be forced to fix the manifest than
        # maintain code to support both methods, when the Placeholder: full-stack-name makes the SourcedParams section better
        if 'DependsOnStacks' in self.document:
            logger.critical("DependsOnStacks Not yet implemented")
            raise NotImplementedError

        try:
            if 'DependentStacks' in self.document and self.document['DependentStacks'] is not None:
                # The new way
                for source_key, source_stack_name in self.document['DependentStacks'].items():
                    my_stack = CFStack(source_stack_name, self.region, self.session)
                    if my_stack is None or my_stack.get() is None:
                        logger.error(f"Creating stack object for {source_stack_name} returned None")
                        raise CFStackDoesNotExistError(source_stack_name)
                    stack_map[source_key] = my_stack
        except CFStackDoesNotExistError as e:
            logger.critical(f"Could not find dependent stack {source_stack_name} in {self.region}: {e}")
            raise
        except ClientError as e:
            logger.critical(f"Error attempting to create {self.stack_name} in {self.region}: {e}")
            raise

        if 'SourcedParameters' in self.document and self.document['SourcedParameters'] is not None:
            for k, v in self.document['SourcedParameters'].items():
                (stack_map_key, section, resource_id) = v.split('.')
                if stack_map_key not in stack_map:
                    logger.error(f"DependentStack {stack_map_key} was required by {k} but was not found or referenced.")
                    continue
                source_stack = stack_map[stack_map_key]
                if section == "Parameters":
                    params = source_stack.get_parameters()
                    if resource_id in params:
                        param_dict[k] = {'ParameterKey': k, 'ParameterValue': params[resource_id], 'UsePreviousValue': False}
                    else:
                        logger.error(f"Unable to find {resource_id} in {source_stack.stack_name} (aliased as {stack_map_key}) Parameters")
                        raise StackLookupException
                elif section == "Outputs":
                    outputs = source_stack.get_outputs()
                    if resource_id in outputs:
                        param_dict[k] = {'ParameterKey': k, 'ParameterValue': outputs[resource_id], 'UsePreviousValue': False}
                    else:
                        logger.error(f"Unable to find {resource_id} in {source_stack.stack_name} (aliased as {stack_map_key}) Outputs")
                        raise StackLookupException
                elif section == "Resources":
                    resources = source_stack.get_resources()
                    if resource_id in resources:
                        param_dict[k] = {'ParameterKey': k, 'ParameterValue': resources[resource_id], 'UsePreviousValue': False}
                    else:
                        logger.error(f"Unable to find {resource_id} in {source_stack.stack_name} (aliased as {stack_map_key}) Resources")
                        raise StackLookupException
                else:
                    logger.error(f"Invaluid SourcedParameters section type: {section}")

        # Finally, any parameters passed in as an override take precedence
        if override is not None:
            for k, v in override.items():
                param_dict[k] = {'ParameterKey': k, 'ParameterValue': v, 'UsePreviousValue': False}

        # Now make it the array the CF Service wants
        self.params = []
        for k, v in param_dict.items():
            self.params.append(v)

        return(True)

    def build_cft_payload(self):
        """Generate the CFT Payload"""
        stack_policy_body = {
            'Statement': self.document['StackPolicy']
        }

        # Start with the general structure
        payload = {
            'StackName':        self.document['StackName'],
            'Parameters':       self.params,
            'Capabilities':     ['CAPABILITY_NAMED_IAM', 'CAPABILITY_AUTO_EXPAND'],
            'Tags':             [],
        }

        # These elements may or may not be in the manifest and should be handled accordingly.
        if 'TerminationProtection' in self.document:
            payload['EnableTerminationProtection'] = self.document['TerminationProtection']
        if 'TimeOut' in self.document:
            payload['TimeoutInMinutes'] = int(re.sub("\D", "", self.document['TimeOut']))
        if 'OnFailure' in self.document:
            payload['OnFailure'] = self.document['OnFailure']
        if 'StackPolicy' in self.document:
            payload['StackPolicyBody'] = json.dumps(stack_policy_body)

        # Now make the decision on what to tell CF about the template
        if 'LocalTemplate' in self.document:
            payload['TemplateBody'] = self.template.template_body
        elif 'S3Template' in self.document:
            payload['TemplateURL'] = self.document['S3Template']
        else:
            logger.critical("Neither 'TemplateBody' nor 'TemplateURL' found in manifest")
            return(False)

        # format and add the tags
        if 'Tags' in self.document:
            for k, v in self.document['Tags'].items():
                payload['Tags'].append({'Key': k, 'Value': v})

        return(payload)

    def estimate_cost(self):
        """Return a url to the simple monthly cost estimator for this template / parameter set."""
        self.fetch_parameters()
        response = self.cf_client.estimate_template_cost(
            TemplateBody=self.template.template_body,
            Parameters=self.params
        )
        return(response['Url'])


class StackLookupException(Exception):
    """Thrown when the cross-stack lookup fails to find a specified Resource, Parameter or Output"""
    pass
