# 实施计划 — 逐步开发指南

> 最后更新：2026-02-15
> 开发顺序：自底向上（浏览器层 → 智能层 → 编排层）

---

## 开发原则

1. **每一步都可独立运行和验证** — 不写完三层才能测试
2. **先跑通再优化** — 先用最简单的方式实现，确认能工作后再迭代
3. **LinkedIn 硬编码和 LLM 通用适配并行推进** — 但 LinkedIn 优先

---

## Phase 0：项目脚手架（Day 1）

### 目标
能 `python -m src.main` 跑起来，Playwright 能打开浏览器。

### 步骤

1. 初始化项目结构：

```
hamster/
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── browser/
│   │   └── __init__.py
│   ├── ai/
│   │   └── __init__.py
│   ├── orchestrator/
│   │   └── __init__.py
│   └── config/
│       └── __init__.py
├── config/
│   ├── profile.yaml
│   └── settings.yaml
├── data/
├── pyproject.toml
├── requirements.txt
└── README.md
```

2. `requirements.txt` 初始依赖：

```
playwright>=1.40
ollama>=0.4
pyyaml>=6.0
loguru>=0.7
typer>=0.9
```

3. `src/main.py` — 验证 Playwright 能启动：

```python
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto("https://www.linkedin.com")
        await page.wait_for_timeout(3000)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
```

4. 运行 `playwright install chromium` 安装浏览器

### 验收标准
- ✅ 运行后能看到 Chromium 打开 LinkedIn 首页

---

## Phase 1：浏览器层 — BrowserManager（Day 2）

### 目标
封装 Playwright 实例管理，支持 Cookie 持久化（避免每次重新登录）。

### 文件：`src/browser/browser_manager.py`

### 核心接口

```python
class BrowserManager:
    async def launch(self, headless: bool = False) -> None
        """启动浏览器，加载已保存的 Cookie/Session"""

    async def new_page(self) -> Page
        """创建新页面"""

    async def save_session(self) -> None
        """保存当前 Cookie 到本地文件（data/session.json）"""

    async def close(self) -> None
        """关闭浏览器"""
```

### 关键实现细节
- 使用 `browser.new_context(storage_state="data/session.json")` 加载已保存的登录状态
- 首次运行时 `storage_state` 文件不存在，正常创建空 context
- 每次关闭前调用 `context.storage_state(path="data/session.json")` 保存

### 验收标准
- ✅ 第一次运行：打开浏览器，手动登录 LinkedIn，关闭后 session 保存到文件
- ✅ 第二次运行：打开浏览器，自动恢复登录状态，无需重新登录

---

## Phase 2：浏览器层 — DOMExtractor（Day 3-4）

### 目标
从任意页面提取所有可交互元素，输出结构化 JSON。

### 文件：`src/browser/dom_extractor.py`

### 核心接口

```python
class DOMExtractor:
    async def extract(self, page: Page) -> PageDOM
        """提取页面可交互元素，返回结构化描述"""
```

### 输出数据结构

```python
@dataclass
class PageElement:
    id: str              # 内部编号 "el_1", "el_2"...
    tag: str             # "input", "select", "button", "textarea"
    type: str | None     # "text", "email", "file", "submit"...
    label: str | None    # 关联的 label 文本
    placeholder: str | None
    required: bool
    options: list[str] | None  # select 的选项列表
    value: str | None    # 当前值
    selector: str        # CSS selector，用于后续操作

@dataclass
class PageDOM:
    url: str
    title: str
    elements: list[PageElement]
```

### 开发顺序（从简单到复杂）

1. **先做基础提取**（Day 3 上午）
   - `input[type=text]`, `input[type=email]`, `input[type=tel]`, `input[type=password]`
   - `textarea`
   - `button`, `input[type=submit]`
   - 用 `page.query_selector_all()` 遍历

2. **加上 label 关联**（Day 3 下午）
   - `<label for="xxx">` → 通过 `for` 属性关联
   - `<label><input></label>` → 嵌套关联
   - `aria-label`, `aria-labelledby` 属性
   - 没有 label 时用 `placeholder` 兜底

3. **处理 select 和 checkbox/radio**（Day 4 上午）
   - 原生 `<select>` → 提取所有 `<option>` 文本
   - `input[type=checkbox]`, `input[type=radio]` → 提取关联文本
   - `input[type=file]` → 标记为文件上传

4. **处理自定义组件**（Day 4 下午）
   - `role="combobox"`, `role="listbox"` → 自定义下拉框
   - `div[contenteditable]` → 富文本编辑器
   - 这部分先做基础识别，复杂情况后续迭代

