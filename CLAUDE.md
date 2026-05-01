# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

cft-deploy is a Python CLI tool and module for managing AWS CloudFormation stacks with manifest files. It simplifies CloudFormation deployments by storing stack parameters, options, and cross-stack dependencies in YAML manifest files that can be version controlled.

## Development Setup

Install for development:
```bash
pip install -e .
```

The package requires Python ≥3.6 and depends on:
- boto3 >= 1.26.0, < 2.0.0
- botocore >= 1.29.0, < 2.0.0
- pyyaml >= 6.0, < 7.0

## Code Architecture

### Core Module Structure

The codebase is organized into four main modules in `cftdeploy/`:

1. **template.py (CFTemplate)**: Represents CloudFormation templates
   - Reads/downloads templates from local files or S3
   - Validates templates with AWS CloudFormation service
   - Generates manifest files from templates
   - Handles templates >51200 bytes (requires S3 upload)

2. **manifest.py (CFManifest)**: Represents manifest files
   - Parses YAML manifest files with security constraints (10MB limit, structure validation)
   - Resolves parameters from dependent stacks (cross-stack lookups)
   - Builds CloudFormation API payloads
   - Supports parameter sourcing from other stacks' Resources, Outputs, or Parameters

3. **stack.py (CFStack)**: Represents deployed CloudFormation stacks
   - Manages stack lifecycle (create, update, delete)
   - Retrieves stack parameters, outputs, and resources
   - Monitors stack events for progress tracking
   - Handles stack status checking

4. **entry_points.py**: CLI command implementations
   - All CLI commands call `do_args()` which handles common flags (--version, --debug, --region, --profile)
   - Commands must check `--version` BEFORE validating required arguments
   - Parameter overrides use format: `key=value` (validated with maxsplit=1 to handle `=` in values)
   - `make_session(args)` creates the boto3 session from `args.profile`; always use this instead of constructing sessions directly
   - `_credentials_error(e)` is the shared handler for expired/missing credential exceptions — catches `NoCredentialsError`, `TokenRetrievalError`, and `ProfileNotFound`

### Key Design Patterns

**Cross-Stack Parameter Resolution**: Manifest files can reference other stacks using `DependentStacks` and `SourcedParameters`:
```yaml
DependentStacks:
  VPCStack: my-vpc-stack-name

SourcedParameters:
  pVPCID: VPCStack.Outputs.VPCID
  pSubnetId: VPCStack.Resources.PrivateSubnet
```

**Event Streaming**: Stack operations (create/update/delete) stream events to console with colored status indicators (yellow=in-progress, red=failed, green=complete).

**Session Support**: All classes accept optional `session` parameter for cross-account role assumption via boto3. In entry_points.py, always create the session via `make_session(args)` and pass it explicitly to every `CFStack`, `CFTemplate`, and `CFManifest` constructor so that `--profile` is honoured consistently.

**Credential Error Handling**: All commands catch `botocore.exceptions.NoCredentialsError` and `botocore.exceptions.TokenRetrievalError` (raised when an SSO token expires during request signing) and route them through `_credentials_error()` for a clean user-facing message. `make_session()` catches `ProfileNotFound` at session-creation time.

## Security Considerations

Recent security improvements (DO NOT REVERT):
- Path normalization with `os.path.abspath()` prevents directory traversal
- S3 object keys are URL-encoded with `urllib.parse.quote()`
- Regex patterns use character classes (e.g., `[^/]+`) to prevent ReDoS
- YAML files limited to 10MB with structure validation
- Input validation on all parameter parsing

## CLI Commands

**Note**: All commands support `--version` flag without requiring other arguments. All commands also accept `--profile <name>` to use a named AWS credential profile instead of the default chain.

Key commands:
- `cft-deploy -m manifest.yaml [--profile name] [key=value...]` - Create or update stack
- `cft-validate -t template.json [--profile name]` - Validate template syntax
- `cft-validate-manifest -m manifest.yaml [--profile name]` - Validate manifest and dependencies
- `cft-generate-manifest -m output.yaml -t template.json [--profile name]` - Generate manifest from template
- `cft-upload -t template.json -b bucket -o key [--profile name]` - Upload template to S3
- `cft-delete --stack-name stack-name [--profile name]` - Delete stack
- `cft-get-output --stack-name stack-name --output-key key [--profile name]` - Get stack output value

## Version Management

Version is stored in `cftdeploy/_version.py` as `__version_info__` tuple.
setup.py reads this directly (no shell execution) to avoid command injection.

## Code Style

pycodestyle configuration (setup.cfg):
- Max line length: 160
- Ignored: E251, E221, E241 (alignment-related)
