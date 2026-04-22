#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def find_latest_runtime(runtime_dir: Path) -> Path | None:
    if not runtime_dir.exists():
        return None

    candidates = [path for path in runtime_dir.glob("*.json") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def main() -> int:
    repo_root = Path.cwd()
    spec_path = repo_root / ".codex-loop" / "spec.json"
    runtime_dir = repo_root / ".codex-loop" / "runtime"

    if not spec_path.exists():
        print("当前仓库未配置 codex-loop。")
        print(f"期望路径: {spec_path}")
        return 1

    spec = read_json(spec_path)
    latest_runtime_path = find_latest_runtime(runtime_dir)

    print(f"spec: {spec_path}")
    print(f"enabled: {str(bool(spec.get('enabled', False))).lower()}")
    print(f"task: {spec.get('task', '')}")
    print(f"done_token: {spec.get('done_token', '')}")
    print(f"required_sections: {', '.join(spec.get('required_sections', []))}")
    print(f"required_paths_modified: {', '.join(spec.get('required_paths_modified', [])) or '(none)'}")
    print(f"required_paths_exist: {', '.join(spec.get('required_paths_exist', [])) or '(none)'}")
    print(f"commands: {len(spec.get('commands', []))}")
    print(f"max_rounds: {spec.get('max_rounds', '')}")

    if latest_runtime_path is None:
        print("latest_runtime: (none)")
        return 0

    runtime = read_json(latest_runtime_path)
    print(f"latest_runtime: {latest_runtime_path}")
    print(f"latest_round: {runtime.get('round', '')}")
    print(f"latest_reason: {runtime.get('reason', '')}")
    print(f"last_updated_at: {runtime.get('updated_at', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
