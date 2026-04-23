#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


REQUIRED_TOP_LEVEL_KEYS = [
    "enabled",
    "completed",
    "task",
    "done_token",
    "required_sections",
    "required_paths_modified",
    "required_paths_exist",
    "commands",
    "max_rounds",
]
SPECS_RELATIVE_PATH = Path(".codex-loop/specs")


def load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_session_id(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def resolve_session_id(explicit: str | None = None) -> str | None:
    return normalize_session_id(explicit) or normalize_session_id(os.environ.get("CODEX_THREAD_ID"))


def ensure_specs_dir(repo_root: Path) -> Path:
    specs_dir = repo_root / SPECS_RELATIVE_PATH
    specs_dir.mkdir(parents=True, exist_ok=True)
    return specs_dir


def spec_path_for_session(repo_root: Path, session_id: str) -> Path:
    return ensure_specs_dir(repo_root) / f"{session_id}.json"


def list_active_spec_paths(repo_root: Path) -> list[Path]:
    specs_dir = repo_root / SPECS_RELATIVE_PATH
    if not specs_dir.exists():
        return []
    return sorted(path for path in specs_dir.glob("*.json") if path.is_file())


def is_git_repo(path: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(path),
        check=False,
        text=True,
        capture_output=True,
    )
    return result.returncode == 0


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_string_list(value: Any, key: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{key} 必须是字符串数组。")
        return []
    result: list[str] = []
    for index, entry in enumerate(value):
        if not _is_non_empty_string(entry):
            errors.append(f"{key}[{index}] 必须是非空字符串。")
            continue
        result.append(entry.strip())
    return result


def validate_spec_payload(spec: Any, repo_root: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(spec, dict):
        return ["spec 顶层必须是 JSON object。"]

    for key in REQUIRED_TOP_LEVEL_KEYS:
        if key not in spec:
            errors.append(f"缺少顶层字段: {key}")

    if "enabled" in spec and not isinstance(spec.get("enabled"), bool):
        errors.append("enabled 必须是布尔值。")
    if "completed" in spec and not isinstance(spec.get("completed"), bool):
        errors.append("completed 必须是布尔值。")
    if "task" in spec and not _is_non_empty_string(spec.get("task")):
        errors.append("task 必须是非空字符串。")
    if "done_token" in spec and not _is_non_empty_string(spec.get("done_token")):
        errors.append("done_token 必须是非空字符串。")
    if isinstance(spec.get("done_token"), str) and any(ch.isspace() for ch in spec["done_token"].strip()):
        errors.append("done_token 不能包含空白字符。")
    if "owner_session_id" in spec and not _is_non_empty_string(spec.get("owner_session_id")):
        errors.append("owner_session_id 必须是非空字符串。")

    required_sections = _validate_string_list(spec.get("required_sections"), "required_sections", errors)
    required_paths_modified = _validate_string_list(
        spec.get("required_paths_modified"), "required_paths_modified", errors
    )
    _validate_string_list(spec.get("required_paths_exist"), "required_paths_exist", errors)

    commands = spec.get("commands")
    if not isinstance(commands, list):
        errors.append("commands 必须是数组。")
    else:
        for index, entry in enumerate(commands):
            if not isinstance(entry, dict):
                errors.append(f"commands[{index}] 必须是 object。")
                continue
            if not _is_non_empty_string(entry.get("label")):
                errors.append(f"commands[{index}].label 必须是非空字符串。")
            if not _is_non_empty_string(entry.get("command")):
                errors.append(f"commands[{index}].command 必须是非空字符串。")
            if not _is_non_empty_string(entry.get("cwd")):
                errors.append(f"commands[{index}].cwd 必须是非空字符串。")
            if not isinstance(entry.get("expect_exit_code"), int):
                errors.append(f"commands[{index}].expect_exit_code 必须是整数。")

    max_rounds = spec.get("max_rounds")
    if not isinstance(max_rounds, int) or isinstance(max_rounds, bool) or max_rounds < 1:
        errors.append("max_rounds 必须是大于等于 1 的整数。")

    if not is_git_repo(repo_root) and required_paths_modified:
        errors.append("当前目录不是 git 仓库，required_paths_modified 必须为空。")

    if not required_sections and not commands and not required_paths_modified and not spec.get("required_paths_exist"):
        if not _is_non_empty_string(spec.get("done_token")):
            errors.append("当没有其他 gate 时，done_token 仍必须存在。")

    return errors
