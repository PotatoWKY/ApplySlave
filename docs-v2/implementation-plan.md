# 实施计划 v2

> 分阶段交付：CLI 可用 → FastAPI 服务 → Tauri Desktop App → 打包发布

---

## 总体时间轴

```
┌──────────────────────────────────────────────────────────┐
│  阶段 1: Python Monorepo + CLI（5-6 周）                  │
│  目标：命令行能跑通完整投递流程                             │
├──────────────────────────────────────────────────────────┤
│  阶段 2: FastAPI 服务层（1-2 周）                          │
│  目标：把 CLI 逻辑暴露为 HTTP API                          │
├──────────────────────────────────────────────────────────┤
│  阶段 3: Tauri Desktop App（3-4 周）                      │
│  目标：TypeScript + React UI，跨平台                      │
├──────────────────────────────────────────────────────────┤
│  阶段 4: 打包和发布（2-3 周）                              │
│  目标：三平台一键安装                                      │
└──────────────────────────────────────────────────────────┘

合计：11-15 周（约 3-4 个月）
```

---

## 阶段 1：Python Monorepo + CLI

### Phase 1.0 Monorepo 脚手架（2 天）

**目标**：`uv sync` 能成功安装所有 workspace packages，`uv run applyslave --help` 显示 CLI。

**任务**：
- 初始化 uv workspace（根 `pyproject.toml`）
- 创建所有 package 目录骨架
  - `packages/shared`
  - `packages/profile-store`
  - `packages/job-discovery`
  - `packages/applicator`
  - `packages/orchestrator`
  - `apps/cli`（临时 CLI，后面会改成 FastAPI）
- 每个 package 的 `pyproject.toml` 配置好 workspace 依赖
- 配置 ruff、pyright、pytest

**验收**：
- `uv sync` 成功
- `uv run applyslave --help` 返回帮助信息
- `uv run pytest` 能跑起来

---

### Phase 1.1 shared 包（1 天）

**目标**：定义所有 package 共用的数据模型和接口。

**产出**：
- `shared/models.py`：`UserProfile`、`Education`、`Experience`、`JobListing`、`SearchQuery`、`Action`、`ApplyResult`、`ApplicationStatus` enum
- `shared/protocols.py`：`JobSource`、`FormFiller`、`LLMClient`、`Storage` Protocol 定义
- `shared/constants.py`：枚举常量

**验收**：
- 其他 package 能 `from shared.models import UserProfile`
- `pyright` 类型检查通过

---

### Phase 1.2 profile-store 包（3 天）

**目标**：能存储 / 读取用户简历和基本信息，支持从 PDF 解析简历。

**任务**：

#### Day 1: SQLite 存储
- `profile_store/storage.py`：SQLite 封装
- `profile_store/profile.py`：`ProfileStore.save()` / `load()`

#### Day 2-3: PDF 解析
- `profile_store/resume_parser.py`：用 `pdfplumber` 提取文本 + 规则识别基础字段 + LLM 提取复杂字段
- 提供 `ResumeParser.parse(pdf_path) -> UserProfile` 接口

**验收**：
- 示例简历 PDF 能解析出 name/email/phone
- 单元测试覆盖核心 CRUD

---

### Phase 1.3 job-discovery 包（4 天）

**目标**：从 Greenhouse / Lever / Ashby / Workable 四个 ATS 公开 API 获取职位。

**任务**：

#### Day 1: 共享基础
- `sources/base.py`：HTTP 客户端（httpx）、重试、限流
- 抽象方法定义

#### Day 2: Greenhouse
- API: `https://boards-api.greenhouse.io/v1/boards/{company}/jobs`
- 实现 `list_jobs()` 返回 `list[JobListing]`

#### Day 3: Lever + Ashby
- Lever: `https://api.lever.co/v0/postings/{company}`
- Ashby: `https://api.ashbyhq.com/posting-api/job-board/{company}`

#### Day 4: Workable + Aggregator
- Workable public API
- `aggregator.py`：并行调用、去重、排序
- `sources/companies.yaml`：要搜索的公司列表（初期 50-100 家 tech 公司）

**验收**：
- `applyslave discover --keywords "engineer" --location "remote"` 返回真实职位
- 每个 source 单元测试（mock HTTP）+ 集成测试（真实 API）

---

### Phase 1.4 applicator/browser（5 天）

**目标**：打开任意 URL，提取表单字段，执行操作。

可以参考或迁移 v1 的实现。

**任务**：
- `browser/manager.py`：BrowserManager
- `browser/dom_extractor.py`：DOMExtractor（最核心）
- `browser/action_executor.py`：ActionExecutor

**验收**：
- 能提取 Greenhouse / Lever / Ashby 申请页面的所有表单字段
- 能执行 fill、click、select、upload 操作

---

### Phase 1.5 applicator/llm（3 天）

**目标**：集成 llama-cpp-python，本地 LLM 推理。

**任务**：

