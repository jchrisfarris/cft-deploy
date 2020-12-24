
import boto3
from botocore.exceptions import ClientError
import os
import sys
import json
import datetime
import dateutil.parser

from .template import *

import logging
logger = logging.getLogger('cft-deploy.stack')


ResourceGoodStatus      = ["CREATE_COMPLETE", "UPDATE_COMPLETE"]
ResourceBadStatus       = ["CREATE_FAILED", "DELETE_IN_PROGRESS", "DELETE_FAILED", "DELETE_COMPLETE", "DELETE_COMPLETE",
                           "DELETE_SKIPPED", "UPDATE_FAILED"]
ResourceTempStatus      = ["CREATE_IN_PROGRESS", "UPDATE_IN_PROGRESS"]
StackTempStatus         = ["N/A", "CREATE_IN_PROGRESS", "ROLLBACK_IN_PROGRESS", "DELETE_IN_PROGRESS", "UPDATE_IN_PROGRESS",
                           "UPDATE_COMPLETE_CLEANUP_IN_PROGRESS", "UPDATE_ROLLBACK_IN_PROGRESS",
                           "UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS"]
StackDoneStatus         = ["CREATE_FAILED", "CREATE_COMPLETE", "ROLLBACK_FAILED", "ROLLBACK_COMPLETE", "DELETE_FAILED",
                           "DELETE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_FAILED", "UPDATE_ROLLBACK_COMPLETE"]
StackGoodStatus         = ["CREATE_COMPLETE", "UPDATE_COMPLETE"]