### 验收标准
- ✅ 在 LinkedIn 职位申请页面运行，能提取出所有表单字段
- ✅ 在 Greenhouse 示例申请页面运行，能提取出所有表单字段
- ✅ 输出的 JSON 人眼可读，字段名和 label 对应正确

### 测试方法
写一个独立脚本，打开指定 URL，提取 DOM，打印 JSON：

```python
# scripts/test_extractor.py
async def test():
    bm = BrowserManager()
    await bm.launch()
    page = await bm.new_page()
    await page.goto("https://boards.greenhouse.io/some-company/jobs/12345")

    extractor = DOMExtractor()
    dom = await extractor.extract(page)

    for el in dom.elements:
        print(f"[{el.id}] {el.tag}({el.type}) label='{el.label}' required={el.required}")
```

---

## Phase 3：浏览器层 — ActionExecutor（Day 5）

### 目标
根据指令执行页面操作（填写、点击、选择、上传）。

### 文件：`src/browser/action_executor.py`

### 核心接口

```python
class ActionExecutor:
    async def execute(self, page: Page, action: Action) -> ActionResult
        """执行单个操作指令"""
```

### 操作类型

```python
@dataclass
class Action:
    type: str       # "fill", "click", "select", "upload", "check"
    selector: str   # CSS selector
    value: str | None

@dataclass
class ActionResult:
    success: bool
    error: str | None
```

### 每种操作的实现

| 操作 | Playwright API | 注意事项 |
|------|---------------|---------|
| fill | `page.fill(selector, value)` | 先 `page.click(selector)` 聚焦，再 fill |
| click | `page.click(selector)` | 加 `timeout=5000` 防止元素未加载 |
| select | `page.select_option(selector, value)` | 自定义下拉框需要先 click 展开再 click 选项 |
| upload | `page.set_input_files(selector, filepath)` | 验证文件路径存在 |
| check | `page.check(selector)` / `page.uncheck()` | 先检查当前状态 |

### 验收标准
- ✅ 能在 LinkedIn Easy Apply 表单上自动填写姓名、邮箱
- ✅ 能上传 PDF 简历
- ✅ 能点击 "Submit" 按钮
- ✅ 操作失败时返回错误信息而不是崩溃

---

## Phase 4：LinkedIn 硬编码 — 登录 + 搜索（Day 6-7）

### 目标
自动登录 LinkedIn，按条件搜索职位，获取职位列表。

### 文件：`src/linkedin/navigator.py`

### 开发顺序

1. **登录流程**（Day 6 上午）
   - 检查是否已登录（Cookie 恢复）
   - 未登录 → 导航到登录页 → 填写账号密码 → 点击登录
   - 遇到二次验证 → 暂停，打印提示，等待用户手动完成
   - 登录成功 → 保存 session

2. **职位搜索**（Day 6 下午）
   - 导航到 `linkedin.com/jobs/search/`
   - 填写关键词、地点
   - 设置筛选器（经验级别、时间范围、Easy Apply 筛选）
   - 这些都是硬编码的 URL 参数或 DOM 操作

3. **职位列表解析**（Day 7 上午）
   - 提取当前页面的职位卡片列表
   - 每个卡片提取：职位名、公司名、地点、链接、是否 Easy Apply
   - 滚动加载更多 / 翻页

4. **职位遍历逻辑**（Day 7 下午）
   - 逐个点击职位卡片
   - 判断是 Easy Apply 还是外部 Apply
   - Easy Apply → 进入 Phase 5
   - 外部 Apply → 记录 URL，后续由 LLM 通用流程处理

### 核心接口

```python
class LinkedInNavigator:
    async def login(self, email: str, password: str) -> bool
    async def search_jobs(self, keywords: str, location: str, filters: dict) -> None
    async def get_job_listings(self) -> list[JobListing]
    async def next_page(self) -> bool

@dataclass
class JobListing:
    title: str
    company: str
    location: str
    url: str
    is_easy_apply: bool
```

### 验收标准
- ✅ 能自动登录（或恢复 session）
- ✅ 能搜索 "Software Engineer" + "Shanghai" 并看到结果
- ✅ 能解析出职位列表，区分 Easy Apply 和外部 Apply

---

## Phase 5：LinkedIn 硬编码 — Easy Apply（Day 8-9）

### 目标
完成 LinkedIn Easy Apply 的多步表单填写和提交。

### 文件：`src/linkedin/easy_apply.py`

### Easy Apply 流程拆解

LinkedIn Easy Apply 是一个多步 wizard：

