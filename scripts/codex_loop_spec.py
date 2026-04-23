#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import hashlib
import re
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
SAFE_SESSION_ID_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")
IGNORED_SNAPSHOT_TOP_LEVEL = {".git", ".codex-loop"}


def load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_session_id(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    text = SAFE_SESSION_ID_PATTERN.sub("_", value.strip())
    text = text.strip("._-")
    return text or None


def resolve_session_id(explicit: str | None = None) -> str | None:
    return normalize_session_id(explicit) or normalize_session_id(os.environ.get("CODEX_THREAD_ID"))


def ensure_specs_dir(repo_root: Path) -> Path:
    specs_dir = repo_root / SPECS_RELATIVE_PATH
    specs_dir.mkdir(parents=True, exist_ok=True)
    return specs_dir


def spec_path_for_session(repo_root: Path, session_id: str) -> Path:
    return ensure_specs_dir(repo_root) / f"{session_id}.json"


def resolve_repo_relative_path(repo_root: Path, relative_path: str) -> Path | None:
    target = (repo_root / relative_path).resolve()
    try:
        target.relative_to(repo_root.resolve())
    except ValueError:
        return None
    return target


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_repo_path(repo_root: Path, relative_path: str) -> dict[str, Any]:
    target = resolve_repo_relative_path(repo_root, relative_path)
    if target is None:
        return {"valid": False, "exists": False, "kind": "invalid", "digest": None}
    if not target.exists():
        return {"valid": True, "exists": False, "kind": "missing", "digest": None}
    if target.is_symlink():
        return {
            "valid": True,
            "exists": True,
            "kind": "symlink",
            "digest": hashlib.sha256(os.readlink(target).encode("utf-8", "surrogateescape")).hexdigest(),
        }
    if target.is_file():
        return {"valid": True, "exists": True, "kind": "file", "digest": _hash_file(target)}
    if target.is_dir():
        digest = hashlib.sha256()
        for child in sorted(path for path in target.rglob("*") if path.is_file() or path.is_symlink()):
            if any(part in IGNORED_SNAPSHOT_TOP_LEVEL for part in child.relative_to(repo_root.resolve()).parts):
                continue
            relative_child = child.relative_to(target).as_posix()
            digest.update(relative_child.encode("utf-8", "surrogateescape"))
            digest.update(b"\0")
            if child.is_symlink():
                digest.update(b"symlink\0")
                digest.update(os.readlink(child).encode("utf-8", "surrogateescape"))
            else:
                digest.update(b"file\0")
                digest.update(_hash_file(child).encode("ascii"))
            digest.update(b"\0")
        return {"valid": True, "exists": True, "kind": "dir", "digest": digest.hexdigest()}
    return {"valid": True, "exists": True, "kind": "other", "digest": None}


def build_required_paths_modified_baseline(repo_root: Path, required_paths: list[str]) -> dict[str, Any]:
    return {relative_path: snapshot_repo_path(repo_root, relative_path) for relative_path in required_paths}


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
    required_paths_exist = _validate_string_list(spec.get("required_paths_exist"), "required_paths_exist", errors)

    for key, paths in (
        ("required_paths_modified", required_paths_modified),
        ("required_paths_exist", required_paths_exist),
    ):
        for relative_path in paths:
            if resolve_repo_relative_path(repo_root, relative_path) is None:
                errors.append(f"{key} 不能指向仓库外路径: {relative_path}")

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
            elif resolve_repo_relative_path(repo_root, str(entry.get("cwd"))) is None:
                errors.append(f"commands[{index}].cwd 不能指向仓库外路径。")
            if not isinstance(entry.get("expect_exit_code"), int) or isinstance(entry.get("expect_exit_code"), bool):
                errors.append(f"commands[{index}].expect_exit_code 必须是整数。")

    baseline = spec.get("required_paths_modified_baseline")
    if baseline is not None and not isinstance(baseline, dict):
        errors.append("required_paths_modified_baseline 必须是 object。")

    max_rounds = spec.get("max_rounds")
    if not isinstance(max_rounds, int) or isinstance(max_rounds, bool) or max_rounds < 1:
        errors.append("max_rounds 必须是大于等于 1 的整数。")

    if not is_git_repo(repo_root) and required_paths_modified:
        errors.append("当前目录不是 git 仓库，required_paths_modified 必须为空。")

    if not required_sections and not commands and not required_paths_modified and not spec.get("required_paths_exist"):
        if not _is_non_empty_string(spec.get("done_token")):
            errors.append("当没有其他 gate 时，done_token 仍必须存在。")

    return errors
