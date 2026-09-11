"""Generate or check the versioned API contract without requiring secrets or a database."""

import json
import sys
from pathlib import Path

from app.config import Settings
from app.main import create_app

path = Path(__file__).resolve().parents[1] / "docs" / "openapi.json"
app = create_app(Settings(api_key="contract-generation-placeholder-32-bytes"))
serialized = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
if "--check" in sys.argv:
    if path.read_text() != serialized:
        raise SystemExit("OpenAPI snapshot is stale; run python scripts/export_openapi.py")
else:
    path.write_text(serialized)
