#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from codex_loop_spec import (
    load_json_file,
    list_active_spec_paths,
    resolve_session_id,
    spec_path_for_session,
    validate_spec_payload,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate codex-loop spec files for the current repository.")
    parser.add_argument(
        "--path",
        default=None,
        help="Path to the spec file; defaults to the current session's bound spec",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Session id whose bound spec should be validated; defaults to CODEX_THREAD_ID",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Validate all active specs under .codex-loop/specs/",
    )
    return parser.parse_args()


def validate_one(repo_root: Path, spec_path: Path) -> int:
    if not spec_path.exists():
        print(f"未找到 spec 文件: {spec_path}")
        return 1

    try:
        spec = load_json_file(spec_path)
    except Exception as exc:
        print(f"spec 解析失败: {exc}")
        return 1

    errors = validate_spec_payload(spec, repo_root)
    if errors:
        print(f"spec 校验失败: {spec_path}")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"spec 校验通过: {spec_path}")
    return 0


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()

    if args.all:
        spec_paths = list_active_spec_paths(repo_root)
        if not spec_paths:
            print(f"未找到活动 spec: {repo_root / '.codex-loop' / 'specs'}")
            return 1
        exit_code = 0
        for spec_path in spec_paths:
            if validate_one(repo_root, spec_path) != 0:
                exit_code = 1
        return exit_code

    if args.path is not None:
        spec_path = (repo_root / args.path).resolve()
    else:
        session_id = resolve_session_id(args.session_id)
        if session_id is None:
            print("缺少 session id。请在 Codex 会话内运行，或显式传入 --session-id / --path。")
            return 1
        spec_path = spec_path_for_session(repo_root, session_id)

    return validate_one(repo_root, spec_path)


if __name__ == "__main__":
    raise SystemExit(main())
