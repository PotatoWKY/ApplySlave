# API 合约

> Tauri 前端（TypeScript）↔ Python 后端（FastAPI）的 HTTP / WebSocket 接口定义

---

## 一、基础约定

- Base URL: `http://localhost:8765`（端口由 Tauri Rust 侧传给前端，通过 `invoke('backend_port')` 获取）
- 所有请求 / 响应：JSON
- 日期格式：ISO 8601（`2026-02-13T10:30:00Z`）
- 分页：`?limit=20&offset=0`
- 认证：localhost 单用户场景暂不做认证（后续需要时加 token）

---

## 二、TypeScript 类型定义

前端和后端的数据模型对应关系，通过手写或自动生成保持同步：

```typescript
// apps/hamster-desktop/src/types/api.ts

export interface UserProfile {
    id: number;
    first_name: string;
    last_name: string;
    email: string;
    phone: string;
    location: string;
    linkedin_url?: string;
    github_url?: string;
    education: Education[];
    experience: Experience[];
    skills: string[];
    updated_at: string;
}

export interface JobListing {
    id: string;
    source: 'greenhouse' | 'lever' | 'ashby' | 'workable' | 'linkedin';
    company: string;
    title: string;
    location: string;
    url: string;
    apply_url: string;
    posted_at: string;
}

export type ApplicationStatus =
    | 'queued'
    | 'in_progress'
    | 'submitted'
    | 'failed'
    | 'skipped';

export interface Application {
    id: number;
    url: string;
    company: string;
    title: string;
    status: ApplicationStatus;
    error: string | null;
    applied_at: string | null;
}
```

