#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from codex_loop_spec import load_json_file, validate_spec_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate .codex-loop/spec.json for the current repository.")
    parser.add_argument(
        "--path",
        default=".codex-loop/spec.json",
        help="Path to the spec file, defaults to .codex-loop/spec.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()
    spec_path = (repo_root / args.path).resolve()

    if not spec_path.exists():
        print(f"未找到 spec 文件: {spec_path}")
        return 1

    try:
        spec = load_json_file(spec_path)
    except Exception as exc:
        print(f"spec.json 解析失败: {exc}")
        return 1

    errors = validate_spec_payload(spec, repo_root)
    if errors:
        print(f"spec 校验失败: {spec_path}")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"spec 校验通过: {spec_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
