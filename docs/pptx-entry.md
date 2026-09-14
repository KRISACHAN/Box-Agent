# PPT 统一入口

公共 Skill `pptx`（PPT 制作）负责选择，生成仍由独立的后端 Skill 执行。

| 用户模式 | 内部 Skill | 默认交付 |
|---|---|---|
| 快速模式 | `ppt-fast` | 沿用原主题、版式和编辑流程；请求 PPTX 时导出文件 |
| 创意模式：静态 | `sn-ppt-entry` → `sn-ppt-story` → `sn-ppt-standard` | 静态 HTML 和可编辑 PPTX |
| 创意模式：动态 | `sn-ppt-entry` → `sn-ppt-story` → `sn-ppt-dazzle` | 带动效的 HTML，不是原生 PowerPoint 动画 |

Tools 和 Doctor 为创意模式提供共用工具和检查。未集成旧 Web、Creative 图片整页、
Workbench 或 Edit；Standard 自带静态页面与 PPTX exporter，保留源代码模块结构及字体许可。
静态字段为 `static_html` / `standard` / `static_postprocess`；默认要求 HTML 和 PPTX
同时交付，仅用户明确只要 HTML 时省略 PPTX。旧静态任务恢复时由 Entry 迁移对应字段，
保留绝对任务目录、原材料、大纲、页面及后处理选择。

## 选择与续跑

OfficeV3 直接发送用户需求，不做 PPT 正则分类或发送前的模式拦截。Box-Agent 原有通用
Skill 发现将匹配的入口放入目录，模型需调用 `get_skill` 读取完整指引；显式选择则由宿主
直接提供 Skill reference。当前 ACP 不按 PPT 关键词自动预载正文。只有用户在 prompt 中明确选择
“快速模式”或“创意模式”，或同一任务已有用户亲自作出的模式选择，才直接路由。其余
请求均调用 `request_user_decision`，使用 `presentation_mode` 分类和 `fast`/`creative`
选项。套模板、自由设计、静态/动态、文件格式或模型已写入的默认模式不能代替用户选择。
这仍是 Skill 的执行指引，不增加前端正则判断。

system 的通用 Skill 指引要求匹配任务先读取 Skill，且 Skill 要求人工选择时必须调用
决策工具并等待。`pptx` 强调 JSON 示例只是工具参数，普通正文不会触发选择卡。
同一任务同时匹配入口与旧后端时，用户未指定 Skill 则先读取入口，由入口路由；不删除
或禁用用户安装的旧 Skill，用户明确选择其他 Skill 时仍尊重其选择。
这些指引改善模型遵循，不能当作运行时对每次路由的强制保证；验收需检查实际
`get_skill`/显式 reference 和 `request_user_decision` 事件，不能仅看模型口头说明。

工具新增手动等待用法：省略 `default_option_id`、`requested_auto_submit_seconds` 及
相应安全声明。返回既有 `user_decision_request`，`autoSubmit.allowed=false`。原有请求
超时默认选项的调用仍必须提供完整声明，安全策略不变。

工具成功后现有 `ends_turn_on_success` 机制停止当前轮；OfficeV3 通过现有
`UserDecisionCard` 展示按钮，并以 `_meta.user_decision` 续跑同一个任务。ACP 将选择写入
既有 `[HOST_USER_DECISION_RESPONSE]` 用户消息；不增加 PPT 专用 RPC、状态文件或内核
策略。重复加载入口、补充材料和恢复会话沿用已有选择。取消卡片不自动选择任何模式。

## 名称和资源兼容

- 原 `pptx` 注册名改为 `ppt-fast`；物理目录 `document-skills/pptx/` 保留，避免移动原有
  导出器、受信同步脚本和打包资源路径。新入口位于 `skills/pptx/SKILL.md`。
- 公共入口与后端设置 `metadata.allow_override=false`，避免旧用户安装覆盖该套件。
  后端另设 `metadata.user_visible=false`；它们不参与普通目录推荐，但允许精确读取。
  显式禁用、任务作用域和 Connector 授权限制仍生效。
- `ppt-router` 是旧演示入口；新内置目录不注册该名称。旧分支和用户安装不在迁移中删除。
- 保存过旧 Skill 注册名的任务可能需要新建任务；本改动不改写历史会话或用户禁用设置。

## 视觉检查

`inspect_images` 的代理请求继承主会话当前的 thinking 开关，包括首轮附件预处理和
后续轮次切换；不再因子请求漏传而落入默认关闭值。同一主/视觉 client 使用同一套
provider 参数映射；单独配置的视觉 client 保留自身 provider 和关闭思考时的档位策略。
原生图片路径继续直接随主请求发送。主会话本身关闭思考时的服务兼容配置仍由 provider
负责，此改动不把所有模型的 `none` 全局替换为 `low`。

## 更新创意模块

源库保持独立开发。`scripts/sync_presentation_suite.py` 从指定 Git 提交读取六模块及所需
资源，用可检查的替换适配两个出口和 Box-Agent 工具名称。源文本变化不满足适配条件时
同步失败，要求维护者重新检查，不静默套用旧修改。`source.json` 记录来源和集成后文件哈希。

```bash
uv run python scripts/sync_presentation_suite.py --source-checkout /path/to/sensenova-presentation-int
uv run python scripts/generate_skills_manifest.py
uv run pytest -q tests/test_pptx_entry.py tests/test_presentation_suite_bundle.py tests/test_request_user_decision_tool.py
```

跨仓库交付需要重建 Box-Agent runtime 并将其装入 OfficeV3 包。连接正式服务的未签名
macOS 包使用 `publish:electron-mac-unsigned`；`:test` 会编入测试服务地址。用户在新包内
登录正式环境后，客户端自动同步 Box-Agent 登录态。源测试、包内协议探针、真实模型
生成和视觉质量分别验收，不能互相替代。
