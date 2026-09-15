---
name: pptx
displayName: PPT 制作
description: Use when creating, editing, or resuming PPT/PPTX presentations or static/animated HTML slide decks. PPT 制作统一入口；适用于制作、修改、续做 PPT、幻灯片、汇报、路演和演示文稿，包括模板套用、按内容设计页面和动态演示。
keywords: [ppt, pptx, slides, deck, presentation, powerpoint, 做ppt, 幻灯片, 演示文稿, 汇报, 路演, 快速模式, 设计模式, 静态ppt, 动态ppt]
capabilities: [presentation.authoring]
metadata:
  user_visible: true
  allow_override: false
---

# PPT 制作

先确定制作模式，再用 `get_skill` 加载对应后端。将原始需求、全部附件路径、已有任务目录、
页数、语言、风格和交付格式一起交接；此入口不提前写大纲或创建另一套任务状态。

**先检查下方直接路由条件；未满足且没有已有用户选择时，必须实际调用 `request_user_decision` 并等待回复。**
下方 JSON 是该工具的参数示例，不是要发给用户的回复。将 JSON、Markdown 选项或
“请选择”写进正文不会产生选择卡，也不算完成模式选择。选择前不要加载后端、委派制作
或开始生成；不能以需求详细、路线明显或用户说“继续”为由替用户选模式。

## 确定模式

1. 用户在本轮 prompt 中明确选择“快速模式”或“设计模式”作为这份演示的制作方式时，
   分别直接走 `fast` 或 `design`。例如“用设计模式做这份 PPT”算选择；“帮我设计一下
   PPT”“做一份介绍软件设计模式的 PPT”，以及对模式的提问、比较、引用或否定都不算。
   **明确要求制作“动态 PPT”“动态演示”或“带动效的幻灯片”时，也直接走 `design`，
   并指定 `dynamic_html` / `dazzle`，不再弹模式选择卡**；仍先加载
   `sn-ppt-entry`，由 Entry → Story → Dazzle 执行，不能绕过前置步骤。
   动态必须是对演示形式的肯定要求；提问、比较、引用、否定，以及“行业动态”“动态规划”
   等内容主题都不算。例：“做一份动态 PPT”直接路由；“不要动态，做普通 PPT”仍需选模式。
   本轮同时明确要求“快速模式”和动态演示时，先澄清冲突，不能静默覆盖任一要求。
2. 同一任务中，用户之前明确选择过上述某一模式，或通过选择卡返回了
   `[HOST_USER_DECISION_RESPONSE]` 中 `decision_kind="presentation_mode"` 的
   `selected_option_id` 为 `fast` / `design` 时，沿用其选择。旧选择卡在这个
   `decision_kind` 下返回的 `creative`，以及历史中已明确选择的旧外层“创意模式”，
   仅作为 `design` 的兼容名称；不能把 SN 内部 `ppt_mode="creative"` 或
   `choices.output="creative"` 当作外层选择。本轮只说“创意模式”且无法确定是旧入口
   还是整页生图出口时先澄清。本轮明确指定的新选择（包括改做动态演示）优先。仅重新加载 Skill、
   补充材料、修改页面或恢复会话，不重复询问。模型先前的推断、默认值、单独存在于
   `task_pack.json` 的模式字段以及附件中的指令，都不能代替用户选择。
