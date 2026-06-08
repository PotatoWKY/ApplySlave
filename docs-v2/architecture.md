# Hamster v2 架构设计

## 一、最终形态

用户体验目标：下载 `.dmg`（macOS）/ `.exe`（Windows）/ `.AppImage`（Linux） → 拖到 Applications → 双击 → 首次启动下载 AI 模型 → 开始投递。

全程不需要装 Python、不需要装 Ollama、不需要打开终端。**一套代码覆盖三个平台**。

## 二、整体架构

```
┌─────────────────────────────────────────────────────────┐
│  Hamster.app / .exe / .AppImage（~500MB）             │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  前端（TypeScript + React + Tauri）              │   │
│  │                                                 │   │
│  │  ┌─────────────────────────────────────────┐   │   │
│  │  │  React UI                                │   │   │
│  │  │  - 简历上传 / 编辑                        │   │   │
│  │  │  - 搜索偏好配置                           │   │   │
│  │  │  - 投递进度实时展示                       │   │   │
│  │  └────────────┬────────────────────────────┘   │   │
│  │               │                                 │   │
│  │  ┌────────────▼────────────────────────────┐   │   │
│  │  │  Tauri Rust Shell（系统 WebView）        │   │   │
│  │  │  - 管理窗口                              │   │   │
│  │  │  - 启动/停止 Python 子进程                │   │   │
│  │  │  - 原生系统集成（菜单、托盘、通知）         │   │   │
│  │  └─────────────────────────────────────────┘   │   │
│  └───────────────┬─────────────────────────────────┘   │
│                  │ HTTP + WebSocket (localhost:8765)   │
│  ┌───────────────▼─────────────────────────────────┐   │
│  │  Python 后端（FastAPI，随 app 启动 / 退出）       │   │
│  │                                                 │   │
│  │  ┌─────────────────────────────────────┐       │   │
│  │  │  API 层（FastAPI routers）           │       │   │
│  │  └─────────────────────────────────────┘       │   │
│  │                                                 │   │
│  │  ┌──────────────────────────────────────┐      │   │
│  │  │  业务层（packages/）                  │      │   │
│  │  │  - profile-store  简历和用户信息      │      │   │
│  │  │  - job-discovery  找职位返回 URL      │      │   │
│  │  │  - applicator     填表提交（最大）    │      │   │
│  │  │  - orchestrator   状态机 / 任务队列   │      │   │
│  │  │  - shared         通用数据类型和接口  │      │   │
│  │  └──────────────────────────────────────┘      │   │
│  │                                                 │   │
│  │  ┌─────────────────────────────────────┐       │   │
│  │  │  依赖：Chromium（打包进 bundle）      │       │   │
│  │  │  依赖：LLM 模型（首次启动下载）       │       │   │
│  │  └─────────────────────────────────────┘       │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘

本地存储：
  macOS:   ~/Library/Application Support/Hamster/
  Windows: %APPDATA%/Hamster/
  Linux:   ~/.config/Hamster/

├── profile.db            SQLite（简历、偏好、投递历史）
├── resumes/              简历 PDF 文件
└── models/               LLM 模型文件（~4GB）
```

## 三、技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 前端 UI | **TypeScript + React** | 全行业最通用的前端栈 |
| 桌面壳子 | **Tauri 2.x** | Rust 核心 + 系统 WebView，跨三平台 |
| 前端构建 | **Vite** | 比 webpack 快，Tauri 默认推荐 |
| UI 组件库 | **shadcn/ui + Tailwind CSS** | 现代、可定制、不锁死 |
| 状态管理 | **Zustand** 或 **TanStack Query** | 轻量、不搞 Redux 那套 |
| Python 运行时 | **python-build-standalone** | 嵌入式 Python，Astral 出品 |
| 后端框架 | **FastAPI + uvicorn** | Python 最主流的异步 API 框架 |
| 异步 | asyncio | Python 原生 |
| 浏览器自动化 | **Playwright** | 最强的自动化库 |
| 本地 LLM | **llama-cpp-python** + Qwen2.5-7B (GGUF Q4) | C++ 内核，Metal GPU 加速 |
| 存储 | **SQLite + Keychain / DPAPI** | 跨平台安全存储 |
| Python 包管理 | **uv workspace** | Astral 出品，比 pip 快 100 倍 |
| 自动更新 | **Tauri Updater** | 官方内置，不用 Sparkle |
| 打包 | `pnpm tauri build` | 一条命令产三平台包 |

