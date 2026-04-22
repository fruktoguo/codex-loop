#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


MARKETPLACE_RELATIVE_PATH = Path(".agents/plugins/marketplace.json")
CONFIG_RELATIVE_PATH = Path(".codex/config.toml")
HOOKS_RELATIVE_PATH = Path(".codex/hooks.json")
HELPER_BIN_RELATIVE_PATH = Path(".local/bin")
HELPER_SHARE_RELATIVE_PATH = Path(".local/share/codex-loop")
HELPER_SCRIPTS = {
    "codex-loop-init": "codex_loop_init.py",
    "codex-loop-status": "codex_loop_status.py",
    "codex-loop-validate": "codex_loop_validate.py",
}
PLUGIN_SHARED_SCRIPTS = ["codex_loop_stop_hook.py"]
ROOT_SHARED_SCRIPTS = ["codex_loop_spec.py"]


def run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=False,
        text=True,
        capture_output=True,
    )


def ensure_codex() -> None:
    if shutil.which("codex") is None:
        raise SystemExit("codex CLI 未安装，无法继续。")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def upsert_top_level_key(text: str, key: str, value_literal: str) -> str:
    lines = text.splitlines()
    key_prefix = f"{key} ="

    # Only consider keys before the first table header as top-level keys.
    first_table_index = len(lines)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            first_table_index = index
            break

    for index in range(first_table_index):
        if lines[index].strip().startswith(key_prefix):
            lines[index] = f"{key} = {value_literal}"
            return "\n".join(lines) + "\n"

    insert_at = first_table_index
    while insert_at > 0 and lines[insert_at - 1].strip() == "":
        insert_at -= 1

    lines.insert(insert_at, f"{key} = {value_literal}")
    return "\n".join(lines) + "\n"


def upsert_key_in_section(text: str, section_header: str, key: str, value_literal: str) -> str:
    lines = text.splitlines()
    section_line = f"[{section_header}]"
    key_prefix = f"{key} ="

    section_start = None
    for index, line in enumerate(lines):
        if line.strip() == section_line:
            section_start = index
            break

    if section_start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(section_line)
        lines.append(f"{key} = {value_literal}")
        return "\n".join(lines) + "\n"

    section_end = len(lines)
    for index in range(section_start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section_end = index
            break

    for index in range(section_start + 1, section_end):
        if lines[index].strip().startswith(key_prefix):
            lines[index] = f"{key} = {value_literal}"
            return "\n".join(lines) + "\n"

    lines.insert(section_end, f"{key} = {value_literal}")
    return "\n".join(lines) + "\n"


def write_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def ensure_global_stop_hook(home: Path) -> Path:
    hooks_path = home / HOOKS_RELATIVE_PATH
    payload: dict[str, object]
    try:
        payload = json.loads(read_text(hooks_path) or "{}")
    except json.JSONDecodeError:
        payload = {}

    hooks = payload.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        payload["hooks"] = hooks

    stop_groups = hooks.setdefault("Stop", [])
    if not isinstance(stop_groups, list):
        stop_groups = []
        hooks["Stop"] = stop_groups

    command = 'python3 "$HOME/.local/share/codex-loop/codex_loop_stop_hook.py"'
    already_present = False
    for group in stop_groups:
        if not isinstance(group, dict):
            continue
        group_hooks = group.get("hooks")
        if not isinstance(group_hooks, list):
            continue
        for hook in group_hooks:
            if isinstance(hook, dict) and hook.get("command") == command:
                already_present = True
                break
        if already_present:
            break

    if not already_present:
        stop_groups.append(
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": command,
                        "statusMessage": "Codex Loop checking task completion",
                    }
                ]
            }
        )

    ensure_parent(hooks_path)
    hooks_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return hooks_path


