
MANIFEST_SKELETON = '''
# Manifest Auto-generated at {timestamp}
# Template Description: {template_description}

# These control how and where the cloudformation is executed
StackName: {my_stack_name}

Region: {region}
TimeOut: 15m
TerminationProtection: {term_protection}

# Either DisableRollback or OnFailure can be specified, not both.
OnFailure: DO_NOTHING # accepts DO_NOTHING, ROLLBACK, DELETE
# DisableRollback: true

# You must specify LocalTemplate or S3Template but not both.
{template_line}

# Parameters:
# There are two kinds of parameters, regular and sourced.
# Regular parameters are static and defined in the Parameters: section of this yaml file
# Sourced are parameters that cft-deploy will go and fetch from other Stacks that are referenced in the DependentStacks section.


###########
# Parameters to the cloudformation stack that are defined manually.
###########
Parameters:{parameter_yaml}

###########
# These stacks are needed by the SourcedParameters section
###########
DependentStacks:
#    MyOtherStack: stack_name_for_other_stack

###########
# Parameters that come from other deployed stacks.
# Valid Sections are Resources, Outputs Parameters
#
# Hint. Get your list of resources this way:
# aws cloudformation describe-stack-resources --stack-name stack_name_for_other_stack --output text
SourcedParameters:

#  # Description from the CloudFormation Template
#  pVPCID: MyOtherStack.Outputs.VPCID

###########
# Tags that apply to the stack. Will be inherited by some resources.
###########
Tags:
  Name: {my_stack_name}

###########
# Stack Policies protect resources from accidental deletion or replacement
# for the definition of stack policies see:
# see http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/protect-stack-resources.html#stack-policy-reference
###########
StackPolicy:
    # All resources should be modifiable.
  - Resource: "*"
    Effect: Allow
    Principal: "*"
    Action:
      - "Update:Modify"
      - "Update:Delete"
      - "Update:Replace"

# End of Manifest
'''  # End of Manifest skeleton
