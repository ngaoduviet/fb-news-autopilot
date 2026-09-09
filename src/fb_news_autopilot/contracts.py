"""Validate every inter-module object against checked-in JSON Schema."""
import json
import sys
from pathlib import Path
from functools import lru_cache
from jsonschema import Draft202012Validator, FormatChecker

@lru_cache
def validator(name: str) -> Draft202012Validator:
    root = Path(__file__).resolve().parents[2] / 'schemas'
    if not root.exists():
        root = Path(sys.prefix) / 'share/fb-news-autopilot/schemas'
    schema = json.loads((root / f'{name}.schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())

def validate(name: str, value: dict) -> dict:
    # Round trip also excludes NaN/Infinity and non-JSON Python values.
    json.dumps(value, allow_nan=False)
    validator(name).validate(value)
    return value