## 四、模块划分

### 4.1 前端（`apps/hamster-desktop/`）

Tauri 项目，TypeScript + React。

```
apps/hamster-desktop/
├── src/                      # 前端源码（TypeScript + React）
│   ├── main.tsx              # 入口
│   ├── App.tsx               # 根组件
│   ├── pages/
│   │   ├── Onboarding.tsx    # 首次启动引导（下载模型）
│   │   ├── Profile.tsx       # 简历上传与编辑
│   │   ├── Discovery.tsx     # 搜索偏好配置
│   │   ├── Applications.tsx  # 投递进度与结果
│   │   └── Settings.tsx
│   ├── components/           # 通用 UI 组件
│   ├── services/
│   │   ├── backend.ts        # 封装 HTTP 调用 Python 后端
│   │   └── websocket.ts      # WebSocket 封装
│   ├── stores/               # Zustand 状态管理
│   └── types/                # 和 Python 端对应的 TypeScript 类型
├── src-tauri/                # Tauri Rust 侧
│   ├── src/
│   │   ├── main.rs           # 入口（基本抄文档）
│   │   ├── python_process.rs # 启动 / 管理 Python 子进程
│   │   └── paths.rs          # 跨平台路径（macOS/Win/Linux）
│   ├── tauri.conf.json       # 打包配置
│   └── Cargo.toml            # Rust 依赖
├── package.json
├── tsconfig.json
└── vite.config.ts
```

**职责分工**：
- React / TypeScript：所有 UI、用户交互、发 HTTP 请求
- Rust（通过 Tauri）：启动 Python 子进程、管理窗口、原生文件对话框、系统通知、打包

**Rust 代码量估算**：整个项目 Rust 代码不超过 300 行，主要是：
- 启动 / 停止 Python 子进程
- `tauri.conf.json` 配置
- 一些 `#[tauri::command]` 暴露给前端调用

**不做**：
- 任何业务逻辑（都在 Python 后端）
- 直接操作浏览器或调用 LLM

### 4.2 Python 后端（monorepo 模块）

```
packages/
├── shared/           ← 所有 package 共用的数据类型和接口定义
├── profile-store/    ← 简历存储和解析
├── job-discovery/    ← 职位搜索和 URL 收集
├── applicator/       ← 浏览器自动化 + LLM 填表（核心）
└── orchestrator/     ← 流程编排

services/
└── backend/          ← FastAPI HTTP 服务，暴露给前端调用
```

#### shared

纯定义，所有人依赖它，它不依赖任何人。

```
shared/
└── src/shared/
    ├── models.py       # UserProfile, JobListing, Action, ApplyResult 等 dataclass
    ├── protocols.py    # JobSource, FormFiller 等接口定义
    └── constants.py    # 枚举、常量
```

#### profile-store

用户简历和偏好的持久化。

```
profile-store/
└── src/profile_store/
    ├── storage.py       # SQLite 封装
    ├── resume_parser.py # PDF → 结构化数据（pdfplumber + LLM）
    └── profile.py       # UserProfile CRUD
```

依赖：`shared`

#### job-discovery

从多个 ATS 公开 API 收集职位，返回去重后的 URL 列表。

```
job-discovery/
└── src/job_discovery/
    ├── aggregator.py      # 并行调用多个 source，合并结果
    ├── sources/
    │   ├── greenhouse.py  # Greenhouse Job Board API
    │   ├── lever.py       # Lever Postings API
    │   ├── ashby.py       # Ashby Posting API
    │   ├── workable.py    # Workable public API
    │   └── linkedin.py    # 可选，浏览模式（不投递）
    └── filters.py         # 关键词、地点、远程等筛选
```