```
Step 1: 联系信息（姓名、邮箱、电话 — 通常预填）
    ↓ [Next]
Step 2: 简历上传（上传 PDF 或选择已有简历）
    ↓ [Next]
Step 3: 附加问题（工作年限、是否需要签证、薪资期望等 — 可选）
    ↓ [Next]
Step N: Review（确认信息）
    ↓ [Submit]
```

### 开发顺序

1. **点击 Easy Apply 按钮，打开弹窗**（Day 8 上午）
   - 定位 "Easy Apply" 按钮
   - 处理弹窗加载等待

2. **逐步填写表单**（Day 8 下午 - Day 9 上午）
   - 每一步：检测当前步骤的字段 → 用 profile 数据填写 → 点击 Next
   - 联系信息通常已预填，检查即可
   - 简历上传：`set_input_files`
   - 附加问题：这里需要 LLM 辅助回答开放式问题（先硬编码常见问题的答案，后续接入 LLM）

3. **提交 + 确认**（Day 9 下午）
   - 最后一步点击 "Submit application"
   - 检测提交成功的确认信息
   - 记录结果

### 核心接口

```python
class EasyApplyHandler:
    async def apply(self, page: Page, profile: UserProfile) -> ApplyResult

@dataclass
class ApplyResult:
    success: bool
    job_title: str
    company: str
    error: str | None
```

### 验收标准
- ✅ 能完成一个完整的 Easy Apply 流程（建议用测试职位，不要真的提交）
- ✅ 能处理多步表单（Next → Next → Submit）
- ✅ 简历上传成功
- ✅ 附加问题能用预设答案填写

---

## Phase 6：智能层 — Ollama 集成 + PromptBuilder（Day 10-11）

### 目标
能调用本地 LLM 分析页面结构，输出结构化操作指令。

### 文件
- `src/ai/llm_client.py` — Ollama API 封装
- `src/ai/prompt_builder.py` — Prompt 模板构建

### 开发顺序

1. **LLM 客户端**（Day 10 上午）

```python
class LLMClient:
    async def generate(self, prompt: str) -> dict
        """调用 Ollama，返回解析后的 JSON"""
```

   - 调用 `ollama.chat()` 或 `ollama.generate()`
   - 指定 `format="json"` 强制 JSON 输出
   - 加超时处理（本地模型推理可能慢）
   - JSON 解析失败时重试（最多 3 次）

2. **Prompt 模板**（Day 10 下午 - Day 11）

   核心 prompt 结构：

```
你是一个网页表单填写助手。

## 用户简历数据
{profile_yaml}

## 当前页面信息
URL: {url}
标题: {title}

## 页面可交互元素
{elements_json}

## 任务
1. 判断页面类型（login/job_list/job_detail/application_form/confirmation/unknown）
2. 如果是申请表单，将表单字段与用户简历数据匹配
3. 生成操作指令列表

## 输出格式（严格 JSON）
{output_schema}
```

   - 需要 few-shot 示例（给 2-3 个输入输出样例）
   - 输出格式校验：用 JSON Schema 或手动检查必填字段

### 验收标准
- ✅ 给定一个 Greenhouse 申请页面的 DOM 提取结果，LLM 能正确识别为申请表单
- ✅ LLM 能正确匹配 "First Name" → profile.first_name
- ✅ 输出的 JSON 格式稳定，能被代码解析

### 测试方法
先离线测试（不需要真的打开浏览器）：

```python
# scripts/test_llm.py
# 用之前 DOMExtractor 保存的真实 DOM 数据作为输入
dom_json = load_json("test_data/greenhouse_page.json")
profile = load_yaml("config/profile.yaml")

prompt = prompt_builder.build(dom_json, profile)
result = await llm_client.generate(prompt)
print(json.dumps(result, indent=2))
```

---

## Phase 7：智能层 — PageAnalyzer + FormMapper（Day 12-13）

### 目标
将 LLM 的原始输出转化为可执行的操作指令。

### 文件
- `src/ai/page_analyzer.py` — 页面类型判断
- `src/ai/form_mapper.py` — 表单字段匹配
- `src/ai/decision_engine.py` — 综合决策

### PageAnalyzer 策略（混合方案）

先用规则快速判断，LLM 做兜底：

```python
class PageAnalyzer:
    def analyze_by_rules(self, dom: PageDOM) -> str | None:
        """规则判断：URL 模式 + 关键元素"""
        if "login" in dom.url or "signin" in dom.url:
            return "login"
        if dom has submit button and input fields > 3:
            return "application_form"
        return None  # 规则无法判断，交给 LLM

    async def analyze_by_llm(self, dom: PageDOM) -> str:
        """LLM 判断页面类型"""
```

