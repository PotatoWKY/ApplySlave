# ApplySlave Docs v2

> 架构第二版：从 LinkedIn 爬虫 pivot 到 ATS API + 跨平台桌面 App（Tauri）

---

## 为什么有 v2

v1（`docs/`）设计了一个 Python CLI 工具，以 LinkedIn 为主入口。调研和原型验证后发现几个根本性问题：

1. **LinkedIn 反 bot 检测激进** — 账号限制、CAPTCHA、甚至永久封号的风险真实存在
2. **LinkedIn ToS 明确禁止自动化** — 合规风险
3. **Easy Apply 面试转化率只有 2-3%** — 公司官网直接申请能到 8-12%
4. **Python CLI 不是最终用户想要的** — 大多数人不会用命令行

v2 基于这些认知做了根本性调整：

| 维度 | v1 | v2 |
|------|----|----|
| 入口 | LinkedIn 爬虫 | ATS 公开 API（Greenhouse / Lever / Ashby / Workable） |
| 法律风险 | 违反 LinkedIn ToS | 合规，使用公开 API |
| 封号风险 | 高 | 零 |
| 用户接口 | Python CLI | 跨平台桌面 App（Tauri + React + TypeScript） |
| 平台支持 | macOS（理论上） | macOS + Windows + Linux |
| 分发方式 | pip install | `.dmg` / `.exe` / `.AppImage` 一键安装 |
| 代码结构 | 单包 Python | monorepo（多个独立 packages） |

## 前端技术栈选择：为什么是 Tauri

简要说明（详见 [architecture.md](./architecture.md)）：

- **跨平台**：一套代码产 macOS、Windows、Linux 三种包。Swift 只能做 macOS。
- **性能**：最终产物 10-20MB（vs Electron 150MB+），内存 30-40MB（vs Electron 150MB+）
- **用户体验**：不像 Electron app 那样动不动卡顿 / 崩溃（VS Code、Kiro 的痛点）
- **学习价值**：TypeScript + React 是全行业最通用的前端技能，就业面最广
- **开发速度**：比 Swift 原生快，热重载改一行刷新立即可见

## 文档索引

- [architecture.md](./architecture.md) — 整体架构、模块划分、依赖关系
- [competitive-analysis.md](./competitive-analysis.md) — 竞品对标（基于新认知更新）
- [packaging-strategy.md](./packaging-strategy.md) — 一键打包方案（Python + Chromium + LLM 模型）
- [implementation-plan.md](./implementation-plan.md) — 分阶段开发计划
- [api-contract.md](./api-contract.md) — 前端和 Python 后端之间的 HTTP API 合约

## 开发状态

- ✅ v1 脚手架和核心模块已完成（`src/` 目录）
- 🔄 v2 架构设计中
- ⏳ v2 重构未开始
