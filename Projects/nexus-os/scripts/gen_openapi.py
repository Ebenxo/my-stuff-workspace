#!/usr/bin/env python3
"""Regenerate packages/schemas (openapi.json + src/api.d.ts) from the FastAPI app.

    python scripts/gen_openapi.py           # write
    python scripts/gen_openapi.py --check   # fail if the committed files are stale (CI)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "services" / "api"
SCHEMAS = ROOT / "packages" / "schemas"


def dump_openapi() -> str:
    """Build the OpenAPI document in a child process against a throwaway NEXUS_HOME."""
    code = (
        "import json; from app.main import create_app; "
        "print(json.dumps(create_app().openapi(), indent=2, sort_keys=True))"
    )
    with tempfile.TemporaryDirectory() as home:
        env = {**os.environ, "NEXUS_HOME": home}
        out = subprocess.run(  # noqa: S603
            ["uv", "run", "--project", str(API_DIR), "python", "-c", code],  # noqa: S607
            check=True,
            capture_output=True,
            text=True,
            env=env,
            cwd=API_DIR,
        )
    # create_app logs to stderr; the document is the last stdout line block.
    return out.stdout.strip() + "\n"


def generate_types(openapi_path: Path, out_path: Path) -> None:
    pnpm = shutil.which("pnpm") or "pnpm"
    subprocess.run(  # noqa: S603
        [pnpm, "exec", "openapi-typescript", str(openapi_path), "-o", str(out_path), "--default-non-nullable", "false"],
        check=True,
        cwd=ROOT,
        capture_output=True,
    )


def main() -> int:
    check = "--check" in sys.argv
    document = dump_openapi()
    json.loads(document)  # validate
    target_json = SCHEMAS / "openapi.json"
    target_ts = SCHEMAS / "src" / "api.d.ts"
    if check:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_json, tmp_ts = Path(tmp) / "openapi.json", Path(tmp) / "api.d.ts"
            tmp_json.write_text(document, encoding="utf-8")
            generate_types(tmp_json, tmp_ts)
            stale = (
                not target_json.exists()
                or target_json.read_text(encoding="utf-8") != document
                or not target_ts.exists()
                or target_ts.read_text(encoding="utf-8") != tmp_ts.read_text(encoding="utf-8")
            )
        if stale:
            print("API types are stale. Run: python scripts/gen_openapi.py", file=sys.stderr)
            return 1
        print("API types are up to date.")
        return 0
    target_json.write_text(document, encoding="utf-8")
    generate_types(target_json, target_ts)
    print(f"wrote {target_json.relative_to(ROOT)} and {target_ts.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
