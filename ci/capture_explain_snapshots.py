#!/usr/bin/env python3
"""Capture EXPLAIN plan snapshots for the heaviest SQL-backed reporting views."""

from __future__ import annotations

import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "ci" / "explain_snapshots"
SNAPSHOT_QUERIES = {
    "federation_report_season_portfolio": (
        "SELECT * FROM federation_report_season_portfolio WHERE season_id = {season_id}"
    ),
    "federation_report_club_performance": (
        "SELECT * FROM federation_report_club_performance WHERE season_id = {season_id}"
    ),
}


def _compose_command(compose_file: str, project_name: str | None) -> list[str]:
    command = ["docker", "compose", "-f", compose_file]
    if project_name:
        command.extend(["-p", project_name])
    return command


def _run_psql(
    compose_file: str,
    project_name: str | None,
    db_service: str,
    db_user: str,
    db_name: str,
    sql: str,
) -> str:
    command = _compose_command(compose_file, project_name) + [
        "exec",
        "-T",
        db_service,
        "psql",
        "-U",
        db_user,
        "-d",
        db_name,
        "-At",
        "-c",
        sql,
    ]
    result = subprocess.run(
        command, cwd=WORKSPACE_ROOT, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or result.stdout.strip()
            or f"psql failed for query: {sql}"
        )
    return result.stdout.strip()


def _get_default_season_id(
    compose_file: str,
    project_name: str | None,
    db_service: str,
    db_user: str,
    db_name: str,
) -> str:
    return _run_psql(
        compose_file,
        project_name,
        db_service,
        db_user,
        db_name,
        "SELECT id FROM federation_season ORDER BY date_start DESC NULLS LAST, id DESC LIMIT 1;",
    )


def _capture_plan(
    compose_file: str,
    project_name: str | None,
    db_service: str,
    db_user: str,
    db_name: str,
    sql: str,
) -> str:
    explain_sql = f"EXPLAIN {sql}"
    return _run_psql(
        compose_file, project_name, db_service, db_user, db_name, explain_sql
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", required=True, help="Database to query for EXPLAIN snapshots."
    )
    parser.add_argument(
        "--compose-file",
        default=str(WORKSPACE_ROOT / "docker-compose.yaml"),
        help="Compose file to use for docker compose exec.",
    )
    parser.add_argument("--project-name", help="Optional docker compose project name.")
    parser.add_argument(
        "--db-service", default="db", help="Compose database service name."
    )
    parser.add_argument("--db-user", default="odoo", help="PostgreSQL user for psql.")
    parser.add_argument(
        "--season-id", help="Optional explicit season id to use in snapshot queries."
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where plan snapshots will be written.",
    )
    args = parser.parse_args()

    season_id = args.season_id or _get_default_season_id(
        args.compose_file,
        args.project_name,
        args.db_service,
        args.db_user,
        args.db,
    )
    if not season_id:
        print(f"Unable to resolve a season id from database '{args.db}'.")
        return 1

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for view_name, template in SNAPSHOT_QUERIES.items():
        sql = template.format(season_id=season_id)
        plan_text = _capture_plan(
            args.compose_file,
            args.project_name,
            args.db_service,
            args.db_user,
            args.db,
            sql,
        )
        snapshot_path = output_dir / f"{view_name}.txt"
        snapshot_path.write_text(
            "\n".join(
                [
                    f"# Captured at: {captured_at}",
                    f"# Database: {args.db}",
                    f"# Season ID: {season_id}",
                    f"# Query: {sql}",
                    "",
                    plan_text,
                    "",
                ]
            ),
            encoding="utf-8",
        )
        print(f"Wrote {snapshot_path.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(error)
        raise SystemExit(1)
