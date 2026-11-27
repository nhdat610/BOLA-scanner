import os
import re

_ENV_PATTERN = re.compile(r"^\\$\\{([A-Za-z_][A-Za-z0-9_]*)\\}$")

def resolve_header_values(headers):
    result = {}
    for name, value in (headers or {}).items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise ValueError("Custom header names and values must be strings.")
        match = _ENV_PATTERN.match(value)
        if match:
            env_name = match.group(1)
            resolved = os.environ.get(env_name)
            if resolved is None:
                raise ValueError(f"Environment variable '{env_name}' is not set.")
            value = resolved
        result[name] = value
    return result
