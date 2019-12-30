from setuptools import setup, find_packages
import os, sys

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
  name='cftdeploy',
  version=os.popen('{} cftdeploy/_version.py'.format(sys.executable)).read().rstrip(),
  author='Chris Farris',
  author_email='chris@room17.com',
  license="Apache License 2.0",
  license_file="LICENSE",
  description='Tools and modules for managing CloudFormation Templates & Stacks',
  long_description=long_description,
  long_description_content_type="text/markdown",
  packages=find_packages(),
  py_modules=['cftdeploy'],
  url='http://github.com/jchrisfarris/cft-deploy',
  python_requires='>=3.6',
  include_package_data=True,
  install_requires=[
    'boto3 >= 1.10.0',
    'botocore >= 1.13.0'
  ],
  entry_points={
    'console_scripts': [
      "cft-deploy = cftdeploy:cft_deploy",
      "cft-get-resource = cftdeploy:cft_get_resource",
      "cft-validate = cftdeploy:cft_validate",
      "cft-validate-manifest = cftdeploy:cft_validate_manifest",
      "cft-upload  = cftdeploy:cft_upload",
      "cft-delete  = cftdeploy:cft_delete",
      "cft-generate-manifest = cftdeploy:cft_generate_manifest",
      "cft-get-events = cftdeploy:cft_get_events",
      "cft-diff = cftdeploy:cft_diff",
      "cft-get-output = cftdeploy:cft_get_output",
    ]
  }
)