class CFStack(object):
    """Class to represent a CloudFormation Template"""

    def __init__(self, stack_name, region, session=None):
        """Constructs a CFTemplate from the template_body (json or yaml)."""
        self.stack_name = stack_name
        self.region = region
        if session is None:
            self.session = boto3.session.Session()
        else:
            self.session = session

        self.cf_client = self.session.client('cloudformation', region_name=region)

        # if self.get() is None:
        #     return(None)

    def create(self, template=None, S3Template=None, params=None, tags=None, OnFailure=None, stack_policy_body=None, TerminationProtection=None, TimeoutInMinutes=None):
        logger.info(f"Creating Stack {self.stack_name} in {self.region}")

        payload = {
            'StackName':        self.stack_name,
            'Capabilities':     ['CAPABILITY_NAMED_IAM', 'CAPABILITY_AUTO_EXPAND'],
        }

        if tags is not None:
            payload['Tags'] = tags

        if params is not None:
            payload['Parameters'] = []
            for key, value in params.items():
                payload['Parameters'].append({'ParameterKey': str(key), 'ParameterValue': str(value)})

        if stack_policy_body is not None:
            payload['StackPolicyBody'] = json.dumps(stack_policy_body)
        if TerminationProtection is not None:
            payload['EnableTerminationProtection'] = TerminationProtection
        if TimeoutInMinutes is not None:
            payload['TimeoutInMinutes'] = TimeoutInMinutes
        if OnFailure is not None:
            payload['OnFailure'] = OnFailure

        # Now make the decision on what to tell CF about the template
        if template is not None:
            self.template = template
            payload['TemplateBody'] = self.template.template_body
        elif S3Template is not None:
            self.S3Template = S3Template
            payload['TemplateURL'] = self.S3Template
        else:
            logger.critical("Neither 'TemplateBody' nor 'TemplateURL' found in manifest")
            return(False)

        try:
            stack_response = self.cf_client.create_stack(**payload)
            if 'StackId' not in stack_response:
                logger.error("Unable to create stack")
                return(None)
            return(stack_response['StackId'])
        except CFStackDoesNotExistError as e:
            logger.error(f"Could not find new stack {self.stack_name} in {self.region}: {e}")
            return(None)
        except ClientError as e:
            logger.error(f"Error attempting to create {self.stack_name} in {self.region}: {e}")
            return(None)

    def get(self):
        """Fetch the latest set of data for this stack from AWS and update properties of the instance."""
        try:
            if hasattr(self, "StackId"):
                response = self.cf_client.describe_stacks(StackName=self.StackId)
            else:
                response = self.cf_client.describe_stacks(StackName=self.stack_name)
            if 'Stacks' not in response or len(response['Stacks']) == 0:
                logger.error(f"Unable to find a stack named {self.stack_name}")
                return(None)
            self.stackData = response['Stacks'][0]
            self.__dict__.update(self.stackData)
            return(self.StackId)
        except ClientError as e:
            if e.response['Error']['Code'] == "ValidationError":
                raise CFStackDoesNotExistError(self.stack_name)
            else:
                raise

    def delete(self):
        """ Deletes this stack."""
        self.cf_client.delete_stack(StackName=self.StackId)

    def update(self, manifest=None, override=None, payload=None):
        """ Updates a Stack based on this manifest."""
        logger.info(f"Updating Stack {self.stack_name} in {self.region}")
        if manifest is None and payload is None:
            logger.error("update has neither manifest nor payload")
            return(None)

        if manifest is not None:
            manifest.fetch_parameters(override=override)
            payload = manifest.build_cft_payload()

        try:
            # These are only valid for Create, but may or may not be in the manifest.
            if 'TimeoutInMinutes' in payload:
                del payload['TimeoutInMinutes']
            if 'OnFailure' in payload:
                del payload['OnFailure']
            if 'EnableTerminationProtection' in payload:
                del payload['EnableTerminationProtection']

            logger.debug(json.dumps(payload, indent=2))
            stack_response = self.cf_client.update_stack(**payload)
            if 'StackId' not in stack_response:
                logger.error("Unable to update stack")
                return(None)
            return(stack_response['StackId'])
        except CFStackDoesNotExistError as e:
            logger.error(f"Could not find stack {self.stack_name} in {self.region}: {e}")
            return(None)
        except ClientError as e:
            if e.response['Error']['Code'] == "ValidationError":
                if "No updates are to be performed." in str(e):
                    logger.info(f"No updates to be performed")
                    return(True)
                else:
                    logger.error(f"Error attempting to update {self.stack_name} in {self.region}: {e}")
                    return(None)
            else:
                logger.error(f"Error attempting to update {self.stack_name} in {self.region}: {e}")
                return(None)

    def get_parameters(self):
        """ Return a dict of each parameter to this stack."""
        self.get()
        output = {}
        for p in self.Parameters:
            if 'ResolvedValue' in p:
                output[p['ParameterKey']] = p['ResolvedValue']
            elif 'ParameterValue' in p:
                output[p['ParameterKey']] = p['ParameterValue']
            else:
                logger.error(f"No values for {p['ParameterKey']} in get_parameters()")
        return(output)

    def get_outputs(self):
        """ Return a dict of each output of this stack."""
        self.get()
        output = {}
        for o in self.Outputs:
            if 'OutputValue' in o:
                output[o['OutputKey']] = o['OutputValue']
            else:
                logger.error(f"No values for {o['OutputKey']} in get_outputs()")
        return(output)

    def get_resources(self):
        """ Return all the PhysicalResourceIds for each LogicalId in the template"""
        response = self.cf_client.list_stack_resources(StackName=self.StackId)
        self.resources = response['StackResourceSummaries']
        while "NextToken" in response:
            response = self.cf_client.list_stack_resources(StackName=self.StackId, NextToken=response[ "NextToken"])
            self.resources.extend( response['StackResourceSummaries'] )

        output = {}
        for o in self.resources:
            if 'PhysicalResourceId' not in o:
                logger.error(f"No values for {o['LogicalResourceId']} in get_resources()")
                continue

            if o['ResourceStatus'] in ResourceGoodStatus:
                output[o['LogicalResourceId']] = o['PhysicalResourceId']
            else:
                logger.error(f"{o['LogicalResourceId']} is in non-good status {o['ResourceStatus']}")
                continue

        return(output)

    def detect_drift(self):
        """ Triggers Drift Detection for this stack."""
        raise NotImplementedError

    def get_status(self):
        '''Fetch the value of StackStatus from AWS CF API for this stack'''
        self.get()
        return(self.stackData['StackStatus'])

    def get_stack_events(self, last_event_id=None):
        """ Return all stack events since last_event_id."""
        events = []
        response = self.cf_client.describe_stack_events(StackName=self.StackId)
        # Enabling the following would return all of the stack events since the begining of time.
        # If we're just doing a tail-f with a short interval, then we don't need to paginate the results.
        # while 'NextToken' in response:
        #     for event in response['StackEvents']:
        #         if last_event_id is not None and event['EventId'] == last_event_id:
        #             # Abort now and return what we've got.
        #             events.reverse()
        #             return(events)
        #         events.append(event)
        #     response = self.cf_client.describe_stack_events(StackName=self.StackId, NextToken=response['NextToken'])
        for event in response['StackEvents']:
            if last_event_id is not None and event['EventId'] == last_event_id:
                # Abort now and return what we've got.
                events.reverse()
                return(events)
            events.append(event)
        events.reverse()
        return(events)

    def create_changeset(self, changeset_name):
        """ Trigger the creation of the changeset."""
        raise NotImplementedError

    def describe_changeset(self, changeset_name):
        """ Get the details of changes from a previously created changeset."""
        raise NotImplementedError

    def list_changesets(self):
        """ List all active changesets for this stack."""
        raise NotImplementedError

    def get_template(self):
        """ Return as a CFTemplate the current template for this stack."""
        response = self.cf_client.get_template(StackName=self.StackId)
        template_body = response['TemplateBody']
        return(CFTemplate(template_body, self.region, session=self.session))

    @classmethod
    def find_by_resource(cls, PhysicalResourceId=None, region=None, session=None):

        if region is None:
            if 'AWS_DEFAULT_REGION' not in os.environ:
                logger.critical("No default region specified in environment")
                exit(1)
            region = os.environ['AWS_DEFAULT_REGION']

        if session is None:
            session = boto3.session.Session()
        cf_client = session.client('cloudformation', region_name=region)

        try:
            if PhysicalResourceId is None:
                logger.error("PhysicalResourceId must be set")
                return(None)
            response = cf_client.describe_stack_resources(PhysicalResourceId=PhysicalResourceId)
        except ClientError as e:
            if e.response['Error']['Code'] == 'ValidationError':
                return(None)
            else:
                raise

        if 'StackResources' not in response and len(response['StackResources']) == 0:
            logger.error(f"Unable to find a stack for PhysicalResourceId={PhysicalResourceId} / LogicalResourceId={LogicalResourceId} in {region}")
            return(None)

        stack_name = response['StackResources'][0]['StackName']
        stack = CFStack(stack_name, region, session=session)
        stack.get()
        return(stack)


class CFStackDoesNotExistError(Exception):
    """Exception to raise when the CF Stack is not found. """
    def __init__(self, stackname):
        self.stackname = stackname

    def __str__(self):
        return(f"{self.stackname} does not exist")