### FormMapper — 核心匹配逻辑

```python
class FormMapper:
    async def map_fields(self, elements: list[PageElement], profile: UserProfile) -> list[Action]:
        """将表单字段与用户数据匹配，生成填写指令"""
```

这个模块的输入是 DOMExtractor 的输出 + 用户 profile，输出是 ActionExecutor 能执行的 Action 列表。

### 验收标准
- ✅ 给定 Greenhouse 页面 DOM，能生成正确的填写指令列表
- ✅ 给定 Lever 页面 DOM，同样能工作
- ✅ 置信度低于阈值时，标记为需要人工介入

---

## Phase 8：编排层 — 状态机 + 任务队列（Day 14-16）

### 目标
把所有模块串起来，实现完整的自动投递流程。

### 文件
- `src/orchestrator/flow_state_machine.py`
- `src/orchestrator/job_queue.py`
- `src/orchestrator/retry_handler.py`
- `src/orchestrator/result_logger.py`

### 状态机定义

```python
class FlowState(Enum):
    INIT = "init"
    LINKEDIN_SEARCH = "linkedin_search"
    LINKEDIN_BROWSE = "linkedin_browse"
    EASY_APPLY = "easy_apply"
    EXTERNAL_NAVIGATE = "external_navigate"
    EXTERNAL_ANALYZE = "external_analyze"
    EXTERNAL_FILL = "external_fill"
    CONFIRMATION = "confirmation"
    ERROR = "error"
    DONE = "done"
```

### 核心流程

```
INIT → LINKEDIN_SEARCH → LINKEDIN_BROWSE
                              ↓
                    is_easy_apply?
                    ├── Yes → EASY_APPLY → CONFIRMATION → DONE
                    └── No  → EXTERNAL_NAVIGATE → EXTERNAL_ANALYZE
                                                      ↓
                                              EXTERNAL_FILL → CONFIRMATION → DONE
```

### 验收标准
- ✅ 能从搜索开始，自动遍历职位列表
- ✅ Easy Apply 职位走硬编码流程
- ✅ 外部 Apply 职位走 LLM 通用流程
- ✅ 每个投递结果记录到 `data/applications.json`
- ✅ 失败时自动重试，超过次数跳过并记录

---

## Phase 9：集成联调 + 稳定性（Day 17-20）

### 测试矩阵

| 场景 | 预期行为 | 优先级 |
|------|---------|--------|
| LinkedIn Easy Apply（标准流程） | 自动完成 | P0 |
| LinkedIn Easy Apply（有附加问题） | LLM 辅助回答 | P0 |
| 外部跳转 → Greenhouse 表单 | LLM 分析 + 填写 | P0 |
| 外部跳转 → Lever 表单 | LLM 分析 + 填写 | P1 |
| 外部跳转 → Workday 表单 | LLM 分析 + 填写 | P2 |
| 登录 session 过期 | 检测 + 重新登录 | P1 |
| 网络超时 | 重试 | P1 |
| 验证码 / 人机验证 | 暂停 + 通知用户 | P1 |
| LLM 输出格式错误 | 重试 3 次 → 跳过 | P1 |
| 文件上传失败 | 重试 → 跳过 | P2 |

### CLI 命令设计

```bash
# 启动投递
python -m src.main start --keywords "Software Engineer" --location "Shanghai"

# 查看投递状态
python -m src.main status

# 从中断处恢复
python -m src.main resume

# 查看/编辑配置
python -m src.main config show
python -m src.main config edit
```

---

## 开发顺序总结

```
Day 1     Phase 0   脚手架，Playwright 能跑
Day 2     Phase 1   BrowserManager，Cookie 持久化
Day 3-4   Phase 2   DOMExtractor，能提取表单字段
Day 5     Phase 3   ActionExecutor，能填表点按钮
Day 6-7   Phase 4   LinkedIn 登录 + 搜索 + 职位列表
Day 8-9   Phase 5   LinkedIn Easy Apply 全流程
Day 10-11 Phase 6   Ollama 集成 + Prompt 工程
Day 12-13 Phase 7   PageAnalyzer + FormMapper
Day 14-16 Phase 8   状态机 + 编排层
Day 17-20 Phase 9   联调 + 稳定性 + CLI
```

**Day 9 结束时**你就有一个能用的 LinkedIn Easy Apply 机器人了（相当于 AIHawk 的核心功能）。

**Day 20 结束时**你有一个能处理外部公司页面的完整投递机器人（这是 AIHawk 做不到的）。