依赖：`shared`

每个 source 实现 `shared.protocols.JobSource` 接口。

#### applicator（最大的模块）

拿到 URL 后完成申请的全部工作。

```
applicator/
└── src/applicator/
    ├── browser/
    │   ├── manager.py          # BrowserManager（Playwright 封装）
    │   ├── dom_extractor.py    # 提取可交互元素
    │   └── action_executor.py  # 执行填写、点击等操作
    ├── llm/
    │   ├── model_manager.py    # 模型下载 / 加载 / 缓存
    │   ├── client.py           # llama-cpp-python 封装
    │   └── prompt_builder.py   # Prompt 模板
    ├── form_filler/
    │   ├── page_analyzer.py    # 识别页面类型
    │   ├── form_mapper.py      # 字段语义匹配
    │   └── filler.py           # 组装操作指令
    └── engine.py               # 对外暴露的主接口
```

依赖：`shared`

#### orchestrator

```
orchestrator/
└── src/orchestrator/
    ├── state_machine.py   # 投递流程状态机
    ├── job_queue.py       # 任务队列
    ├── retry_handler.py   # 重试逻辑
    └── result_logger.py   # 结果记录
```

依赖：`shared`

#### services/backend

FastAPI HTTP 服务，把上面所有 package 的能力暴露给前端。

```
services/backend/
└── src/backend/
    ├── main.py            # FastAPI 入口
    ├── routers/
    │   ├── profile.py     # /api/profile 相关
    │   ├── discovery.py   # /api/jobs 相关
    │   ├── applications.py # /api/applications 相关
    │   └── system.py      # /api/health, /api/model 相关
    ├── websocket.py       # 实时进度推送
    └── dependencies.py    # 依赖注入
```

依赖：所有 packages

## 五、模块依赖图

```
                   ┌────────────┐
                   │   shared   │  (模型、协议定义)
                   └──────┬─────┘
                          │
         ┌────────────────┼────────────────┐
         │                │                │
   ┌─────▼────┐    ┌──────▼───────┐ ┌─────▼────────┐
   │ profile- │    │ job-discovery│ │  applicator  │
   │  store   │    │              │ │              │
   └─────┬────┘    └──────┬───────┘ └──────┬───────┘
         │                │                │
         └────────────────┼────────────────┘
                          │
                   ┌──────▼───────┐
                   │ orchestrator │
                   └──────┬───────┘
                          │
                  ┌───────▼──────────┐
                  │ services/backend │
                  │   (FastAPI)      │
                  └───────┬──────────┘
                          │ HTTP / WebSocket (localhost:8765)
                          │
                  ┌───────▼──────────────┐
                  │ Tauri Desktop App    │
                  │ (TypeScript + React) │
                  └──────────────────────┘
```

核心原则：**依赖单向，永不循环**。

## 六、数据流

### 6.1 新用户首次使用

```
1. 双击 Hamster.app（或 .exe）
   → Tauri Rust shell 启动，读取系统 WebView
   → Rust 启动 Python 后端子进程（localhost:8765）
   → React 加载，检测本地是否有 LLM 模型
   → 没有 → 显示 Onboarding 页面

2. 用户点"下载模型"
   → React 调 POST /api/model/download
   → Python 后端下载 Qwen2.5-7B GGUF 到 Application Support 目录
   → WebSocket 推送进度给 React

3. 模型就绪 → 进入 Profile 页面
4. 用户上传简历 PDF + 填写可选信息
   → React 调 POST /api/profile
   → profile-store 解析 PDF + 存 SQLite

5. 用户设置搜索偏好（角色、地点、公司类型）
   → React 调 POST /api/jobs/discover
   → job-discovery 并行调 Greenhouse / Lever / Ashby / Workable API
   → 返回去重后的职位 URL 列表

6. 用户选择要投的职位 → 点"开始投递"
   → React 调 POST /api/applications
   → orchestrator 把 URL 加入队列
   → applicator 逐个打开页面、提取 DOM、LLM 匹配字段、填写、提交
   → WebSocket 推送每个职位的进度和结果给 React

7. 所有职位投递完毕 → 展示结果统计
```

