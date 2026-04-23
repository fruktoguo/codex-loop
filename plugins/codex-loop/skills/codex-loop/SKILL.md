---
name: codex-loop
description: Use when the user wants Codex to keep going until a task satisfies explicit done criteria enforced by a Stop hook.
---

# Codex Loop

Use this skill when the user wants a true completion gate instead of a single best-effort reply.

## Standard interaction

The standard user workflow is:

1. The user explicitly invokes `$codex-loop` or clearly asks for loop execution.
2. The user describes the task in natural language.
3. You create or refresh `.codex-loop/spec.json` yourself.
4. You validate the spec yourself.
5. You continue the real task under that spec.

Do not make the user run `codex-loop-init` or `codex-loop-validate` as the normal path. Those helper commands are implementation tools for you, not the user's primary interface.

## Spec creation rule

When the task is to create or refresh `.codex-loop/spec.json`, prefer this order:

1. Infer the correct spec shape from the user's request.
2. Write or update `.codex-loop/spec.json` yourself.
3. Validate it before claiming the spec is ready.

If local helper scripts are available, you may use them internally. If not, write the JSON manually and validate it against the field rules below.

## What this plugin expects

The current repository should contain `.codex-loop/spec.json` with:

- `enabled`
- `task`
- `done_token`
- `required_sections`
- `required_paths_modified` when completion must include actual file edits
- `required_paths_exist` when completion must create concrete artifacts
- `commands` when completion must pass real command checks
- `max_rounds`

If the file does not exist yet, create it before continuing substantive work.

## Field selection rules

- `required_sections`
  - Use the default three sections only when the final answer should be structured.
  - If the user wants a plain-text final reply like `hello`, set it to `[]`.
- `required_paths_modified`
  - Only use this when completion must include real file modifications.
  - If the current directory is not a git repo, it must be `[]`.
- `required_paths_exist`
  - Use this only when completion must create concrete files or directories.
- `commands`
  - Only add real command gates the task actually needs.
  - If the task is just conversational or text-only, keep it `[]`.
- `done_token`
  - Must be a single non-whitespace token.
- `max_rounds`
  - Must be a positive integer.

## Authoring discipline

When you generate `.codex-loop/spec.json` from a user request:

1. Translate the user intent into the smallest sufficient gate.
2. Do not add file gates or command gates unless the task truly needs them.
3. Do not default to structured sections for plain-text or conversational tasks.
4. Do not invent extra acceptance conditions that the user did not ask for.
5. After writing the file, verify that:
   - the JSON parses,
   - all required top-level keys exist,
   - the chosen gates match the user intent,
   - no field conflicts with the current directory context, especially non-git directories.

If validation fails, fix the file before proceeding with the task.

## Working contract

When Codex Loop is active:

1. Read the spec before major work.
2. Treat `required_sections` as mandatory output sections in the final answer.
3. Include `done_token` only when the task is truly complete by the spec, and place it near the end of the final reply. Very short final replies are tolerated automatically.
4. Do not emit the done token in partial progress updates.
5. If `commands` are configured, treat them as real gate checks. A final answer is not complete unless those commands pass.
6. If `required_paths_modified` or `required_paths_exist` are configured, satisfy them before emitting the done token.
7. If verification is incomplete, be explicit; Codex Loop should keep the loop alive until the final answer format and command/path gates are satisfied or `max_rounds` is reached.

## Recommended defaults

```json
{
  "enabled": true,
  "task": "[current task]",
  "done_token": "STOPGATE_DONE",
  "required_sections": [
    "完成了什么",
    "验证结果",
    "剩余风险"
  ],
  "required_paths_modified": [
    "src/"
  ],
  "required_paths_exist": [],
  "commands": [
    {
      "label": "typecheck",
      "command": "pnpm build",
      "cwd": ".",
      "expect_exit_code": 0
    }
  ],
  "max_rounds": 99
}
```

## Request translation examples

If the user says:

```text
$codex-loop 修复这个构建错误，并确认 pnpm build 通过
```

Then the spec should usually include:

- a structured `task`
- default `required_sections`
- a real `commands` gate such as `pnpm build`
- `required_paths_modified` only if actual code edits are required

If the user says:

```text
$codex-loop 创建一个循环任务，每次只回复 hello，第 3 次结束
```

Then the spec should usually include:

- plain-text `task`
- `done_token` such as `HELLO_LOOP_DONE`
- `required_sections: []`
- `required_paths_modified: []`
- `required_paths_exist: []`
- `commands: []`
- `max_rounds: 3`

Helper commands may still be used internally, but never present them as the required user workflow.

## Final answer discipline

A Codex Loop-compatible final answer should place the token near the end:

```text
完成了什么
...

验证结果
...

剩余风险
...

STOPGATE_DONE
```

Do not include the token unless you are willing for the loop to stop.