def install_helper_scripts(source_repo: Path, home: Path) -> tuple[Path, list[str]]:
    share_dir = home / HELPER_SHARE_RELATIVE_PATH
    bin_dir = home / HELPER_BIN_RELATIVE_PATH
    share_dir.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)

    installed_commands: list[str] = []
    for command_name, script_name in HELPER_SCRIPTS.items():
        source_script = source_repo / "scripts" / script_name
        if not source_script.exists():
            raise SystemExit(f"未找到 helper script: {source_script}")

        target_script = share_dir / script_name
        shutil.copyfile(source_script, target_script)
        target_script.chmod(0o755)

        wrapper_path = bin_dir / command_name
        wrapper_path.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env bash",
                    "set -euo pipefail",
                    f'exec python3 "{target_script}" "$@"',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        wrapper_path.chmod(0o755)
        installed_commands.append(command_name)

    plugin_scripts_dir = source_repo / "plugins" / "codex-loop" / "scripts"
    for script_name in PLUGIN_SHARED_SCRIPTS:
        source_script = plugin_scripts_dir / script_name
        if not source_script.exists():
            raise SystemExit(f"未找到 runtime script: {source_script}")
        target_script = share_dir / script_name
        shutil.copyfile(source_script, target_script)
        target_script.chmod(0o755)

    root_scripts_dir = source_repo / "scripts"
    for script_name in ROOT_SHARED_SCRIPTS:
        source_script = root_scripts_dir / script_name
        if not source_script.exists():
            raise SystemExit(f"未找到 shared script: {source_script}")
        target_script = share_dir / script_name
        shutil.copyfile(source_script, target_script)
        target_script.chmod(0o755)

    return bin_dir, installed_commands


def load_marketplace(repo_root: Path) -> tuple[str, str]:
    marketplace_path = repo_root / MARKETPLACE_RELATIVE_PATH
    payload = json.loads(marketplace_path.read_text(encoding="utf-8"))
    marketplace_name = str(payload["name"])
    plugin_name = str(payload["plugins"][0]["name"])
    return marketplace_name, plugin_name


def add_or_upgrade_marketplace(source: str, marketplace_name: str) -> None:
    result = run(["codex", "plugin", "marketplace", "add", source])
    if result.returncode == 0:
        return

    combined = "\n".join(part for part in [result.stdout, result.stderr] if part).lower()
    if "already" in combined or "exists" in combined:
        upgrade = run(["codex", "plugin", "marketplace", "upgrade", marketplace_name])
        if upgrade.returncode == 0:
            return
        raise SystemExit(upgrade.stderr.strip() or upgrade.stdout.strip() or "marketplace upgrade 失败")

    raise SystemExit(result.stderr.strip() or result.stdout.strip() or "marketplace add 失败")


def main() -> int:
    parser = argparse.ArgumentParser(description="Install codex-loop in one step.")
    parser.add_argument("--source", required=True, help="Local path to the marketplace repository")
    parser.add_argument(
        "--marketplace-source",
        required=False,
        help="Marketplace source passed to `codex plugin marketplace add`; defaults to --source",
    )
    args = parser.parse_args()

    source_repo = Path(args.source).resolve()
    if not (source_repo / MARKETPLACE_RELATIVE_PATH).exists():
        raise SystemExit(f"未找到 marketplace.json: {source_repo / MARKETPLACE_RELATIVE_PATH}")
    marketplace_source = args.marketplace_source or str(source_repo)

    ensure_codex()

    marketplace_name, plugin_name = load_marketplace(source_repo)
    home = Path.home()
    config_path = home / CONFIG_RELATIVE_PATH
    config_text = read_text(config_path)
    config_text = upsert_top_level_key(config_text, "suppress_unstable_features_warning", "true")
    config_text = upsert_key_in_section(config_text, "features", "codex_hooks", "true")
    plugin_section = f'plugins."{plugin_name}@{marketplace_name}"'
    config_text = upsert_key_in_section(config_text, plugin_section, "enabled", "true")
    write_text(config_path, config_text)

    add_or_upgrade_marketplace(marketplace_source, marketplace_name)
    helper_bin_dir, installed_commands = install_helper_scripts(source_repo, home)
    hooks_path = ensure_global_stop_hook(home)
    helper_bin_in_path = str(helper_bin_dir) in os.environ.get("PATH", "").split(":")

    sys.stdout.write(
        "\n".join(
            [
                "codex-loop 安装完成。",
                f"marketplace: {marketplace_name}",
                f"marketplace source: {marketplace_source}",
                f"plugin: {plugin_name}@{marketplace_name}",
                f"config: {config_path}",
                "已确保 suppress_unstable_features_warning = true",
                "已确保 features.codex_hooks = true",
                "已确保插件启用。",
                f"已确保全局 Stop hook 配置: {hooks_path}",
                f"已安装本地辅助脚本到: {helper_bin_dir}",
                f"可用命令: {', '.join(installed_commands)}",
                (
                    "当前 PATH 已包含该目录，可直接运行这些命令。"
                    if helper_bin_in_path
                    else f"当前 PATH 未包含该目录；可直接用绝对路径运行，或把 {helper_bin_dir} 加入 PATH。"
                ),
                "请重启 Codex 以加载新插件。",
            ]
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