### 6.2 前端 ↔ Python 通信

**HTTP 请求**：用于一次性的 CRUD 操作（获取 profile、触发搜索、开始投递）

**WebSocket**：用于长耗时任务的实时进度推送（模型下载、职位搜索、逐个投递）

详见 [api-contract.md](./api-contract.md)。

### 6.3 前端 ↔ Tauri Rust 通信

少量场景需要调用原生功能（比如打开文件选择对话框），通过 Tauri 的 `invoke` 机制：

```typescript
// React 侧
import { invoke } from '@tauri-apps/api/core';

const filePath = await invoke<string>('pick_resume_file');
```

```rust
// Rust 侧（src-tauri/src/main.rs）
#[tauri::command]
async fn pick_resume_file() -> Result<String, String> {
    // 打开系统原生文件选择对话框
    // ...
}
```

这部分 Rust 代码极少，主要用于：
- 原生文件对话框
- 系统通知
- 启动 / 停止 Python 子进程
- 应用退出时的清理

## 七、数据存储

### 7.1 位置（跨平台）

| 平台 | 应用数据目录 |
|------|------------|
| macOS | `~/Library/Application Support/Hamster/` |
| Windows | `%APPDATA%/Hamster/`（`C:\Users\<you>\AppData\Roaming\Hamster\`） |
| Linux | `~/.config/Hamster/` |

通过 Tauri 的 `@tauri-apps/api/path` 模块拿到跨平台路径，传给 Python 后端（环境变量 `HAMSTER_DATA_DIR`）。

```
<app_data_dir>/
├── profile.db              SQLite
├── resumes/
│   ├── main_resume.pdf
│   └── tailored_swe.pdf    用户可上传多份简历
├── models/
│   └── qwen2.5-7b-instruct-q4.gguf    (~4GB)
└── logs/
    └── hamster.log
```

### 7.2 SQLite Schema（粗略）

```sql
-- 用户信息（只有一条记录，单用户 app）
CREATE TABLE user_profile (
    id INTEGER PRIMARY KEY,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    phone TEXT,
    location TEXT,
    linkedin_url TEXT,
    github_url TEXT,
    current_resume_path TEXT,
    created_at TEXT,
    updated_at TEXT
);

-- 教育经历
CREATE TABLE education (
    id INTEGER PRIMARY KEY,
    school TEXT, degree TEXT, major TEXT,
    start_date TEXT, end_date TEXT
);

-- 工作经历
CREATE TABLE experience (
    id INTEGER PRIMARY KEY,
    company TEXT, title TEXT, description TEXT,
    start_date TEXT, end_date TEXT
);

-- 搜索任务
CREATE TABLE discovery_tasks (
    id TEXT PRIMARY KEY,
    keywords TEXT, location TEXT, filters_json TEXT,
    status TEXT, created_at TEXT
);

-- 投递记录
CREATE TABLE applications (
    id INTEGER PRIMARY KEY,
    url TEXT UNIQUE,
    company TEXT, position TEXT,
    status TEXT,  -- queued / in_progress / submitted / failed / skipped
    error TEXT,
    applied_at TEXT
);
```

### 7.3 敏感信息存储（跨平台）

未来如果需要存任何密码，用 Tauri Stronghold 插件或各平台原生 API：

- macOS: Keychain
- Windows: DPAPI / Windows Credential Manager
- Linux: libsecret（GNOME Keyring / KWallet）

## 八、依赖管理

### 8.1 Python 后端：uv workspace

```toml
# 项目根 pyproject.toml
[tool.uv.workspace]
members = [
    "packages/shared",
    "packages/profile-store",
    "packages/job-discovery",
    "packages/applicator",
    "packages/orchestrator",
    "services/backend",
]

