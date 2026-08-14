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

Choose the capability by the experience the user expects. Do not require the user to understand internal components. Both browser types may be used in separate steps of one turn, but never reuse a snapshot or ref across them.

## Choose the browser

- High priority: For explicit public-web search, retrieval, crawling, or bulk collection (for example, “公开检索”, “爬取”, or “批量抓取”), prefer managed browser automation. Do not open or manipulate the user's real browser even when its tools are visible.
- High priority: If the user says “填好让我检查”, wants to take over, or wants to submit personally, prefer the user's visible real browser from the start. Do not fill the form in a managed browser and then claim the user can take over. Leave the page open and stop before submission. If the real browser is not connected, guide the user to connect it instead of silently falling back.
- Use the user's visible browser for the current page, existing login state, cookies, extensions, intranet access, system/default-browser requests, or any task the user must see or take over.
- Use managed browser automation for public pages, background extraction, bulk collection, testing, screenshots, DOM inspection, and network inspection.
- Treat headed/headless only as the managed browser's window visibility. It does not inherit the user's Chrome login state. Do not treat a visible managed window as proof that the real browser is in use.
- When the intent is genuinely ambiguous, ask once in the user's language whether they want an independent automated browser or their currently logged-in browser.

## Switch the managed browser window

Change this configuration only when the user cares whether a window appears or explicitly requests headed/headless mode. Never switch it silently for an ordinary browser task.

1. Call `mcp_config(action="inspect_browser")` and inspect `mode`, `isolated`, `profile`, and `enabled`.
2. If the current mode already matches the request, use the existing Playwright tools.
3. If the mode does not match and the user explicitly requested a switch, call:
   - Headed / visible window (`有头`, `带头`): `mcp_config(action="update", name="playwright", config={"args_remove":["--headless"]})`
   - Headless / background (`无头`, `后台`): `mcp_config(action="update", name="playwright", config={"args_add":["--headless"]})`
4. Change only `--headless` on the existing `playwright` entry. Preserve `--isolated`, the executable path, environment variables, and timeouts. Let the host watch the file and hot-reconnect. Never add duplicate instances such as `playwright-headed` or `playwright-headless`.
5. Inspect again and start a new browser operation. A successful file write does not prove that the new process is active; only a successful hot reconnect and the actual window/runtime result prove the switch. If no host performs hot reconnects, tell the user to restart Box-Agent.

Officev3 may restore the managed configuration to its default after restart or resynchronization. Even with `mode=headed`, `isolated=true` still means an independent managed Chromium that does not inherit the user's Chrome login state.

## Tools and safety

- Use the visible real browser to open URLs, read the current page, take snapshots, click, fill, and perform confirmed submissions.
- Use the managed browser for navigation, snapshots, clicks, filling, screenshots, scripts, and network inspection. Do not substitute the Gateway's internal Playwright fallback for standalone Playwright tools.
- When a task depends on the current page or login state and the real browser is disconnected, guide the user to connect it. Never silently switch to an independent browser and pretend the state remains available.
- By default, describe the choices to the user as “independent browser”, “your currently logged-in browser”, and “show/hide the window”. Do not expose MCP or internal component names unless the user asks about the architecture.
- Filling is not submitting. Sending, publishing, purchasing, deleting, and other external side effects require explicit confirmation under the existing policy.
