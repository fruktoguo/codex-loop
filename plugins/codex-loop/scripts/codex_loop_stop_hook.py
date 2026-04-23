#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import UTC, datetime
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_DONE_TOKEN = "STOPGATE_DONE"
DEFAULT_REQUIRED_SECTIONS = ["完成了什么", "验证结果", "剩余风险"]
DEFAULT_MAX_ROUNDS = 99
DONE_TOKEN_TAIL_RATIO = 0.6
DONE_TOKEN_TAIL_GRACE_CHARS = 120


def emit(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))


def load_event() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def resolve_repo_root(event: dict[str, Any]) -> Path:
    cwd = event.get("cwd")
    if isinstance(cwd, str) and cwd:
        return Path(cwd)
    return Path.cwd()


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None


def ensure_runtime_dir(repo_root: Path) -> Path:
    runtime_dir = repo_root / ".codex-loop" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir


def ensure_specs_dir(repo_root: Path) -> Path:
    specs_dir = repo_root / ".codex-loop" / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)
    return specs_dir


def ensure_history_dir(repo_root: Path) -> Path:
    history_dir = repo_root / ".codex-loop" / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    return history_dir


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def spec_path_for_session(repo_root: Path, session_id: str) -> Path:
    return ensure_specs_dir(repo_root) / f"{session_id}.json"


def normalize_required_sections(value: Any) -> list[str]:
    if not isinstance(value, list):
        return DEFAULT_REQUIRED_SECTIONS[:]
    result: list[str] = []
    for entry in value:
        if isinstance(entry, str):
            text = entry.strip()
            if text:
                result.append(text)
    return result


def normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for entry in value:
        if isinstance(entry, str):
            text = entry.strip()
            if text:
                result.append(text)
    return result


