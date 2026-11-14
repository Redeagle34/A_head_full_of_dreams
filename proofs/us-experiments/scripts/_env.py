"""Load KEY=VALUE pairs from ./.env into os.environ (never prints values)."""
import os, pathlib
p = pathlib.Path(__file__).resolve().parents[1] / ".env"
if p.exists():
    for line in p.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip().strip("'\""))
