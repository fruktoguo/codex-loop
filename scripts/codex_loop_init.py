#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from codex_loop_spec import resolve_session_id, spec_path_for_session, validate_spec_payload


DEFAULT_DONE_TOKEN = "STOPGATE_DONE"
DEFAULT_SECTIONS = ["完成了什么", "验证结果", "剩余风险"]


def load_existing_spec(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or refresh the current session-bound codex-loop spec for the repository."
    )
    parser.add_argument("task", nargs="?", help="Task description written into the spec")
    parser.add_argument(
        "--session-id",
        default=None,
        help="Bind the spec to this session id; defaults to CODEX_THREAD_ID",
    )
    parser.add_argument("--done-token", default=None, help="Done token required in the final answer")
    parser.add_argument(
        "--section",
        action="append",
        default=None,
        help="Required final-answer section title; repeatable",
    )
    parser.add_argument(
        "--no-sections",
        action="store_true",
        help="Write required_sections as an empty array",
    )
    parser.add_argument(
        "--path-modified",
        action="append",
        default=None,
        help="Path that must end up modified; repeatable",
    )
    parser.add_argument(
        "--no-path-modified",
        action="store_true",
        help="Write required_paths_modified as an empty array",
    )
    parser.add_argument(
        "--path-exists",
        action="append",
        default=None,
        help="Path that must exist at completion; repeatable",
    )
    parser.add_argument(
        "--no-path-exists",
        action="store_true",
        help="Write required_paths_exist as an empty array",
    )
    parser.add_argument(
        "--command",
        action="append",
        default=None,
        help="Shell command gate to run near the final turn; repeatable",
    )
    parser.add_argument(
        "--no-commands",
        action="store_true",
        help="Write commands as an empty array",
    )
    parser.add_argument(
        "--command-cwd",
        default=".",
        help="cwd used for every --command entry, defaults to current repository root",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=None,
        help="Maximum continuation rounds before the hook gives up",
    )
    parser.add_argument(
        "--disable",
        action="store_true",
        help="Write enabled=false instead of enabled=true",
    )
    return parser.parse_args()


def build_commands(raw_commands: list[str] | None, command_cwd: str) -> list[dict]:
    if not raw_commands:
        return []

    commands: list[dict] = []
    for index, command in enumerate(raw_commands, start=1):
        commands.append(
            {
                "label": f"check-{index}",
                "command": command,
                "cwd": command_cwd,
                "expect_exit_code": 0,
            }
        )
    return commands


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()
    session_id = resolve_session_id(args.session_id)
    if session_id is None:
        print("缺少 session id。请在 Codex 会话内运行，或显式传入 --session-id。")
        return 1

    spec_path = spec_path_for_session(repo_root, session_id)
    spec_path.parent.mkdir(parents=True, exist_ok=True)

    existing = load_existing_spec(spec_path)
    task = args.task or existing.get("task") or "Describe the task here."
    if args.no_sections:
        sections = []
    else:
        sections = args.section if args.section is not None else existing.get("required_sections") or DEFAULT_SECTIONS
    if args.no_path_modified:
        modified = []
    else:
        modified = args.path_modified if args.path_modified is not None else existing.get("required_paths_modified") or []
    if args.no_path_exists:
        required_exist = []
    else:
        required_exist = args.path_exists if args.path_exists is not None else existing.get("required_paths_exist") or []
    if args.no_commands:
        commands = []
    else:
        commands = (
            build_commands(args.command, args.command_cwd)
            if args.command is not None
            else existing.get("commands") or []
        )
    spec = {
        "enabled": not args.disable,
        "completed": False,
        "owner_session_id": session_id,
        "task": task,
        "done_token": args.done_token or existing.get("done_token") or DEFAULT_DONE_TOKEN,
        "required_sections": sections,
        "required_paths_modified": modified,
        "required_paths_exist": required_exist,
        "commands": commands,
        "max_rounds": args.max_rounds if args.max_rounds is not None else existing.get("max_rounds") or 99,
    }

    errors = validate_spec_payload(spec, repo_root)
    if errors:
        print("spec 生成失败：")
        for error in errors:
            print(f"- {error}")
        return 1

    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"已写入: {spec_path}")
    print(f"session_id: {session_id}")
    print(f"enabled: {str(spec['enabled']).lower()}")
    print(f"completed: {str(spec['completed']).lower()}")
    print(f"task: {spec['task']}")
    print(f"done_token: {spec['done_token']}")
    print(f"required_sections: {', '.join(spec['required_sections'])}")
    print(f"required_paths_modified: {len(spec['required_paths_modified'])}")
    print(f"required_paths_exist: {len(spec['required_paths_exist'])}")
    print(f"commands: {len(spec['commands'])}")
    print(f"max_rounds: {spec['max_rounds']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