**可选优化**：Python 端用 Pydantic 定义 schema，用 [`datamodel-code-generator`](https://github.com/koxudaxi/datamodel-code-generator) 或 FastAPI 的 OpenAPI + `openapi-typescript` 自动生成 TypeScript 类型，避免手动同步。

---

## 三、Profile API

### POST /api/profile

上传 / 更新用户简历和信息。

**Request**：
```json
{
    "first_name": "San",
    "last_name": "Zhang",
    "email": "san@example.com",
    "phone": "+86-13800000000",
    "location": "Shanghai",
    "linkedin_url": "https://linkedin.com/in/sanzhang",
    "github_url": "https://github.com/sanzhang",
    "education": [
        {
            "school": "XX University",
            "degree": "Bachelor",
            "major": "Computer Science",
            "start_date": "2018-09",
            "end_date": "2022-06"
        }
    ],
    "experience": [
        {
            "company": "XX Corp",
            "title": "Software Engineer",
            "description": "...",
            "start_date": "2022-07",
            "end_date": null
        }
    ],
    "skills": ["Python", "TypeScript", "AWS"]
}
```

**Response 200**：
```json
{
    "id": 1,
    "updated_at": "2026-02-13T10:30:00Z"
}
```

### GET /api/profile

获取当前 profile。

**Response 200**：（同 POST 的 request body，外加 `id`、`updated_at`）

### POST /api/profile/resume

上传简历 PDF 文件。

**Request**：`multipart/form-data`
- `file`: PDF 文件
- `name`: "main_resume" | "tailored_swe"（可选，默认 main_resume）

**Response 200**：
```json
{
    "path": "resumes/main_resume.pdf",
    "parsed_fields": {
        "detected_name": "San Zhang",
        "detected_email": "san@example.com",
        "detected_experience_count": 3
    }
}
```

后端会自动解析 PDF，把提取到的字段反向更新到 profile（用户可以在 UI 确认 / 修改）。

---

## 四、Job Discovery API

### POST /api/jobs/discover

触发职位搜索（异步任务）。

**Request**：
```json
{
    "keywords": "Software Engineer",
    "location": "Remote",
    "filters": {
        "experience_level": ["Entry", "Mid"],
        "job_type": ["Full-time"],
        "remote_only": true,
        "exclude_companies": ["Oracle"]
    },
    "sources": ["greenhouse", "lever", "ashby", "workable"],
    "max_results": 200
}
```

**Response 202**：
```json
{
    "task_id": "disc-abc123",
    "status": "queued"
}
```

### GET /api/jobs/discover/{task_id}

查询搜索任务进度。

**Response 200**：
```json
{
    "task_id": "disc-abc123",
    "status": "completed",
    "progress": {
        "total_sources": 4,
        "completed_sources": 4,
        "total_jobs_found": 187
    },
    "results": [
        {
            "id": "gh-stripe-engineer-1",
            "source": "greenhouse",
            "company": "Stripe",
            "title": "Software Engineer",
            "location": "San Francisco / Remote",
            "url": "https://boards.greenhouse.io/stripe/jobs/12345",
            "posted_at": "2026-02-10",
            "apply_url": "https://boards.greenhouse.io/stripe/jobs/12345/application"
        }
    ]
}
```

### GET /api/jobs/discover

列出所有搜索任务历史。

---

## 五、Applications API

### POST /api/applications

批量提交要投递的职位 URL。

**Request**：
```json
{
    "jobs": [
        {
            "url": "https://boards.greenhouse.io/stripe/jobs/12345/application",
            "company": "Stripe",
            "title": "Software Engineer"
        },
        {
            "url": "https://jobs.lever.co/company/xxx",
            "company": "Other Co",
            "title": "Backend Engineer"
        }
    ],
    "resume_name": "main_resume",
    "cover_letter_template": null,
    "confirm_before_submit": false
}
```

**Response 202**：
```json
{
    "batch_id": "batch-xyz789",
    "total": 2,
    "queued": 2
}
```

### GET /api/applications

列出投递记录。

**Query params**:
- `status`: queued / in_progress / submitted / failed / skipped
- `limit`, `offset`

**Response 200**：
```json
{
    "total": 42,
    "applications": [
        {
            "id": 1,
            "url": "https://boards.greenhouse.io/stripe/jobs/12345",
            "company": "Stripe",
            "title": "Software Engineer",
            "status": "submitted",
            "applied_at": "2026-02-13T10:35:22Z",
            "error": null
        },
        {
            "id": 2,
            "url": "https://jobs.lever.co/company/xxx",
            "company": "Other Co",
            "title": "Backend Engineer",
            "status": "failed",
            "error": "CAPTCHA detected, manual intervention required"
        }
    ]
}
```

### GET /api/applications/{id}

单个投递记录的详细信息（截图、LLM 决策日志等）。

### POST /api/applications/{id}/retry

重试失败的投递。

---

## 六、System API

### GET /api/health

健康检查。Tauri Rust shell 用它判断后端是否启动完成。

**Response 200**：
```json
{
    "status": "ok",
    "version": "0.1.0",
    "model_loaded": true,
    "model_name": "qwen2.5-7b-instruct-q4"
}
```

### POST /api/model/download

触发 LLM 模型下载（首次启动）。

**Response 202**：
```json
{
    "task_id": "model-dl-1"
}
```

### GET /api/model/status

查询模型状态。

**Response 200**：
```json
{
    "installed": false,
    "downloading": true,
    "download_progress": {
        "downloaded_bytes": 1234567890,
        "total_bytes": 4000000000,
        "speed_bps": 10000000
    }
}
```

---

## 七、WebSocket API

### /api/ws

全局 WebSocket 连接，推送所有实时事件。

**前端连接代码**：
```typescript
// apps/hamster-desktop/src/services/websocket.ts
import { invoke } from '@tauri-apps/api/core';

const port = await invoke<number>('backend_port');
const ws = new WebSocket(`ws://localhost:${port}/api/ws`);

ws.onmessage = (event) => {
    const message = JSON.parse(event.data) as WSMessage;
    // 派发到对应的 handler / Zustand store
};
```

**服务端推送事件**（`WSMessage` 类型）：

```typescript
type WSMessage =
    | ModelDownloadProgress
    | DiscoveryProgress
    | DiscoveryCompleted
    | ApplicationStarted
    | ApplicationStep
    | ApplicationCompleted
    | ApplicationFailed
    | InterventionRequired;

interface ModelDownloadProgress {
    type: 'model_download_progress';
    downloaded_bytes: number;
    total_bytes: number;
    speed_bps: number;
}

interface DiscoveryProgress {
    type: 'discovery_progress';
    task_id: string;
    source: string;
    jobs_found: number;
}

interface ApplicationStep {
    type: 'application_step';
    application_id: number;
    step: 'analyzing_page' | 'filling_form' | 'submitting' | 'verifying';
    message: string;
}

interface InterventionRequired {
    type: 'intervention_required';
    application_id: number;
    reason: 'CAPTCHA' | 'LOW_CONFIDENCE' | 'LOGIN_REQUIRED';
    screenshot_base64: string;
}
```

---

## 八、Tauri Commands（前端 ↔ Rust）

少量场景前端需要直接调 Rust：

```typescript
import { invoke } from '@tauri-apps/api/core';

// 获取 Python 后端端口（启动时分配）
const port = await invoke<number>('backend_port');

// 打开原生文件对话框选简历
const resumePath = await invoke<string | null>('pick_resume_file');

// 在系统文件管理器中显示文件
await invoke('show_in_folder', { path: resumePath });

// 触发更新检查
await invoke('check_for_updates');
```

对应的 Rust 侧：

```rust
#[tauri::command]
fn backend_port() -> u16 { 8765 }

#[tauri::command]
async fn pick_resume_file() -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    // 弹出原生文件对话框
}

#[tauri::command]
fn show_in_folder(path: String) -> Result<(), String> {
    // macOS: `open -R path`
    // Windows: `explorer /select,path`
    // Linux: `xdg-open dirname`
}
```

---

## 九、错误响应

所有 HTTP 错误统一格式：

```json
{
    "error": {
        "code": "PROFILE_NOT_FOUND",
        "message": "No profile configured. Please upload resume first.",
        "details": {}
    }
}
```

HTTP 状态码：
- 400: 请求参数错误
- 404: 资源不存在
- 409: 状态冲突（如已经有相同 URL 在投递中）
- 500: 服务端错误
- 503: 依赖不可用（如 LLM 模型未加载）

---

## 十、版本管理

API version 在 URL 前缀：`/api/v1/profile`

v1 稳定前可以省略 version 段，用 `/api/profile`，v2 出来时再加前缀。
