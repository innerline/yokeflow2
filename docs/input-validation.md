# Input Validation Framework

**Status**: Implemented (January 8, 2026)
**Location**: `server/api/validation.py`
**Tests**: `tests/test_validation.py` (52 tests, 100% passing)

## Overview

Comprehensive input validation framework using Pydantic models for all API inputs, configuration files, and specification files. Provides type safety, clear error messages, and sensible defaults.

## Features

### 1. API Request Validation

**Models**:
- `ProjectCreateRequest` - Project creation with name format validation
- `SessionStartRequest` - Session start with model name validation and iteration limits
- `ProjectRenameRequest` - Project renaming with name format validation
- `EnvConfigRequest` - Environment variable configuration with name format validation
- `LoginRequest` - User login credentials
- `TokenResponse` - Authentication token response

**Validation Rules**:
- Project names: Alphanumeric, hyphens, underscores, dots only (max 100 chars)
- Claude model names: Must match `claude-(opus|sonnet|haiku)-X-X-YYYYMMDD` format
- Max iterations: 1-1000 (positive integers)
- Environment variables: Uppercase with underscores only

### 2. Configuration Validation

**Models**:
- `ModelConfigValidator` - Claude model configuration
- `TimingConfigValidator` - Timing and delay settings
- `SecurityConfigValidator` - Security and blocked commands
- `DatabaseConfigValidator` - Database connection settings
- `ProjectConfigValidator` - Project settings
- `SandboxConfigValidator` - Docker/E2B sandbox settings
- `InterventionConfigValidator` - Intervention system settings
- `VerificationConfigValidator` - Verification and testing settings
- `ConfigValidator` - Complete configuration validation

**Validation Rules**:
- Auto-continue delay: 1-300 seconds
- Web UI port: 1024-65535
- Database URL: Must start with `postgresql://` or `postgres://`
- Memory limits: Format like "2g", "512m", "1024k"
- CPU limits: 0-32 cores
- Port mappings: Format like "3000:3000"
- Test coverage: 0.0-1.0 (0-100%)
- Error rate threshold: 0.0-1.0 (0-100%)

### 3. Specification File Validation

**Model**: `SpecFileValidator`

**Validation Rules**:
- Minimum 100 characters
- At least 3 non-empty lines
- Must contain description keywords (description, overview, purpose, goal, or summary)

### 4. Helper Functions

- `validate_config_dict(config_dict)` - Validate configuration dictionary
- `validate_spec_file_content(content)` - Validate specification file content
- `validate_project_name(name)` - Validate project name format

## Usage Examples

### API Request Validation

```python
from server.api.validation import ProjectCreateRequest

# Validates automatically
request = ProjectCreateRequest(
    name="my-project",
    spec_content="Valid specification content..."
)
```

### Configuration Validation

```python
from server.api.validation import validate_config_dict

config_dict = {
    "models": {
        "initializer": "claude-opus-4-5-20251101"
    },
    "timing": {
        "auto_continue_delay": 5
    }
}

# Validates and returns ConfigValidator instance
config = validate_config_dict(config_dict)
```

### Spec File Validation

```python
from server.api.validation import validate_spec_file_content

content = """
Project Description
===================

This is a comprehensive specification...
"""

# Validates and returns SpecFileValidator instance
spec = validate_spec_file_content(content)
```

## Integration with FastAPI

The validation models are designed to work seamlessly with FastAPI's automatic validation:

```python
from fastapi import FastAPI
from server.api.validation import SessionStartRequest

app = FastAPI()

@app.post("/sessions/start")
async def start_session(request: SessionStartRequest):
    # Request is automatically validated by FastAPI
    # Invalid requests return 422 Unprocessable Entity
    return {"status": "started"}
```

## Error Handling

All validation errors use Pydantic's ValidationError with clear, detailed messages:

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "name"],
      "msg": "Project name must contain only alphanumeric characters, hyphens, underscores, and dots. Got: invalid name!",
      "input": "invalid name!",
      "ctx": {
        "error": "..."
      }
    }
  ]
}
```

## Testing

Comprehensive test suite with 52 tests covering:

- Valid and invalid inputs for all models
- Boundary conditions (min/max values)
- Edge cases (empty strings, special characters)
- Integration scenarios

Run tests:
```bash
pytest tests/test_validation.py -v
```

## Benefits

1. **Type Safety**: Catch validation errors at runtime before they reach business logic
2. **Clear Error Messages**: Users get specific feedback about what's wrong
3. **Sensible Defaults**: Configuration works out-of-the-box with reasonable defaults
4. **Documentation**: Pydantic models serve as API documentation
5. **FastAPI Integration**: Automatic validation and OpenAPI schema generation
6. **Maintainability**: Centralized validation logic in one module
7. **Security**: Prevents injection attacks and malformed inputs

## Future Enhancements

1. **API Integration**: Replace existing ad-hoc validation in `server/api/app.py`
2. **Config File Loading**: Integrate with `server/utils/config.py` for validated config loading
3. **CLI Validation**: Use validators in command-line argument parsing
4. **OpenAPI Schema**: Auto-generate API documentation from validation models
5. **Custom Validators**: Add domain-specific validators as needed

## See Also

- [API Documentation](api-guide.md) - API endpoint reference
- [Configuration Guide](configuration.md) - Configuration options
- [Testing Guide](testing-guide.md) - Testing documentation
