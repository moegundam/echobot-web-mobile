from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import add_runtime_arguments, runtime_options_from_args
from ..persistence.export import (
    build_postgres_seed_export,
    validate_postgres_seed_export,
    write_postgres_seed_export,
)
from ..persistence.postgres_schema import POSTGRES_SCHEMA_SQL


def configure_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    subparsers = parser.add_subparsers(dest="db_command")

    schema = subparsers.add_parser(
        "schema",
        help="Print the PostgreSQL schema draft.",
    )
    schema.add_argument("--output", default="", help="Optional output .sql path.")
    schema.set_defaults(handler=run_schema)

    export = subparsers.add_parser(
        "export",
        help="Export current file-backed state as a PostgreSQL migration seed JSON.",
    )
    add_runtime_arguments(export)
    export.add_argument(
        "--output",
        default="",
        help="Output JSON path for the migration seed.",
    )
    export.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and validate the seed without writing a file.",
    )
    export.set_defaults(handler=run_export)
    parser.set_defaults(handler=run)
    return parser


def run(args: argparse.Namespace) -> int:
    handler = getattr(args, "handler", None)
    if handler is None or handler is run:
        raise SystemExit("Choose a db subcommand: schema or export")
    return handler(args)


def run_schema(args: argparse.Namespace) -> int:
    output = str(getattr(args, "output", "") or "").strip()
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(POSTGRES_SCHEMA_SQL + "\n", encoding="utf-8")
        print(f"Wrote PostgreSQL schema: {path}")
        return 0
    print(POSTGRES_SCHEMA_SQL)
    return 0


def run_export(args: argparse.Namespace) -> int:
    options = runtime_options_from_args(args)
    workspace = options.workspace or Path.cwd()
    if bool(getattr(args, "dry_run", False)):
        payload = build_postgres_seed_export(workspace)
        errors = validate_postgres_seed_export(payload)
        print(
            json.dumps(
                {
                    "format": payload["format"],
                    "counts": payload["manifest"]["counts"],
                    "sha256": payload["manifest"]["sha256"],
                    "validation_errors": errors,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 1 if errors else 0

    output = str(getattr(args, "output", "") or "").strip()
    if not output:
        raise SystemExit("db export requires --output unless --dry-run is used")
    write_postgres_seed_export(workspace, output)
    print(f"Wrote PostgreSQL migration seed: {output}")
    return 0