def normalize_command_checks(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for index, entry in enumerate(value):
        if not isinstance(entry, dict):
            continue
        command = entry.get("command")
        if not isinstance(command, str) or not command.strip():
            continue
        result.append(
            {
                "label": str(entry.get("label") or f"command-{index + 1}").strip(),
                "command": command.strip(),
                "cwd": str(entry.get("cwd") or ".").strip() or ".",
                "expect_exit_code": int(entry.get("expect_exit_code") or 0),
            }
        )
    return result


def contains_required_sections(message: str, sections: list[str]) -> tuple[bool, list[str]]:
    missing: list[str] = []
    lowered = message.lower()
    for section in sections:
        if section.lower() not in lowered:
            missing.append(section)
    return len(missing) == 0, missing


def analyze_done_token(message: str, done_token: str) -> dict[str, Any]:
    ratio_min_start = max(0, int(len(message) * DONE_TOKEN_TAIL_RATIO))
    grace_min_start = max(0, len(message) - DONE_TOKEN_TAIL_GRACE_CHARS)
    min_start = min(ratio_min_start, grace_min_start)
    last_index = message.rfind(done_token)
    return {
        "contains": last_index >= 0,
        "near_tail": last_index >= min_start,
        "last_index": last_index,
        "min_start": min_start,
        "ratio_min_start": ratio_min_start,
        "grace_min_start": grace_min_start,
    }


def run_capture(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        check=False,
        text=True,
        capture_output=True,
    )


def resolve_git_root(repo_root: Path) -> Path:
    result = run_capture(["git", "rev-parse", "--show-toplevel"], cwd=repo_root)
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return repo_root


def get_modified_paths(repo_root: Path) -> list[str]:
    git_root = resolve_git_root(repo_root)
    result = run_capture(["git", "status", "--porcelain", "--untracked-files=all"], cwd=git_root)
    if result.returncode != 0:
        return []

    paths: list[str] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        payload = line[3:] if len(line) > 3 else line
        if " -> " in payload:
            payload = payload.split(" -> ", 1)[1]
        payload = payload.strip()
        if payload:
            paths.append(payload)
    return paths


def check_required_paths_exist(repo_root: Path, required_paths: list[str]) -> list[str]:
    missing: list[str] = []
    for relative_path in required_paths:
        target = (repo_root / relative_path).resolve()
        if not target.exists():
            missing.append(relative_path)
    return missing


def check_required_paths_modified(repo_root: Path, required_paths: list[str]) -> list[str]:
    modified_paths = get_modified_paths(repo_root)
    missing: list[str] = []
    for required_path in required_paths:
        matched = any(
            modified == required_path
            or modified.startswith(required_path.rstrip("/") + "/")
            for modified in modified_paths
        )
        if not matched:
            missing.append(required_path)
    return missing


def run_command_checks(repo_root: Path, command_checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for check in command_checks:
        working_dir = (repo_root / str(check["cwd"])).resolve()
        result = subprocess.run(
            check["command"],
            cwd=str(working_dir),
            shell=True,
            check=False,
            text=True,
            capture_output=True,
        )
        results.append(
            {
                "label": check["label"],
                "command": check["command"],
                "cwd": str(working_dir),
                "expect_exit_code": check["expect_exit_code"],
                "exit_code": result.returncode,
                "passed": result.returncode == int(check["expect_exit_code"]),
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
            }
        )
    return results


def summarize_command_failures(command_results: list[dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    for result in command_results:
        if not result["passed"]:
            failures.append(
                f'{result["label"]} 失败，期望退出码 {result["expect_exit_code"]}，实际 {result["exit_code"]}'
            )
    return failures


def archive_completed_spec(
    repo_root: Path,
    spec_path: Path,
    session_id: str,
    spec: dict[str, Any],
    runtime: dict[str, Any],
) -> Path:
    completed_at = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    archive_path = ensure_history_dir(repo_root) / f"{completed_at}-{session_id}.json"
    archive_payload = {
        "completed_at": completed_at,
        "session_id": session_id,
        "spec_path": str(spec_path.relative_to(repo_root)),
        "spec": spec,
        "runtime": runtime,
    }
    write_json(archive_path, archive_payload)
    spec_path.unlink(missing_ok=True)
    return archive_path


def build_continuation_reason(
    task: str,
    spec_path: Path,
    completed: bool,
    missing_sections: list[str],
    missing_paths_modified: list[str],
    missing_paths_exist: list[str],
    command_failures: list[str],
    rounds_used: int,
    max_rounds: int,
) -> str:
    spec_path_text = str(spec_path)
    parts = [
        "继续当前任务，不要停。",
        f"任务目标：{task}",
        f"当前 Codex Loop 轮次：{rounds_used}/{max_rounds}",
        f"当前循环的控制 JSON 文件路径：{spec_path_text}",
        f"当前循环的控制 JSON 文件名：{spec_path.name}",
        "完成开关字段位于该 JSON 顶层：\"completed\"。",
        f"完成前必须保持 {spec_path_text} 里的这一段为：\"completed\": false",
        f"只有任务真实完成并确认配置的 gate 应该通过后，才编辑 {spec_path_text}，把这一段改成：\"completed\": true",
        "未完成时不要输出最终交付，也不要用元叙述解释停止条件；直接继续执行或报告具体阻塞。",
    ]
    if not completed:
        parts.append("当前 completed=false，因此不能结束。")
    elif missing_paths_modified or missing_paths_exist or command_failures:
        parts.append("当前 completed=true，但仍有 gate 未通过，因此不能结束；修复失败项后再收口。")
    if missing_sections:
        parts.append("当前缺少这些必填小节：" + "、".join(missing_sections))
    if missing_paths_modified:
        parts.append("这些路径还没有形成已修改结果：" + "、".join(missing_paths_modified))
    if missing_paths_exist:
        parts.append("这些路径还不存在：" + "、".join(missing_paths_exist))
    if command_failures:
        parts.append("这些命令检查还没通过：" + "；".join(command_failures))
    parts.append(
        f"完成前继续执行；完成后先修改 {spec_path_text} 中的顶层字段 \"completed\": true，再输出最终交付。"
    )
    return " ".join(parts)


def main() -> int:
    event = load_event()
    repo_root = resolve_repo_root(event)
    session_id = str(event.get("session_id") or "default")
    spec_path = spec_path_for_session(repo_root, session_id)
    spec = load_json(spec_path)
    if not spec or not spec.get("enabled", False):
        emit({})
        return 0
    owner_session_id = str(spec.get("owner_session_id") or session_id).strip() or session_id
    if owner_session_id != session_id:
        emit({})
        return 0

    task = str(spec.get("task") or "完成当前任务").strip()
    completed = bool(spec.get("completed", False))
    done_token = str(spec.get("done_token") or DEFAULT_DONE_TOKEN).strip() or DEFAULT_DONE_TOKEN
    required_sections = normalize_required_sections(spec.get("required_sections"))
    required_paths_modified = normalize_string_list(spec.get("required_paths_modified"))
    required_paths_exist = normalize_string_list(spec.get("required_paths_exist"))
    command_checks = normalize_command_checks(spec.get("commands"))
    max_rounds = int(spec.get("max_rounds") or DEFAULT_MAX_ROUNDS)
    if max_rounds < 1:
        max_rounds = DEFAULT_MAX_ROUNDS

    runtime_path = ensure_runtime_dir(repo_root) / f"{session_id}.json"
    runtime = load_json(runtime_path) or {"rounds_used": 0, "status": "idle"}

    last_assistant_message = event.get("last_assistant_message")
    if not isinstance(last_assistant_message, str) or not last_assistant_message.strip():
        emit({})
        return 0

    done_token_state = analyze_done_token(last_assistant_message, done_token)
    has_done_token = bool(done_token_state["near_tail"])
    has_sections, missing_sections = contains_required_sections(last_assistant_message, required_sections)
    missing_paths_modified: list[str] = []
    missing_paths_exist: list[str] = []
    command_results: list[dict[str, Any]] = []
    command_failures: list[str] = []

    # Only run heavier checks once the session spec has been explicitly marked complete.
    if completed:
        missing_paths_modified = check_required_paths_modified(repo_root, required_paths_modified)
        missing_paths_exist = check_required_paths_exist(repo_root, required_paths_exist)
        command_results = run_command_checks(repo_root, command_checks)
        command_failures = summarize_command_failures(command_results)

    if completed and not missing_paths_modified and not missing_paths_exist and not command_failures:
        runtime.update(
            {
                "status": "done",
                "rounds_used": runtime.get("rounds_used", 0),
                "task": task,
                "completed": completed,
                "done_token": done_token,
                "required_sections": required_sections,
                "required_paths_modified": required_paths_modified,
                "required_paths_exist": required_paths_exist,
                "missing_sections": missing_sections,
                "missing_paths_modified": [],
                "missing_paths_exist": [],
                "has_done_token": has_done_token,
                "done_token_contains": done_token_state["contains"],
                "done_token_last_index": done_token_state["last_index"],
                "done_token_min_start": done_token_state["min_start"],
                "command_results": command_results,
                "command_failures": [],
            }
        )
        archive_path = archive_completed_spec(repo_root, spec_path, session_id, spec, runtime)
        runtime["archived_spec_path"] = str(archive_path.relative_to(repo_root))
        write_json(runtime_path, runtime)
        emit({})
        return 0

    rounds_used = int(runtime.get("rounds_used", 0)) + 1
    runtime.update(
        {
            "status": "continued",
            "rounds_used": rounds_used,
            "task": task,
            "completed": completed,
            "done_token": done_token,
            "required_sections": required_sections,
            "required_paths_modified": required_paths_modified,
            "required_paths_exist": required_paths_exist,
            "missing_sections": missing_sections,
            "missing_paths_modified": missing_paths_modified,
            "missing_paths_exist": missing_paths_exist,
            "has_done_token": has_done_token,
            "done_token_contains": done_token_state["contains"],
            "done_token_last_index": done_token_state["last_index"],
            "done_token_min_start": done_token_state["min_start"],
            "command_results": command_results,
            "command_failures": command_failures,
        }
    )
    write_json(runtime_path, runtime)

    if rounds_used >= max_rounds:
        emit({})
        return 0

    emit(
        {
            "decision": "block",
            "reason": build_continuation_reason(
                task,
                spec_path.relative_to(repo_root),
                completed,
                missing_sections,
                missing_paths_modified,
                missing_paths_exist,
                command_failures,
                rounds_used,
                max_rounds,
            ),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