#### Day 1: llama-cpp-python 基础
- `llm/model_manager.py`：下载 GGUF 模型到应用数据目录
- 模型：[Qwen/Qwen2.5-7B-Instruct-GGUF](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF) Q4_K_M 量化（~4.7GB）

#### Day 2: LLM client
- `llm/client.py`：封装 `Llama` 类
- `chat(messages) -> str` / `json_chat(messages, schema) -> dict`
- macOS Metal GPU、Windows CUDA、Linux 通用

#### Day 3: Prompt builder
- `llm/prompt_builder.py`：form filling 场景 prompt 模板
- Few-shot 示例
- 强制 JSON 输出

**验收**：
- `uv run applyslave llm-test`：输入 prompt 返回 JSON
- GPU 加速生效

---

### Phase 1.6 applicator/form-filler（4 天）

**目标**：整合 browser + llm，通用页面分析 + 表单填写。

**任务**：
- `form_filler/page_analyzer.py`
- `form_filler/form_mapper.py`
- `form_filler/filler.py`

**验收**：
- 端到端：给 Greenhouse URL + profile，自动填完到 confirmation 页
- 至少 3 个 ATS 平台支持

---

### Phase 1.7 orchestrator（3 天）

**目标**：批量投递状态管理、重试、记录。

**任务**：
- `orchestrator/state_machine.py`
- `orchestrator/job_queue.py`
- `orchestrator/retry_handler.py`
- `orchestrator/result_logger.py`

---

### Phase 1.8 CLI + 集成联调（4 天）

**命令**：
```bash
applyslave profile import --pdf resume.pdf
applyslave profile show
applyslave discover --keywords engineer ...
applyslave apply --batch latest
applyslave status
```

**验收**：
- 从零开始：导入 PDF → 搜索 → 投递 → 结果，全流程打通
- 至少成功投递 3 个不同 ATS 的真实职位

---

## 阶段 2：FastAPI 服务层（1-2 周）

### Phase 2.1 services/backend 骨架（2 天）

- 创建 `services/backend` package
- FastAPI + uvicorn
- 路由骨架（routers/profile.py、discovery.py、applications.py、system.py）

### Phase 2.2 把 CLI 改造成 HTTP API（3 天）

按 [api-contract.md](./api-contract.md) 实现每个路由。业务逻辑直接调 packages。

### Phase 2.3 WebSocket 实时推送（2 天）

- `/api/ws` endpoint
- orchestrator 关键事件触发 broadcast
- `asyncio.Queue` 事件分发

### Phase 2.4 集成测试（2 天）

- Pytest + httpx 测试 HTTP
- WebSocket 事件推送测试

---

## 阶段 3：Tauri Desktop App（3-4 周）

### Phase 3.1 Tauri + React 项目初始化（2 天）

**任务**：
- `pnpm create tauri-app` 创建 `apps/applyslave-desktop`
- 选择 React + TypeScript + Vite 模板
- 配置 `tauri.conf.json`
- 安装 Tailwind CSS + shadcn/ui
- 安装 Zustand 或 TanStack Query
- 配置 ESLint + Prettier

**验收**：
- `pnpm tauri dev` 启动空白窗口
- 热重载生效

### Phase 3.2 Tauri Rust 侧：后端生命周期（2 天）

**任务**：
- `src-tauri/src/python_process.rs`：启动 / 停止 Python 子进程
- `src-tauri/src/main.rs`：setup + 退出时清理
- `#[tauri::command] backend_port()` 暴露端口给前端
- 开发模式下和打包模式下路径处理

**验收**：
- Tauri 启动时能成功拉起 Python 后端
- 窗口关闭时后端干净退出

### Phase 3.3 前端 Network 层（1 天）

**任务**：
- `services/backend.ts`：HTTP 客户端封装（fetch + 错误处理）
- `services/websocket.ts`：WebSocket 封装 + 自动重连
- `types/api.ts`：和 Python 对应的 TypeScript 类型
- TanStack Query 配置（数据获取 + 缓存）

### Phase 3.4 Profile UI（3 天）

**组件**：
- 拖拽上传简历（react-dropzone）
- PDF 解析结果展示 + 编辑表单
- 多份简历管理
- 表单校验（zod）

### Phase 3.5 Discovery UI（3 天）

**组件**：
- 搜索偏好表单（关键词、地点、filter）
- 结果列表（virtualized for performance）
- 多选 + 批量操作
- 排序和二次筛选

### Phase 3.6 Applications UI（4 天）

**组件**：
- 批量投递启动按钮
- 实时进度列表（通过 WebSocket）
- 每项投递的详情页（步骤、截图、LLM 决策日志）
- CAPTCHA 人工介入弹窗

### Phase 3.7 Onboarding + Settings（2 天）

**组件**：
- 首次启动：检测模型 → 下载进度条
- Settings 页：profile 管理、清除数据、版本信息
- About 对话框

### Phase 3.8 UI polish（2 天）