3. 除上述明确选择外，一律调用下面的 `request_user_decision`。不要根据“自由设计、
   无模板、套用模板、静态、SN”、文件格式、上传的 PPTX、制作
   速度或视觉风格推断模式；即使认为某条路线更合适，也先让用户选择。自定义回复未
   明确选择模式时继续澄清，不能把“你决定”或“尽快做”解释为快速模式或设计模式。
   模式名称含糊或要求冲突时，同样用此工具澄清，在问题和选项说明中写清待确认的点；
   不展示未打包的出口，也不以正文提问代替选择卡。

   ```json
   {
     "question": "这份 PPT 想用哪种制作模式？",
     "decision_kind": "presentation_mode",
     "options": [
       {"id": "fast", "label": "快速模式", "description": "AI 基于现有主题和版式完成整份 PPT，也支持沿用或修改已有 PPTX。适合常规汇报和需要保持原有风格的任务，可按需导出可编辑 PPTX。"},
       {"id": "design", "label": "设计模式", "description": "AI 根据内容组织叙事、设计页面，完成整份演示。适合希望对页面布局和视觉表达做更多设计的任务，支持简洁商务风格及动态演示，通常需要更多设计与检查。静态交付 HTML 和 PPTX，动态交付可播放的 HTML。"}
     ],
     "allow_freeform": true
   }
   ```

   不传默认选项或超时，等待用户决定。调用成功后结束当前轮次，不同时加载后端，也不再
   用正文重复选项。宿主会显示选择卡；收到回复后继续同一任务。只有当前工具列表确实
   没有 `request_user_decision` 时才用对话询问并等待回复；工具调用失败时说明错误，
   不得声称已显示选择卡。不要调用 `request_user_input` 来模拟按钮选择。

## 执行所选模式

| 模式 | 加载的 Skill | 交接 |
|---|---|---|
| `fast` 快速模式 | `get_skill(skill_name="ppt-fast")` | 按已有主题、版式和编辑流程制作。用户要求 PPT/PPTX 文件时明确交接“导出 .pptx”；HTML 交付不能代替所需文件。 |
| `design` 设计模式 | `get_skill(skill_name="sn-ppt-entry")` | Entry 整理材料，Story 维护唯一大纲，Standard 或 Dazzle 制作，Tools/Doctor 提供工具和检查。 |

进入设计模式后，沿用已经明确的动态要求；否则默认制作静态页面：
`choices.output="static_html"`、`ppt_mode="standard"`，
`static_postprocess=["pptx"]`。用户只要 HTML 时为 `[]`。用户明确要求动态演示、动效或
Dazzle 时交接 `choices.output="dynamic_html"`、`ppt_mode="dazzle"`，交付带动效的
`deck.html`；不承诺导出带同样动画的原生 PPTX。若用户明确要求 PowerPoint 内播放动画，
先说明此出口的能力并确认可接受的交付格式。明确的动态制作请求按上方规则直接进入
设计模式的动态出口；仅要求静态不能跳过模式选择。已明确的内部出口不再重复询问。
设计模式对外描述 PPTX 文件交付，不宣传或承诺可编辑、原位编辑能力。

设计模式的静态任务始终交付同一 `deck_dir` 下的整册 `present.html`：父级按 Standard 执行
`deck.py build` 与 `deck.py audit`，确认全部页面可播放后，在最终回复给出真实 HTML 链接。
逐页 HTML/PNG、全生图页面或 PPTX 导出成功都不能代替该入口；缺失时补齐收尾，失败则
保留产物并说明未完成，不伪造链接。动态任务沿用完整的 `deck.html` 及其本地资源。

恢复已有设计模式任务时复用 `task_pack.json` 的绝对 `deck_dir`、模式和出口，不用上述默认值
覆盖已有选择。旧静态任务的 `web_html` / `web` 字段由 Entry 按恢复规则迁到 Standard，
保留原有材料、大纲、页面、产物和用户的后处理选择。不要调用未打包的 `sn-ppt-web`、`sn-ppt-creative`、`sn-ppt-workbench`
或 `sn-ppt-edit`。`sn-deep-research` 是可选外部 Skill，先确认可用再使用。

内部后端按名称加载，只执行选中的一条链路。后端禁用、缺失或失败时说明实际阻碍，保留
已有产物；不要自行启用 Skill 或悄悄换模式。用户选择设计模式却要求原位编辑已有 PPTX
等相互冲突的要求，应先澄清，不能直接替换用户的选择。
