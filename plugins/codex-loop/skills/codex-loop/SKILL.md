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
3. You create or refresh the current session-bound spec under `.codex-loop/specs/<session-id>.json` yourself.
4. You validate the spec yourself.
5. You continue the real task under that spec.

Do not make the user run `codex-loop-init` or `codex-loop-validate` as the normal path. Those helper commands are implementation tools for you, not the user's primary interface.

## Spec creation rule

When the task is to create or refresh the current session-bound spec, prefer this order:

1. Infer the correct spec shape from the user's request.
2. Write or update `.codex-loop/specs/<session-id>.json` yourself.
3. Validate it before claiming the spec is ready.

If local helper scripts are available, you may use them internally. If not, write the JSON manually and validate it against the field rules below.

## What this plugin expects

The current repository should contain a current-session spec at `.codex-loop/specs/<session-id>.json` with:

- `enabled`
- `completed`
- `task`
- `done_token`
- `required_sections`
- `required_paths_modified` when completion must include actual file edits
- `required_paths_exist` when completion must create concrete artifacts
- `commands` when completion must pass real command checks
- `max_rounds`

If the file does not exist yet, create it before continuing substantive work. Other sessions should not be affected by this spec.

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
  - Compatibility field. It must be a single non-whitespace token, but it is not the loop stop signal.
  - Do not add it to the final reply unless the user explicitly asked for that literal text.
- `completed`
  - Must start as `false`.
  - Set it to `true` only after the task is truly complete and all configured gates should pass.
- `max_rounds`
  - Must be a positive integer.

## Authoring discipline

When you generate a session-bound spec from a user request:

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
2. The current session's spec file is the loop completion switch.
3. Treat `required_sections` as final output guidance.
4. Keep `completed: false` while work is incomplete.
5. Before ending a completed task, edit the current session's `.codex-loop/specs/<session-id>.json` and change only the top-level `completed` field from `false` to `true`.
6. Set `completed: true` only after the task is truly complete and all configured gates should pass.
7. Do not include `done_token` in replies unless the user explicitly asked for that literal text.
8. Do not emit the done token in partial progress updates.
9. If `commands` are configured, treat them as real gate checks. A final answer is not complete unless those commands pass.
10. If `required_paths_modified` or `required_paths_exist` are configured, satisfy them before setting `completed: true`.
11. Once the task is complete, Codex Loop will archive the current session's active spec into `.codex-loop/history/` and remove that session-bound active spec.
12. If verification is incomplete, keep working or report the concrete blocker; do not end with a meta statement such as "I will not output the done token."

## Completion Switch

The loop stops only after the current session's spec has `completed: true` and the configured path/command gates pass. Text in the assistant reply is not enough to stop the loop.

When the work is truly done:

1. Open or patch `.codex-loop/specs/<session-id>.json`.
2. Change the top-level field `"completed": false` to `"completed": true`.
3. Leave unrelated spec fields unchanged.
4. Send the final answer in the format requested by the task. Do not add `done_token` unless the task explicitly requested it.

If the work is not done, do not modify `completed`; continue work or report the exact blocker.

## Recommended defaults

```json
{
  "enabled": true,
  "completed": false,
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
- `completed: false`
- default `required_sections`
- a real `commands` gate such as `pnpm build`
- `required_paths_modified` only if actual code edits are required

If the user says:

```text
$codex-loop 创建一个循环任务，每次只回复 hello，第 3 次结束
```

Then the spec should usually include:

- plain-text `task`
- `completed: false`
- a default compatibility `done_token`, but the replies should remain `hello` unless the user explicitly asks for extra text
- `required_sections: []`
- `required_paths_modified: []`
- `required_paths_exist: []`
- `commands: []`
- `max_rounds: 3`

Helper commands may still be used internally, but never present them as the required user workflow.

## Final answer discipline

A Codex Loop-compatible final answer should follow the task's requested shape:

```text
完成了什么
...

验证结果
...

剩余风险
...
```

Do not include the token unless the user explicitly requested that literal text. The loop stops from `completed: true` plus passing gates, not from reply text.
