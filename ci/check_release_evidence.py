#!/usr/bin/env python3
"""Validate release evidence without rewriting its summary."""
from __future__ import annotations
import argparse,json,subprocess
from pathlib import Path
from finalize_release_evidence import DEFAULT_REQUIRED_LANES, build_summary
ROOT=Path(__file__).resolve().parents[1]
def git(*args): return subprocess.run(["git",*args],cwd=ROOT,check=True,text=True,capture_output=True).stdout.strip()
def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("--evidence-dir",type=Path,required=True); p.add_argument("--commit"); p.add_argument("--require-passing",action="store_true"); p.add_argument("--required-lane",action="append",default=[]); a=p.parse_args()
    expected=a.commit or git("rev-parse","HEAD"); required=tuple(a.required_lane or DEFAULT_REQUIRED_LANES); summary=build_summary(a.evidence_dir.resolve(),required,expected); errors=[]; stored_path=a.evidence_dir/"summary.json"
    if stored_path.is_file():
        stored=json.loads(stored_path.read_text(encoding="utf-8"))
        for key in ("commit","status","complete","failed_lanes","skipped_lanes","missing_lanes","unexpected_lanes","commit_mismatches","invalid_records"):
            if stored.get(key)!=summary.get(key): errors.append(f"stored summary has stale {key}")
    else: errors.append("summary.json is missing")
    if summary["commit_mismatches"]: errors.append("lane evidence belongs to another commit")
    if not summary["complete"]: errors.append("evidence set is incomplete or invalid")
    if a.require_passing and summary["status"]!="passed": errors.append("release evidence is not passing")
    if errors:
        print("Release evidence validation failed:"); [print(f"- {e}") for e in errors]; print(json.dumps(summary,indent=2,sort_keys=True)); return 1
    print(f"Release evidence validation passed for {expected} ({summary['status']})."); return 0
if __name__ == "__main__": raise SystemExit(main())
