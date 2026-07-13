# 开发指南

## 目录

- [开发指南](#开发指南)
  - [目录](#目录)
  - [1. 项目架构](#1-项目架构)
  - [2. 基础使用](#2-基础使用)
    - [2.1 交互式命令](#21-交互式命令)
    - [2.2 已集成的 MCP 工具](#22-已集成的-mcp-工具)
      - [Tavily - 网页搜索与内容抽取](#tavily---网页搜索与内容抽取)
      - [Memory - MCP 知识图谱服务器](#memory---mcp-知识图谱服务器)
      - [Playwright - 浏览器自动化](#playwright---浏览器自动化)
  - [3. 扩展能力](#3-扩展能力)
    - [3.1 添加自定义工具](#31-添加自定义工具)
      - [步骤](#步骤)
      - [示例](#示例)
    - [3.2 添加 MCP 工具](#32-添加-mcp-工具)
    - [3.3 内置 Skills](#33-内置-skills)
      - [officev3 推荐 Skills](#officev3-推荐-skills)
    - [3.4 添加新的 Skill](#34-添加新的-skill)
    - [3.5 自定义系统提示词](#35-自定义系统提示词)
      - [可定制内容包括：](#可定制内容包括)
  - [4. 故障排查](#4-故障排查)
    - [4.1 常见问题](#41-常见问题)
      - [API 密钥配置错误](#api-密钥配置错误)
      - [依赖安装失败](#依赖安装失败)
      - [MCP 工具加载失败](#mcp-工具加载失败)
    - [4.2 调试技巧](#42-调试技巧)
      - [启用 Debug 日志](#启用-debug-日志)
      - [使用 Python 调试器](#使用-python-调试器)
      - [监控工具调用](#监控工具调用)

---

## 1. 项目架构

```
box-agent/
├── box_agent/              # 核心源代码
│   ├── core.py              # 执行核心 — run_agent_loop()（Agent 循环本体）
│   ├── agent.py             # 公共 API 封装（Agent 类）
│   ├── llm/                 # Provider 客户端和 LLM 包装器
│   ├── acp/                 # ACP 服务与宿主对接
│   ├── cli.py               # 命令行接口
│   ├── config.py            # 配置加载
│   ├── tools/               # 工具实现（文件、Bash、MCP、技能等）
│   └── skills/              # 内置 Skills 与 manifest
├── tests/                   # 测试代码
├── docs/                    # 文档
├── workspace/               # 工作目录
└── pyproject.toml           # 项目配置
```

## 2. 基础使用

### 2.1 交互式命令

在交互模式 (通过 `box-agent` 启动) 下运行 Agent 时，您可以使用以下命令：

| 命令                   | 说明                                             |
| ---------------------- | ------------------------------------------------ |
| `/exit`, `/quit`, `/q` | 退出 Agent 并显示会话统计信息                    |
| `/help`                | 显示帮助信息和可用命令                           |
| `/clear`               | 清除消息历史并开始新会话                         |
| `/clear_all`           | 清除消息历史并关闭沙箱 kernel                    |
| `/history`             | 显示当前会话的消息数量                           |
| `/stats`               | 显示会话统计信息（步数、工具调用、使用的 Token） |
| `/sandbox_status`      | 显示沙箱会话状态                                 |
| `/log`                 | 显示日志目录或读取指定日志文件                   |
| `/goal`                | 查看或管理当前工作区的持久目标                   |
| `/memory review`       | 审阅可升级为核心记忆的候选条目                   |

CLI 管理命令也可以脚本化使用：

```bash
box-agent --goal "完成发布检查" --task "运行验证"
box-agent --goal "完成发布检查" --task "运行验证" --no-goal-autopilot
box-agent goal status --json
box-agent goal progress "已更新 ACP 文档"
box-agent goal complete --evidence "uv run pytest tests/ -q passed"
```

### 2.2 已集成的 MCP 工具

项目在 `box_agent/config/mcp-example.json` 中提供默认禁用的 MCP 示例配置。
运行 `box-agent install-browser` 会安装 Chromium，并在用户配置中启用 Playwright 入口。
其它 MCP server 需要在 `~/.box-agent/config/mcp.json` 中显式启用。

#### Tavily - 网页搜索与内容抽取

**功能**：通过 Tavily MCP 提供网页搜索和内容抽取。

**状态**：默认禁用；需要在 MCP URL 中配置 Tavily API key。

#### Memory - MCP 知识图谱服务器

**功能**：可选的 Model Context Protocol memory server。

**状态**：默认禁用。Box-Agent 内置记忆工具与这个 MCP server 是两套能力，由 `enable_memory` 控制。

#### Playwright - 浏览器自动化

**功能**：通过 `@playwright/mcp` 提供浏览器自动化。

**状态**：默认禁用。运行 `box-agent install-browser` 会安装 Chromium，并把用户 MCP 配置中的 `mcpServers.playwright.disabled` 改为 `false`。

**配置示例**：

```json
{
  "mcpServers": {
    "tavily": {
      "description": "Tavily - Web search and content extraction",
      "url": "https://mcp.tavily.com/mcp/?tavilyApiKey=YOUR_API_KEY",
      "type": "streamable_http",
      "disabled": false
    },
    "playwright": {
      "description": "Playwright - Browser automation (Chromium)",
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest"],
      "disabled": false
    }
  }
}
```

## 3. 扩展能力

### 3.1 添加自定义工具

#### 步骤

1.  在 `box_agent/tools/` 目录下创建一个新的 Python 文件。
2.  在文件中定义一个新类，并继承 `Tool` 基类。
3.  在类中实现所需的属性和方法。
4.  在 Agent 初始化时注册你的新工具。

#### 示例

```python
# box_agent/tools/my_tool.py
from box_agent.tools.base import Tool, ToolResult
from typing import Dict, Any

class MyTool(Tool):
    @property
    def name(self) -> str:
        """工具的唯一名称，需保持独一无二。"""
        return "my_tool"

    @property
    def description(self) -> str:
        """工具用途的详细描述，帮助 LLM 理解其功能。"""
        return "我的自定义工具，用于完成特定任务"

    @property
    def parameters(self) -> Dict[str, Any]:
        """参数模式（JSON Schema 格式）。"""
        return {
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "第一个参数"
                },
                "param2": {
                    "type": "integer",
                    "description": "第二个参数",
                    "default": 10
                }
            },
            "required": ["param1"]
        }

    async def execute(self, param1: str, param2: int = 10) -> ToolResult:
        """
        工具执行的核心逻辑。

        Args:
            param1: 参数一。
            param2: 参数二，包含默认值。

        Returns:
            返回一个 ToolResult 对象。
        """
        try:
            # 在此实现你的逻辑
            result = f"处理了 {param1}，param2={param2}"

            return ToolResult(
                success=True,
                content=result
            )
        except Exception as e:
            return ToolResult(
                success=False,
                content=f"错误: {str(e)}"
            )

# 在 cli.py 或 Agent 的初始化代码中
from box_agent.tools.my_tool import MyTool

# 创建 Agent 实例时，将新工具加入列表
tools = [
    ReadTool(workspace_dir),
    WriteTool(workspace_dir),
    MyTool(),  # 添加您的自定义工具
]

agent = Agent(
    llm=llm,
    tools=tools,
    max_steps=100
)
```

CLI `--task` 模式和 ACP 会话会对持久 goal 启用有边界的自动续跑。如果一轮自然结束但 goal 仍是 `active`，Box-Agent 会注入内部 continuation，直到模型调用 `goal_write complete`、调用 `goal_write block`、用户取消，达到 `goal_autopilot_max_turns` / `goal_autopilot_max_seconds` 配置预算，或连续 `goal_autopilot_no_progress_turns` 个自动续跑轮次没有记录到 goal 进展。

### 3.2 添加 MCP 工具

编辑 `mcp.json` 文件，即可添加新的 MCP 服务器：

```json
{
  "mcpServers": {
    "my_custom_mcp": {
      "description": "我的自定义 MCP 服务器",
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@my-org/my-mcp-server"],
      "env": {
        "API_KEY": "your-api-key"
      },
      "disabled": false,
      "notes": {
        "description": "这是一个自定义 MCP 服务器。",
        "api_key_url": "https://example.com/api-keys"
      }
    }
  }
}
```

### 3.3 内置 Skills

内置 skills 已提交在 `box_agent/skills/` 下，并通过 `box_agent/skills/_manifest.json` 加载。
正常开发不需要执行 git submodule 初始化。

当前 manifest 列出 32 个内置 skills，包括：

- 📄 **文档处理**：轻松创建和编辑 PDF、DOCX、XLSX、PPTX 等格式的文档。
- 🎨 **设计创作**：生成富有创意的艺术作品、海报和 GIF 动画。
- 🧪 **开发与测试**：支持 Web 自动化测试 (Playwright) 和 MCP 服务器开发。
- 🏢 **企业应用**：高效处理内部沟通、品牌指南应用和主题定制等任务。

如果内置 skills 发生变化，发布前需要重新生成并提交 manifest：

```bash
uv run python scripts/generate_skills_manifest.py
```

#### officev3 推荐 Skills

有些投稿技能需要随 Box-Agent runtime 一起发布，让 officev3 显示成可一键安装的推荐卡片，但又不应该作为始终加载的内置技能启用。这类技能需要同时改 Box-Agent 和 officev3：

1. 将技能目录放到 `box_agent/skills/<skill-slug>/`。`SKILL.md` frontmatter 需要包含完整的 `name`、`description`，推荐卡片需要署名时还要填写 `author`。
2. 在 `scripts/generate_skills_manifest.py` 的 `EXCLUDED_SKILL_DIRS` 中加入这个顶层目录名。这样技能会继续随包存在于磁盘上，但不会进入内置 `_manifest.json` 白名单。
3. 重新生成 manifest：

   ```bash
   uv run python scripts/generate_skills_manifest.py
   ```

   确认脚本输出 `info: excluding '<skill-slug>/SKILL.md'`，并确认 `box_agent/skills/_manifest.json` 中没有这个技能。
4. 在 officev3 仓库的 `electron/main/skillManager.ts` 中，把推荐卡片加入 `DEFAULT_RECOMMENDED`。`sourcePath` 要和 `box_agent/skills/` 下的技能目录匹配，`installable` 设为 `true`，社区投稿推荐位使用 `featured` 分类。
5. 重新构建或同步 officev3 使用的 Box-Agent runtime。推荐卡片只有在 runtime 里实际包含这个技能目录时才能安装成功；从 `_manifest.json` 排除只负责避免它被当作内置技能自动加载。

**更多信息：**

- [Claude Skills 官方文档](https://docs.claude.com/zh-CN/docs/agents-and-tools/agent-skills)
- [Anthropic 博客：为真实世界装备智能体](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)

### 3.4 添加新的 Skill

您可以按照以下步骤创建自定义 Skill：

```bash
# 在用户 skills 目录下创建新技能
mkdir -p ~/.box-agent/skills/my-custom-skill
cd ~/.box-agent/skills/my-custom-skill

# 创建技能描述文件 SKILL.md
cat > SKILL.md << 'EOF'
---
name: my-custom-skill
description: 这是一个自定义技能，用于处理特定任务。
allowed-tools:
  - read_file
---

# 概述

该技能主要提供以下功能：
- 功能 1
- 功能 2

# 使用方法

1. 第一步...
2. 第二步...

# 最佳实践

- 实践 1
- 实践 2

# 常见问题

问：问题 1
答：答案 1
EOF
```

完成以上步骤后，Agent 将在下次启动时自动加载并识别这项新技能。

`allowed-tools`（也兼容 `allowed_tools`）会在加载时归一化、去重并排序。它是
skill catalog 中的路由元数据；当显式子 Agent 选择该 Skill 时，也会进入请求能力
集合，但运行时仍会与父会话实时工具和委派约束取交集。只声明 Skill 真正需要的
最小工具集。依赖 Skill 写入 `required_skills`；`related_skills` 只是推荐项，不会
自动加载。详见[子 Agent 委派](SUB_AGENT_DELEGATION_CN.md)。

### 3.5 自定义系统提示词

系统提示词文件 (`system_prompt.md`) 定义了 Agent 的核心行为、能力边界和工作指南。您可以根据具体应用场景，对其进行深度定制。

#### 可定制内容包括：

1.  **核心能力**：添加或修改工具的描述，以影响 Agent 的工具选择。
2.  **工作指南**：定义特定的工作流程或决策偏好。
3.  **领域专业知识**：注入特定领域的知识，提升 Agent 的专业性。
4.  **沟通风格**：调整 Agent 与用户交互时的语气和风格。
5.  **任务优先级**：设定处理任务时的优先级和策略。

完成修改后，请重启 Agent 以使新配置生效。

## 4. 故障排查

### 4.1 常见问题

#### API 密钥配置错误

```bash
# 错误消息
Error: Invalid API key

# 解决方法
1. 检查 `config.yaml` 文件中的 API 密钥是否填写正确。
2. 确保密钥前后没有多余的空格或引号。
3. 确认该 API 密钥是否仍在有效期内。
```

#### 依赖安装失败

```bash
# 错误消息
uv sync failed

# 解决方法
1. 升级 uv 至最新版本：`uv self update`
2. 清理 uv 缓存：`uv cache clean`
3. 再次尝试同步依赖：`uv sync`
```

#### MCP 工具加载失败

```bash
# 错误消息
Failed to load MCP server

# 解决方法
1. 检查 `mcp.json` 文件中的服务器配置是否正确。
2. 确保您的开发环境已安装 Node.js (大部分 MCP 工具的运行需要)。
3. 确认所需服务的 API 密钥已正确配置。
4. 运行 MCP 测试并查看详细日志：`pytest tests/test_mcp.py -v -s`
```

### 4.2 调试技巧

#### 启用 Debug 日志

```python
# 在 cli.py 或相关测试文件的开头添加以下代码：
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

#### 使用 Python 调试器

```python
# 在需要暂停执行的代码行处插入断点：
import pdb; pdb.set_trace()

# 或者使用 ipdb 以获得更佳的调试体验：
import ipdb; ipdb.set_trace()
```

#### 监控工具调用

```python
# 在 Agent 代码中添加日志，以便实时查看工具的调用详情：
logger.debug(f"工具调用: {tool_call.name}")
logger.debug(f"工具参数: {tool_call.arguments}")
logger.debug(f"工具结果: {result.content[:200]}")
```
