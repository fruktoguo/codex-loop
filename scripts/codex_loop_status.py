#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from codex_loop_spec import list_active_spec_paths, resolve_session_id, spec_path_for_session


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def find_latest_runtime(runtime_dir: Path) -> Path | None:
    if not runtime_dir.exists():
        return None

    candidates = [path for path in runtime_dir.glob("*.json") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def find_latest_history(history_dir: Path) -> Path | None:
    if not history_dir.exists():
        return None

    candidates = [path for path in history_dir.glob("*.json") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def main() -> int:
    repo_root = Path.cwd()
    session_id = resolve_session_id()
    spec_path = spec_path_for_session(repo_root, session_id) if session_id else None
    runtime_dir = repo_root / ".codex-loop" / "runtime"
    history_dir = repo_root / ".codex-loop" / "history"
    current_runtime_path = (runtime_dir / f"{session_id}.json") if session_id else None
    latest_runtime_path = find_latest_runtime(runtime_dir)
    latest_history_path = find_latest_history(history_dir)
    active_spec_paths = list_active_spec_paths(repo_root)

    print(f"current_session_id: {session_id or '(unknown)'}")
    print(f"active_specs: {len(active_spec_paths)}")
    for active_path in active_spec_paths[:10]:
        print(f"- {active_path.name}")
    if len(active_spec_paths) > 10:
        print(f"... and {len(active_spec_paths) - 10} more")

    if spec_path is not None and spec_path.exists():
        spec = read_json(spec_path)
        print(f"spec: {spec_path}")
        print(f"enabled: {str(bool(spec.get('enabled', False))).lower()}")
        print(f"task: {spec.get('task', '')}")
        print(f"done_token: {spec.get('done_token', '')}")
        print(f"required_sections: {', '.join(spec.get('required_sections', []))}")
        print(f"required_paths_modified: {', '.join(spec.get('required_paths_modified', [])) or '(none)'}")
        print(f"required_paths_exist: {', '.join(spec.get('required_paths_exist', [])) or '(none)'}")
        print(f"commands: {len(spec.get('commands', []))}")
        print(f"max_rounds: {spec.get('max_rounds', '')}")
    else:
        print("current_spec: (none)")
        print("当前 session 没有绑定的活动 codex-loop spec。")

    if current_runtime_path is not None and current_runtime_path.exists():
        runtime = read_json(current_runtime_path)
        print(f"current_runtime: {current_runtime_path}")
        print(f"current_runtime_status: {runtime.get('status', '')}")
        print(f"current_runtime_rounds_used: {runtime.get('rounds_used', '')}")
        print(f"current_runtime_archived_spec_path: {runtime.get('archived_spec_path', '')}")
    else:
        print("current_runtime: (none)")

    if latest_runtime_path is None:
        print("latest_runtime: (none)")
    else:
        runtime = read_json(latest_runtime_path)
        print(f"latest_runtime: {latest_runtime_path}")
        print(f"latest_status: {runtime.get('status', '')}")
        print(f"latest_rounds_used: {runtime.get('rounds_used', '')}")
        print(f"archived_spec_path: {runtime.get('archived_spec_path', '')}")

    if latest_history_path is None:
        print("latest_history: (none)")
        return 0

    history = read_json(latest_history_path)
    print(f"latest_history: {latest_history_path}")
    print(f"history_completed_at: {history.get('completed_at', '')}")
    print(f"history_session_id: {history.get('session_id', '')}")
    archived_spec = history.get("spec") or {}
    if isinstance(archived_spec, dict):
        print(f"history_task: {archived_spec.get('task', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
