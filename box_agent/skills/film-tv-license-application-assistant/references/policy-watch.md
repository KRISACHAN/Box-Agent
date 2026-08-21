# 政策变更巡检（F23）

本技能不爬取、不自动改法。巡检是**人工**对照官方原文，更新 references 与 source-map。

## 何时巡检

- 用户提出与包内日期（知识截止日期）冲突的新文件
- 距截止日期超过 90 天仍要做完整咨询
- 施行日临近：第 16 号（2026-09-01）前后必须复核一类/二类交接

## 必打开的源（优先一手）

1. https://www.chinafilm.gov.cn/ 通知公告、送审须知、割接/操作手册
2. http://www.nrta.gov.cn/ 令、通知、办事指南
3. https://www.gov.cn/zhengce/ 国务院令与部门文件库
4. 用户拟申报省的政务事项页（窗口加码）
5. CFCC https://www.cfcc-film.com.cn/ （合拍）

## 对照动作

| 检查 | 若变化 |
|------|--------|
| 入口 URL | 改 `official-links.md` + SKILL 入口句 |
| 证名/分类 | 改 `license-routing.md` 与对应 playbook |
| 材料份数/介质 | 改 playbook 与 `materials-checklists.md` |
| 时限用语 | 令文原文优先；窗口数字标 B |
| 手册仍冲突 | `common-errors.md` 增加一行，手册让路 |
| 新诚实边界 | 写入 `honest-boundaries.md`，禁止升格为硬规则 |

每次巡检更新：`policy-timeline.md` 一行 + `source-map.md` 日期 + SKILL.md 知识截止日期。

## 不做

不把媒体通稿、代办广告、未挂官网的「内部标准」写入硬路由。投资额万元档在 nrta.gov.cn 出现原文之前，保持 L3。
