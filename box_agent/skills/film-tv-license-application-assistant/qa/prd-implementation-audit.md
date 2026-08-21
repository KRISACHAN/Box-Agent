# PRD 落地审计

对照 `prd/PRD-影视资质申请助手-v1.0.md`（产品口径 v1.1）与 `prd/skill-blueprint-影视资质申请助手-v1.0.md`。

## 覆盖

| PRD / 蓝图 | 落地 |
|------------|------|
| 八步工作流 Step 0–7 | SKILL.md |
| 硬停点 | SKILL.md + phrasebook.md |
| 七段交付包 | templates/delivery-pack.md |
| 四条许可 + 微短剧分流 | license-routing + 四份 playbook + micro triage |
| 合拍三形式、VR 龙标 | playbook-coproduction / playbook-vr-film |
| 诚实边界 | honest-boundaries.md |
| T1–T10 | qa/smoke-tests.md（T3 时限按蓝图纠正） |
| T11–T12 | 同文件追加 |
| F13–F18 P1 | coproduction 加深、sensitive-topics-tree、form-field-drafts、promo-compliance-check、common-errors、evidence-grades |
| F19–F23 P2 | class2-3、provincial-windows 样本、VR 须知全文、production-license、policy-watch |
| T13–T18 | smoke-tests.md |

## 明确覆盖的过时 PRD 行

| PRD 位置 | 包内执行 |
|----------|----------|
| §6.2 一类微短剧走网标 | 一类走《微短剧发行许可证》 |
| §5.3 / §6.2 院转网「无需网标须展示龙标号」 | T8 降级，不写硬规则 |
| T3「50 工作日」 | 五十日（令文） |

## 已知残缺（不阻塞本版）

- F20 仅上海细表 + 北京/浙江/广东样本，不是 31 省全表
- F19 二类/三类无各省简化材料清单（第 16 号施行日前）
- F15 系统 HTML 逐字段名以「申报指南」当时页为准，操作手册未枚举全部控件名
