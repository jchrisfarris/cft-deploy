
import boto3
from botocore.exceptions import ClientError
import os
import sys
import json
import yaml
import datetime
import re
from urllib.parse import quote

import logging
logger = logging.getLogger('cft-deploy.template')


class CFTemplate(object):
    """Class to represent a CloudFormation Template"""

    def __init__(self, template_body, region, filename=None, s3url=None, session=None):
        """Constructs a CFTemplate from the template_body (json or yaml)."""
        self.template_body = template_body
        self.filename = filename
        self.s3url = s3url

        if session is None:
            self.session = boto3.session.Session()
        else:
            self.session = session

        self.cf_client = self.session.client('cloudformation', region_name=region)
        self.region = region

    def __str__(self):
        if self.s3url is not None:
            return(self.s3url)
        elif self.filename is not None:
            return(self.filename)
        else:
            return("A Template has no name")

    @classmethod
    def read(cls, filename, region, session=None):
        """Read the template from filename and then initialize."""
        try:
            # Normalize path to prevent directory traversal attacks
            normalized_path = os.path.abspath(filename)

            # Basic security check: warn if path contains suspicious patterns
            if '..' in os.path.normpath(filename):
                logger.warning(f"Path contains '..' which may indicate directory traversal: {filename}")

            with open(normalized_path, "r") as f:
                template_body = f.read()
            return(CFTemplate(template_body, region, filename=filename, session=session))
        except FileNotFoundError as e:
            logger.error(f"Failed to open Template file: {e}")
            exit(1)
        except IOError as e:
            logger.error(f"Failed to read Template file {filename}: {e}")
            exit(1)

    @classmethod
    def download(cls, bucket, object_key, region, session=None):
        """Downloads the template from S3 and then initialize."""
        try:
            s3 = boto3.client('s3')  # FIXME will fail for cross-account roles
            response = s3.get_object(
                Bucket=bucket,
                Key=object_key
            )
            template_body = response['Body'].read().decode("utf-8")
            return(CFTemplate(template_body, region, s3url=f"s3://{bucket}/{object_key}", session=session))
        except ClientError as e:
            logger.error("ClientError downloading template: {}".format(e))
            raise

    def validate(self):
        """Validate the template's syntax by sending to CloudFormation Service. Returns json from AWS."""
        try:
            if self.filename is not None:
                response = self.cf_client.validate_template(TemplateBody=self.template_body)
            else:
                (bucket, object_key) = self.parse_s3_url(self.s3url)
                # URL-encode the object_key to prevent URL injection
                encoded_key = quote(object_key, safe='/')
                template_url = f"https://s3.amazonaws.com/{bucket}/{encoded_key}"
                response = self.cf_client.validate_template(TemplateURL=template_url)
            return(response)
        except ClientError as e:
            if e.response['Error']['Code'] == 'ValidationError':
                if "Member must have length less than or equal to 51200" in e.response['Error']['Message']:
                    raise CFTemplateTooLargeError(e)
                else:
                    logger.error(f"Invalid Template: {e}")
                    return(None)
            if e.response['Error']['Code'] == 'ExpiredToken':
                logger.error(f"Credentials Expired: {e}")
                return(None)
            else:
                raise

    def generate_manifest(self, manifest_file_name, substitutions=None, overwrite=False):
        """Generates a stub manifest file for this template and writes it to manifest_file_name.
        If substitutions are specified, these are populated into the stub manifest file.
        """
        from .manifest import CFManifest
        from .skeleton import MANIFEST_SKELETON
        params = self.validate()
        if params is None:
            logger.error("Unable to validate template. Cannot create Manifest.")
            return(None)

        # Build the yaml for the Parmeters section.
        # All Parameters are standard when written to the generated manifest
        parameter_string = ""
        for p in params['Parameters']:
            if 'Description' in p:
                sanitized_desc = str(p['Description']).replace('\n', ' ').replace('\r', ' ')
                parameter_string += f"\n\n  # {sanitized_desc}"
            else:
                parameter_string += f"\n\n  # No Description"
            if 'DefaultValue' in p:
                sanitized_default = str(p['DefaultValue']).replace('\n', ' ').replace('\r', ' ')
                parameter_string += f"\n  {p['ParameterKey']}: {sanitized_default}"
            else:
                parameter_string += f"\n  {p['ParameterKey']}: "

        # Default Value to be subsituted into the skeleton
        manifest_values = {
            'parameter_yaml': parameter_string,
            'my_stack_name': "CHANGEME",
            'term_protection': "false",  # Use yaml formatting which is lowercase
            'template_line': "# WARNING - No Template Source Defined.",
            'timestamp': datetime.datetime.now(),
            'region': "CHANGEME"
        }
        if 'Description' in params:
            manifest_values['template_description'] = str(params['Description']).replace('\n', ' ').replace('\r', ' ')
        else:
            manifest_values['template_description'] = "No Template Description Provided"

        # Set the Template Line value
        if self.filename is not None:
            manifest_values['template_line'] = f"LocalTemplate: {self.filename}"
        elif self.s3url is not None:
            (bucket, object_key) = self.parse_s3_url(self.s3url)
            # URL-encode the object_key to prevent URL injection
            encoded_key = quote(object_key, safe='/')
            template_url = f"https://s3.amazonaws.com/{bucket}/{encoded_key}"
            manifest_values['template_line'] = f"S3Template: {template_url}"

        # If we pass in any other values we want to use, override the defaults here
        if substitutions is not None:
            if 'termination_protection' in substitutions:
                manifest_values['term_protection'] = substitutions['termination_protection']
            if 'stack_name' in substitutions:
                manifest_values['my_stack_name'] = substitutions['stack_name']
            if 'region' in substitutions:
                manifest_values['region'] = substitutions['region']

        # logger.debug(f"Using Manifest Values: {manifest_values}")
        file_body = MANIFEST_SKELETON.format(**manifest_values)

        # Normalize path to prevent directory traversal attacks
        normalized_path = os.path.abspath(manifest_file_name)

        # Basic security check: warn if path contains suspicious patterns
        if '..' in os.path.normpath(manifest_file_name):
            logger.warning(f"Path contains '..' which may indicate directory traversal: {manifest_file_name}")

        if overwrite is not True and os.path.exists(normalized_path):
            logger.critical(f"Refusing to overwrite {normalized_path}. File exists")
            exit(1)

        try:
            # Now do the substitution and write the file
            with open(normalized_path, "w") as f:
                f.write(file_body)
            return(CFManifest(normalized_path, self.session))
        except IOError as e:
            logger.critical(f"Failed to write manifest file {normalized_path}: {e}")
            exit(1)
        except Exception as e:
            logger.critical(f"Failed to create manifest {normalized_path}: {e}")
            exit(1)

    def diff(self, other_template):
        """prints out the differences between this template and another one."""
        raise NotImplementedError

    def upload(self, bucket, object_key):
        """Upload the template to S3."""
        try:
            s3_client = self.session.client('s3')
            response = s3_client.put_object(
                Body=self.template_body,
                Bucket=bucket,
                ContentType='application/json',
                Key=object_key
            )
            self.s3url = f"s3://{bucket}/{object_key}"
            return(self.s3url)
        except ClientError as e:
            logger.error("ClientError saving template: {}".format(e))
            raise

    @classmethod
    def parse_s3_url(cls, s3url):
        '''Parse an s3url (s3://bucket/object_key) and return the bucket and object_key'''
        bucket = None
        object_key = None
        # Use more specific regex pattern to prevent ReDoS
        # Match s3:// followed by bucket name (non-slash chars) then / then object key (rest)
        r = re.match(r"s3://([^/]+)/(.+)$", s3url)
        if r:
            bucket = r.group(1)
            object_key = r.group(2)
        if bucket is None:
            logger.error("unable to extract bucket")
            return(None, None)
        if object_key is None:
            logger.error("unable to extract object_key")
            return(None, None)
        return(bucket, object_key)


class CFTemplateTooLargeError(Exception):
    """
    Exception to raise when the CFT cannot be passed to the AWS Service via API
    Currently this size is 51200 Bytes
    """
