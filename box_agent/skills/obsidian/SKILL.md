---
name: obsidian
description: Use this skill whenever the user asks to create, export, save, append, prepend, open, or write Markdown notes in Obsidian. It explains when to call the native obsidian_* tools backed by the official Obsidian CLI, and how to avoid unsafe direct bash CLI writes.
keywords: [obsidian, vault, note, daily note, todo, markdown, 导出 Obsidian, 写入 Obsidian, 保存到 Obsidian, 追加到 Obsidian, 笔记, 日记]
---

# Obsidian 笔记助手

当用户明确要求把内容写入、导出、保存、追加或打开到 Obsidian 时，使用本 skill，并优先调用 Box-Agent 的原生 `obsidian_*` 工具。

## 何时使用

出现这些信号就进入本流程：

- “导出到 Obsidian”
- “保存到 Obsidian”
- “写入 Obsidian”
- “追加到某篇 Obsidian 笔记”
- “生成今天的 todo 到 Obsidian”
- “打开 / 更新 / 覆盖 Obsidian 笔记”

## 工具选择

- 新建普通笔记：调用 `obsidian_create_note`。
- 追加、前置或覆盖已有笔记：调用 `obsidian_update_note`。
- 今天的 Daily Note / todo / 日记：调用 `obsidian_daily_note`。

## 引用上下文写回

当 prompt 中存在 `<obsidian_context ... path="...">`，表示 officev3 已从 Vault 原文件读取该笔记内容作为上下文。

- 只读问题（提问、总结、统计、分析）直接参考 `obsidian_context` 回答。
- 如果用户明确要求修改、保存、追加、前置或覆盖这篇被引用的 Obsidian 笔记，必须使用 context 中的 Vault 相对 `path` 调用 `obsidian_update_note`。
- 不要修改 workspace 文件、`.data-sources` 副本或自行复制出的 Markdown 文件；Obsidian 写回以 Vault 原文件为准。

## 路径规则

- `path` 必须是 Vault 相对路径，例如 `Projects/AI 周报.md`。
- 不要传绝对路径。
- 不要使用 `..`。
- 写入目标必须是 `.md` 文件。

## Bash 边界

可以用 bash 做诊断：

```bash
obsidian version
obsidian help
which obsidian
```

不要用 bash 直接执行写入或打开类命令，例如：

```bash
obsidian create ...
obsidian append ...
obsidian prepend ...
obsidian open ...
obsidian daily ...
```

这些操作必须走 `obsidian_*` 原生工具，因为工具会处理 Vault 配置、路径校验、权限确认、CLI 参数转义和失败提示。

## 示例

用户：“帮我生成今天的 todo 项到 Obsidian。”

做法：整理 todo 内容后调用：

```text
obsidian_daily_note(action="append", content="<Markdown todo>", open_after=true)
```

用户：“把这份报告导出为 Obsidian 笔记。”

做法：调用：

```text
obsidian_create_note(title="报告标题", content="<Markdown report>", open_after=true)
```
