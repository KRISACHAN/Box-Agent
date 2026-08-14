---
name: browser-use
description: Route browser tasks by user intent between a visible browser with the user's current tabs and login state, and managed browser automation that can be switched between headed and headless with hot reload. Use for opening URLs or websites, current-page interaction, logged-in or intranet tasks, forms, screenshots, scraping, crawling, web testing, visible or background browsing, headed/headless requests, and browser runtime configuration. Public web retrieval, crawling, and bulk collection should prefer managed automation without touching the user's real browser; forms that the user wants to review, take over, or submit personally should prefer the visible real browser from the start.
keywords:
  - 浏览器
  - 网页
  - 网站
  - 页面
  - 标签页
  - 当前页
  - 打开网址
  - 打开链接
  - 系统浏览器
  - 默认浏览器
  - 真实浏览器
  - 可见浏览器
  - 有头浏览器
  - 带头浏览器
  - 无头浏览器
  - 登录态
  - Cookie
  - 内网
  - 网页抓取
  - 网页自动化
  - 公开检索
  - 批量抓取
  - 爬虫
  - 表单
  - 人工接管
  - 让我检查
  - 我最后提交
  - browser
  - current tab
  - headed
  - headless
  - playwright
  - chrome
  - scrape
  - crawl
---

# Browser Use

按用户想获得的体验选择能力，不要求用户理解内部组件。两种浏览器可在同一 turn 分步骤使用，但 snapshot/ref 不得跨通道复用。

## 选择浏览器

- 高优先级：明确的公开网页检索、爬取、批量抓取或采集始终优先使用受管浏览器自动化，不要打开或操作用户的真实浏览器，即使真实浏览器工具当前可见。
- 高优先级：用户要求“填好让我检查”、亲自接管或最后提交时，从任务开始就优先使用用户的可见真实浏览器，不要在受管浏览器中代填后再声称用户可以接管。填写完成后保留页面并停在提交之前；真实浏览器未连接时引导用户连接，不要静默回退。
- 当前页、现有登录/Cookie/扩展/内网、系统或默认浏览器、需要用户看见或接管：使用用户正在使用的可见浏览器。
- 公开网页、后台抓取、批量采集、测试、截图、DOM/网络检查：使用受管浏览器自动化。
- “有头/无头”只描述受管浏览器是否显示窗口，不代表继承用户 Chrome 登录态。不要把两者视为同义词，也不要仅凭“看到窗口”断言使用了真实浏览器；需要现有登录态时仍使用可见真实浏览器。
- 意图确实不清时只问一次：“我可以用独立浏览器自动完成，也可以操作你当前登录的浏览器。你希望哪一种？”

## 切换受管浏览器窗口

仅当用户关心是否出现窗口或明确要求有头/无头时修改配置；普通浏览任务不得静默切换。

1. 调用 `mcp_config(action="inspect_browser")` 查看当前 `mode`、`isolated`、`profile` 和 `enabled`。
2. 当前模式符合要求时直接使用现有 Playwright 工具。
3. 模式不符且用户已明确要求切换时调用：
   - 有头/带头/显示窗口：`mcp_config(action="update", name="playwright", config={"args_remove":["--headless"]})`
   - 无头/后台/不显示窗口：`mcp_config(action="update", name="playwright", config={"args_add":["--headless"]})`
4. 该操作只增删现有 `playwright` 的 `--headless`，保留 `--isolated`、浏览器路径、环境变量和超时；宿主监听配置并热重连。禁止新增 `playwright-headed`、`playwright-headless` 等重复实例。
5. 修改后重新 inspect，并发起一次新的浏览器操作。配置写入成功不等于新进程已经切换；只有热重连成功及实际窗口/运行结果才能证明生效。没有宿主热重连时提示用户重启 Box-Agent。

受管配置可能在 Officev3 重启或重新同步后恢复默认。即使 `mode=headed`，只要 `isolated=true`，它仍是独立的受管 Chromium，不继承用户 Chrome 登录态。

## 工具与安全

- 可见真实浏览器用于打开 URL、读取当前页、snapshot、点击、填写和经确认的提交。
- 受管浏览器用于导航、snapshot、点击、填写、截图、脚本和网络检查；不要用 Gateway 内部的 Playwright fallback 替代 standalone Playwright 工具。
- 依赖当前页或登录态而真实浏览器未连接时，引导用户连接，不能静默换成独立浏览器并假装状态仍在。
- 默认对用户只说“独立浏览器”“你当前登录的浏览器”“显示/隐藏窗口”；除非用户询问架构，不暴露 MCP 和内部组件名。
- 填写不等于提交。发送、发布、购买、删除等外部副作用操作必须按现有策略获得明确确认。