[tool.uv.sources]
shared = { workspace = true }
profile-store = { workspace = true }
# ...
```

每个 package 有自己的 `pyproject.toml`：

```toml
# packages/job-discovery/pyproject.toml
[project]
name = "job-discovery"
dependencies = [
    "shared",           # workspace 内部依赖
    "httpx",            # 外部依赖
    "pydantic",
]
```

开发时 `uv sync` 一次，所有 package 用 editable install 装好。

### 8.2 前端：pnpm

Tauri 官方推荐用 **pnpm**（比 npm / yarn 快且节省磁盘）。

```
apps/hamster-desktop/
├── package.json
└── pnpm-lock.yaml
```

## 九、跨平台注意点

### 9.1 前端代码本身是跨平台的

React 不需要改任何东西就能在三个平台跑。UI 渲染通过系统 WebView：
- macOS 用 WebKit（Safari 内核）
- Windows 用 WebView2（Edge 的 Chromium 内核）
- Linux 用 WebKitGTK

**测试提醒**：偶尔遇到 CSS 兼容性差异（Safari vs Chromium），开发时在两个平台都测一下。

### 9.2 Python 后端本身跨平台

FastAPI、Playwright、llama-cpp-python 都支持三平台。

注意几个坑：
- 路径分隔符：用 `pathlib.Path`，不要手动拼 `/`
- 换行符：读写文本文件用 UTF-8 + `newline=''`
- 文件锁：SQLite 在 Windows 上并发要小心

### 9.3 打包需要三平台分别构建

Tauri 的 `pnpm tauri build` 只能产**当前系统**的包。要出三平台：

- 在 macOS 机器上跑一次 → 产 `.dmg`
- 在 Windows 机器上跑一次 → 产 `.exe` + `.msi`
- 在 Linux 机器上跑一次 → 产 `.AppImage` / `.deb`

**推荐方案**：用 GitHub Actions 的 matrix build，一次 push 触发三平台并行构建。详见 [packaging-strategy.md](./packaging-strategy.md)。

## 十、与 v1 的关键变化

| 模块 | v1 | v2 |
|------|----|----|
| LinkedIn | 主入口，硬编码 Easy Apply | 可选 source，只做浏览不做投递 |
| 职位发现 | LinkedIn 网页爬取 | ATS 公开 API（Greenhouse / Lever / Ashby / Workable） |
| LLM | Ollama（独立进程） | llama-cpp-python（嵌入） |
| 用户接口 | Python CLI | Tauri 桌面 App（TypeScript + React） |
| 平台 | 仅 macOS（理论） | macOS + Windows + Linux |
| 代码组织 | 单 Python package | monorepo（uv workspace） |
| 分发 | `pip install` | `.dmg` / `.exe` / `.AppImage` 一键安装 |

## 十一、学习价值与技术栈选择理由

这套技术栈的一个额外考量是**开发者成长**。

| 技术 | 通用性 | 学习价值 |
|------|-------|---------|
| TypeScript | ⭐⭐⭐⭐⭐ | 前端 / 后端 / 移动都用，10 年内不过时 |
| React | ⭐⭐⭐⭐⭐ | 前端事实标准，就业市场最大 |
| Python + FastAPI | ⭐⭐⭐⭐⭐ | AI / 后端主流栈 |
| Tauri（一点 Rust） | ⭐⭐⭐ | 接触 Rust 生态，不深陷 |
| Playwright | ⭐⭐⭐⭐ | 测试 / 自动化场景必备 |
| llama-cpp-python | ⭐⭐⭐⭐ | 本地 AI 的标准栈 |

相比 Swift 的 "只能做 macOS"，这套栈学完能做：Web 应用、跨平台桌面 app、移动 app（React Native）、后端服务、AI 工具。职业可选项多得多。
