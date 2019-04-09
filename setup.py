from setuptools import setup, find_packages
import os, sys

setup(
  name='cftdeploy',
  version=os.popen('{} cftdeploy/_version.py'.format(sys.executable)).read().rstrip(),
  author='Chris Farris',
  author_email='chris@room17.com',
  license="Apache License 2.0",
  description='The AWS SDK for Python',
  packages=find_packages(),
  py_modules=['cftdeploy'],
  url='http://github.com/jchrisfarris/cft-deploy',
  # install_requires=[
  #   'boto3',
  # ],
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
    ]
  }
)
