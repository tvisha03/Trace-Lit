"""Patch ChromaDB config.py for Python 3.14 compatibility.

The issue: pydantic v1's @validator decorator references 'chroma_server_nofile'
before the field is defined. Python 3.14 changed annotation handling (PEP 649),
causing pydantic v1 to fail type inference for forward-referenced fields.

Fix: Move the field definition before the @validator decorator.
"""
import pathlib
import sys

config_path = pathlib.Path(sys.prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages" / "chromadb" / "config.py"

if not config_path.exists():
    print(f"ERROR: ChromaDB config not found at {config_path}")
    sys.exit(1)

content = config_path.read_text()

# Check if already patched
if "chroma_server_nofile: Optional[int] = None\n\n    @validator" in content:
    print("Already patched!")
    sys.exit(0)

# The problematic pattern: validator before field definition
old_pattern = '    @validator("chroma_server_nofile", pre=True, always=True, allow_reuse=True)\n    def empty_str_to_none(cls, v: str) -> Optional[str]:\n        if type(v) is str and v.strip() == "":\n            return None\n        return v\n\n    chroma_server_nofile: Optional[int] = None'

new_pattern = '    chroma_server_nofile: Optional[int] = None\n\n    @validator("chroma_server_nofile", pre=True, always=True, allow_reuse=True)\n    def empty_str_to_none(cls, v: str) -> Optional[str]:\n        if type(v) is str and v.strip() == "":\n            return None\n        return v'

if old_pattern in content:
    content = content.replace(old_pattern, new_pattern)
    config_path.write_text(content)
    print(f"PATCHED: {config_path}")
    print("Moved chroma_server_nofile field before its @validator decorator")
else:
    print("WARNING: Expected pattern not found. ChromaDB version may differ.")
    print(f"File: {config_path}")
    # Show context around the problematic area
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'chroma_server_nofile' in line:
            print(f"  Line {i+1}: {line}")
    sys.exit(1)