**任务**：
- Dark mode（Tailwind 的 dark: 前缀）
- Keyboard shortcuts（Ctrl+K 命令面板）
- 桌面通知（Tauri notification plugin）
- 错误边界和优雅降级

---

## 阶段 4：打包和发布（2-3 周）

### Phase 4.1 资源准备脚本（3 天）

按 [packaging-strategy.md](./packaging-strategy.md) 实现：
- `packaging/prepare-resources.sh`（macOS / Linux）
- `packaging/prepare-resources.ps1`（Windows）
- 下载 python-build-standalone
- 安装 Python 依赖到 `--target`
- 下载 Playwright Chromium

### Phase 4.2 Python 后端打包验证（2 天）

**任务**：
- 从 bundle 启动 Python 后端，确认所有依赖能找到
- Playwright 的 Chromium 路径通过 `PLAYWRIGHT_BROWSERS_PATH` 正确解析
- LLM 模型加载路径通过 `APPLYSLAVE_DATA_DIR`

**三平台都测**。

### Phase 4.3 Tauri 资源配置（2 天）

**任务**：
- `tauri.conf.json` 的 `bundle.resources` 包含 Python 运行时、依赖、Chromium
- 测试 dev 模式（从 workspace 读取）vs prod 模式（从 Resources/ 读取）的路径逻辑
- 确认最终 `.app` / `.exe` / `.AppImage` 体积合理

### Phase 4.4 代码签名 + 公证（3 天）

- macOS: 申请 Apple Developer Program，配置 `signingIdentity`，自动公证
- Windows: 代码签名证书或 Azure Trusted Signing
- Linux: 不需要签名

**策略**：先发内测版（不签名），让用户手动绕过；产品稳定后再买签名。

### Phase 4.5 Tauri Updater 配置（2 天）

- `tauri signer generate` 生成密钥对
- `tauri.conf.json` 配置 updater endpoint
- 前端集成 `@tauri-apps/plugin-updater`
- 后端：GitHub Releases 上放 `latest.json`

### Phase 4.6 GitHub Actions CI（2 天）

- `.github/workflows/release.yml` 三平台 matrix build
- Secrets 配置（Apple 证书、签名密钥）
- 一次 `git push --tags` 产出三平台包

### Phase 4.7 QA + bug 修复（5 天）

按 [packaging-strategy.md 测试清单](./packaging-strategy.md#十一测试清单) 逐项过。

---

## 风险缓冲

| 风险 | 缓冲 |
|------|------|
| llama-cpp-python 在三个平台编译 / 加载问题 | +3 天 |
| PDF 解析准确率不够 | +2 天（fallback 到 LLM extraction） |
| 不同 ATS 页面多样性超预期 | +5 天 |
| Tauri Rust 子进程跨平台差异 | +2 天 |
| 代码签名 / 公证卡壳 | +3 天 |
| WebView 兼容性（macOS Safari vs Windows Chromium） | +2 天 |

**含缓冲总预估：14-18 周（3.5-4.5 个月）**

---

## MVP 里程碑

分阶段交付：

### MVP 1（4-5 周）：Python CLI 可用
- 完成阶段 1 全部
- 命令行工具能跑
- 开发者自己能用，也能展示给 reddit/HN 社区

### MVP 2（7-8 周）：无 UI 的 HTTP 服务
- 完成阶段 1 + 2
- 前端可以随便选（不一定非 Tauri），测试容易
- 可作为服务集成

### MVP 3（11-12 周）：完整 Tauri app 但不签名
- 完成阶段 1-3 + 阶段 4 的打包（跳过签名公证）
- 内测版，三平台都能跑
- 用户需要手动绕过系统安全检查

### Final（14-18 周）：正式发布
- 全部完成，签名、公证、CI/CD
- `.dmg` / `.exe` / `.AppImage` 一键安装
- Tauri Updater 自动更新

---

## 学习路径建议（如果之前没写过 TypeScript / React）

假设你有 C++ 和 Python 背景但没 JS 经验，不用一次性学完再开工，边做边学：

| 阶段 | 需要学什么 | 时长 |
|------|----------|------|
| 阶段 1-2（纯 Python） | — | 0 |
| 阶段 3.1 项目初始化 | TypeScript 基础语法（类型、接口、enum） | 3-5 天 |
| 阶段 3.3 Network 层 | async/await、fetch、Promise | 1-2 天 |
| 阶段 3.4 Profile UI | React 基础（组件、hook、state） | 5-7 天 |
| 阶段 3.5+ 其他 UI | React 进阶（useEffect、custom hooks、context） | 边做边学 |
| 阶段 3.6 Applications UI | TanStack Query 或 Zustand 状态管理 | 2-3 天 |
| 阶段 4 打包 | Tauri CLI、一点 Rust 语法（抄文档） | 2-3 天 |

**总学习时间：2-3 周**（夹在阶段 3 里，不是纯学习）。

推荐资源：
- TypeScript: [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/)
- React: [React 官方新教程](https://react.dev/learn)
- Tauri: [Tauri 官方文档](https://tauri.app/start/)
