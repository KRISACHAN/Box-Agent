# Understand Anything 代码图谱

Box-Agent 使用 Understand Anything 作为本地架构索引，用于代码导航、归属追踪、
依赖检查和新成员引导。图谱可以加快定位，但源码、聚焦测试、日志和运行探针仍然是
事实来源。

## 仓库范围

共享分析范围由
[`../.understand-anything/.understandignore`](../.understand-anything/.understandignore)
定义。当前配置包含核心运行时、ACP 适配层、工具、配置、示例和文档；同时排除内置
skill 资源、测试、workspace、虚拟环境和生成产物，使图谱聚焦产品架构。

Git 中只应提交以下共享文件：

- `.understand-anything/.understandignore`
- `.understand-anything/config.json`

不要提交 `knowledge-graph.json`、`meta.json`、fingerprint、intermediate、trash、
dashboard token 或缓存。这些都是本地生成产物，已经由 `.gitignore` 忽略。

## 刷新流程

1. 调整图谱范围前，先检查 `.understand-anything/.understandignore`。
2. 图谱缺失、明显过期或分析范围变化时，在已安装 Understand Anything plugin 的
   客户端中运行 `/understand --full --language zh`；常规增量刷新使用
   `/understand`。
3. 确认验证结果没有 critical issue，并且每个已分析的文件级节点都只属于一个
   架构层。
4. 在本地保留 `scan-result.json` 和 fingerprint 基线，让后续增量刷新可以高效比较
   结构变化。
5. 启动 dashboard 后，应打开 plugin 输出的带 token URL；仅访问本地服务裸地址
   无法通过访问校验。

入口文件、子系统边界、共享工具、ACP 协议、运行时打包或需要进入引导路径的文档
发生变化后，应刷新图谱。仅源码变化不需要提交生成图谱文件。

## 验证与 Review

先用图谱定位可能相关的文件和关系，再通过源码阅读、`rg`、聚焦的
`uv run pytest`、日志或运行探针验证重要结论。如果图谱元数据与当前提交不一致，
在刷新完成前应明确标记图谱已过期。

仅刷新本地图谱属于维护操作。如果共享范围或语言配置发生变化，应在 PR 的 Task、
Proof、Risk 中包含相关配置 diff，并说明预期覆盖范围。
