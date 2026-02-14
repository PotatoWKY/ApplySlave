# 简历自动投递机器人 - 架构设计

## 项目概述

基于 Playwright + 本地 LLM 的智能简历投递机器人。核心理念：不针对特定网站做硬编码适配，而是让模型自主理解页面语义，识别表单字段并完成填写和投递操作。

---

## 整体架构（三层）

```
┌─────────────────────────────────────────────────┐
│                  编排层 (Orchestrator)            │
│         任务调度 / 状态机 / 投递流程管理            │
├─────────────────────────────────────────────────┤
│                  智能层 (AI Core)                 │
│     页面理解 / 意图识别 / 表单映射 / 决策引擎       │
├─────────────────────────────────────────────────┤
│                  浏览器层 (Browser)               │
│     Playwright 控制 / DOM 提取 / 动作执行          │
└─────────────────────────────────────────────────┘
```

---

## 一、浏览器层 (Browser Layer)

负责与网页的所有底层交互，对上层提供结构化的页面信息和原子操作接口。

### 模块

| 模块 | 职责 |
|------|------|
| BrowserManager | Playwright 实例管理、页面生命周期、Cookie/Session 持久化 |
| DOMExtractor | 提取页面可交互元素（input、select、button、textarea、checkbox 等），生成结构化描述 |
| ActionExecutor | 执行原子操作：click、fill、select、upload、scroll、wait |
| ScreenshotCapture | 截图用于调试和 LLM 视觉理解（可选） |

### DOMExtractor 输出示例

```json
{
  "url": "https://jobs.example.com/apply",
  "title": "Software Engineer - Apply",
  "elements": [
    {
      "id": "el_1",
      "tag": "input",
      "type": "text",
      "label": "First Name",
      "placeholder": "Enter your first name",
      "required": true,
      "selector": "#first-name"
    },
    {
      "id": "el_2",
      "tag": "input",
      "type": "file",
      "label": "Upload Resume",
      "accept": ".pdf,.docx",
      "selector": "input[name='resume']"
    },
    {
      "id": "el_3",
      "tag": "button",
      "text": "Submit Application",
      "selector": "button[type='submit']"
    }
  ]
}
```

---

## 二、智能层 (AI Core)

核心大脑。接收结构化页面信息，结合用户简历数据，输出操作指令。

### 模块

| 模块 | 职责 |
|------|------|
| PageAnalyzer | 分析当前页面类型：登录页 / 职位列表 / 职位详情 / 申请表单 / 确认页 / 其他 |
| FormMapper | 将表单字段与用户简历数据做语义匹配（"First Name" → user.firstName） |
| DecisionEngine | 决定下一步动作：填写、点击、跳过、上传文件、翻页等 |
| PromptBuilder | 构建发给本地 LLM 的 prompt，包含页面上下文 + 用户数据 + 指令 |

### LLM 调用策略

```
用户简历数据 + 页面结构化描述
        ↓
   PromptBuilder 组装 prompt
        ↓
   本地 LLM 推理（Ollama / llama.cpp）
        ↓
   结构化 JSON 输出（操作指令列表）
```

### LLM 输出格式

```json
{
  "page_type": "application_form",
  "confidence": 0.95,
  "actions": [
    { "type": "fill", "selector": "#first-name", "value": "张三" },
    { "type": "fill", "selector": "#email", "value": "zhangsan@email.com" },
    { "type": "upload", "selector": "input[name='resume']", "file": "resume.pdf" },
    { "type": "select", "selector": "#experience", "value": "3-5 years" },
    { "type": "click", "selector": "button[type='submit']" }
  ],
  "reasoning": "识别为职位申请表单，已匹配所有必填字段"
}
```

### 本地模型选型建议

| 场景 | 推荐模型 | 说明 |
|------|---------|------|
| 表单字段匹配 | Qwen2.5-7B / Llama3-8B | 文本语义理解，速度快 |
| 复杂页面理解 | Qwen2.5-VL / LLaVA | 需要视觉理解时使用（多模态） |
| 轻量决策 | Phi-3-mini | 简单页面分类，资源占用低 |

运行方式：通过 Ollama 本地部署，HTTP API 调用。

---

## 三、编排层 (Orchestrator)

控制整个投递流程的状态机，管理任务队列和异常处理。

### 模块

| 模块 | 职责 |
|------|------|
| JobQueue | 待投递职位队列管理（URL 列表 / 搜索关键词） |
| FlowStateMachine | 投递流程状态机，驱动页面间跳转 |
| RetryHandler | 失败重试、异常恢复 |
| ResultLogger | 投递结果记录（成功/失败/跳过/原因） |
| ConfigManager | 用户简历数据、偏好设置、模型配置 |

### 状态机流转

```
[开始] → [打开职位页] → [分析页面]
                            ↓
                    ┌── 职位列表页 → 筛选 → 点击职位 → [分析页面]
                    ├── 职位详情页 → 点击申请 → [分析页面]
                    ├── 登录页 → 自动登录 → [分析页面]
                    ├── 申请表单 → 填写 → 提交 → [分析页面]
                    ├── 确认页 → 记录成功 → [下一个职位]
                    └── 未知页面 → 截图 → 跳过/人工介入
```

---

## 四、数据层

### 用户简历数据结构

```json
// config/profile.json
{
  "personal": {
    "first_name": "三",
    "last_name": "张",
    "email": "zhangsan@email.com",
    "phone": "+86-138xxxx0000",
    "location": "上海"
  },
  "education": [
    {
      "school": "XX大学",
      "degree": "本科",
      "major": "计算机科学",
      "start": "2018-09",
      "end": "2022-06"
    }
  ],
  "experience": [
    {
      "company": "XX科技",
      "title": "后端工程师",
      "start": "2022-07",
      "end": "2025-01",
      "description": "负责微服务架构设计与开发..."
    }
  ],
  "skills": ["Python", "TypeScript", "Docker"],
  "resume_file": "./resume.pdf",
  "cover_letter_template": "./cover_letter.md"
}
```

### 投递记录

```json
// data/applications.json
[
  {
    "url": "https://jobs.example.com/apply/12345",
    "company": "Example Inc",
    "position": "Software Engineer",
    "status": "submitted",
    "timestamp": "2026-02-13T10:30:00",
    "error": null
  }
]
```

---

## 五、技术栈

| 层 | 技术 |
|----|------|
| 语言 | TypeScript (Node.js) |
| 浏览器自动化 | Playwright |
| 本地 LLM | Ollama (Qwen2.5 / Llama3) |
| 配置 | JSON |
| 日志 | pino |
| CLI | commander |

---

## 六、项目结构

```
resume-bot/
├── src/
│   ├── browser/
│   │   ├── browser-manager.ts
│   │   ├── dom-extractor.ts
│   │   ├── action-executor.ts
│   │   └── screenshot.ts
│   ├── ai/
│   │   ├── page-analyzer.ts
│   │   ├── form-mapper.ts
│   │   ├── decision-engine.ts
│   │   └── prompt-builder.ts
│   ├── orchestrator/
│   │   ├── job-queue.ts
│   │   ├── flow-state-machine.ts
│   │   ├── retry-handler.ts
│   │   └── result-logger.ts
│   ├── config/
│   │   └── config-manager.ts
│   └── index.ts
├── config/
│   ├── profile.json         # 用户简历数据
│   └── settings.json        # 运行配置
├── data/
│   └── applications.json    # 投递记录
├── package.json
└── tsconfig.json
```

---

## 七、核心流程伪代码

```typescript
async function applyToJob(url: string) {
  const page = await browserManager.openPage(url);
  
  while (true) {
    // 1. 提取页面结构
    const dom = await domExtractor.extract(page);
    
    // 2. LLM 分析页面 + 生成操作指令
    const prompt = promptBuilder.build(dom, userProfile);
    const instructions = await llm.generate(prompt);
    
    // 3. 执行操作
    for (const action of instructions.actions) {
      await actionExecutor.execute(page, action);
    }
    
    // 4. 判断是否完成
    if (instructions.page_type === 'confirmation') {
      resultLogger.log(url, 'submitted');
      break;
    }
    
    // 5. 等待页面变化后继续循环
    await page.waitForLoadState('networkidle');
  }
}
```

---

## 八、关键设计决策

1. **不做网站特定适配** — 所有页面理解都交给 LLM，保证通用性
2. **结构化 DOM 而非截图** — 优先用文本描述页面，速度快、token 少；截图作为 fallback
3. **本地模型优先** — 隐私安全，简历数据不出本机
4. **循环式交互** — 每次操作后重新分析页面，适应多步骤表单和页面跳转
5. **人工介入兜底** — 遇到验证码或低置信度页面时暂停，通知用户处理

---

## 九、Peer Work 对比：与 LLM + Playwright MCP 方案的差异

### 背景

一种常见的替代方案是直接使用大语言模型（如 Claude、GPT-4）配合 Playwright MCP Server 来完成浏览器自动化。MCP（Model Context Protocol）是 Anthropic 发布的开放协议，基于 JSON-RPC 2.0，让 LLM 应用通过标准化接口发现和调用外部工具。Playwright MCP Server 将浏览器操作（navigate、click、fill、screenshot 等）暴露为 MCP Tools，LLM 在每一步推理中决定调用哪个 tool、传什么参数。

### 核心差异：LLM 的角色定位

| 维度 | LLM + Playwright MCP | 本方案 |
|------|----------------------|--------|
| LLM 角色 | 全权决策者：每个原子操作都由 LLM 推理决定 | 语义理解顾问：只在需要"理解"的环节介入 |
| 决策粒度 | 每次点击、填写都是一次完整 LLM 推理 | 每个页面一次 LLM 调用，批量生成操作指令 |
| 流程控制 | LLM 自由发挥，无显式流程约束 | 状态机驱动，确定性步骤用代码锁死 |
| 上下文输入 | 整个 DOM 或截图直接丢给 LLM | DOMExtractor 精简后的结构化可交互元素 |
| 协议开销 | 每步操作经过 JSON-RPC 序列化/反序列化 | 直接函数调用，无协议层开销 |

### 本方案的核心优势

**1. 确定性与可靠性**

状态机将流程中确定性的部分用代码固化：「申请表单填完 → 提交 → 确认页」这类流转不需要 LLM 参与决策。LLM 只负责它擅长的事 — 语义理解（识别页面类型、匹配表单字段与简历数据）。减少 LLM 参与决策的环节，就是减少不确定性的来源。

**2. 可调试性**

状态机的每一步转换都是可追踪、可记录的。出了问题可以精确定位到是哪个环节：是 DOM 提取遗漏了元素？是 LLM 的字段匹配出错？还是 ActionExecutor 执行失败？MCP 模式下 LLM 的决策链是黑盒，调试只能靠回放整个对话历史。

**3. 成本效率**

每个页面只需一次 LLM 调用（分析页面 + 生成全部操作指令），而 MCP 模式下每个原子操作（点击一个按钮、填一个字段）都是一次完整推理。批量投递 200 个职位时，token 消耗差距可达数量级。本地 7B/8B 模型在这种边界清晰的子任务上表现足够好，进一步降低成本。

**4. 容错与恢复**

代码层面的 RetryHandler 提供确定性的重试策略（指数退避、最大重试次数、异常分类处理），比依赖 LLM "自己意识到出错了然后自己修复" 可靠得多。投递记录持久化后，中断恢复也是确定性的。

**5. 执行速度**

批量生成操作指令后由代码顺序执行，省去了每步操作等待 LLM 推理的延迟。对于一个典型的 10 字段申请表单，MCP 模式可能需要 10+ 次 LLM 调用，本方案只需 1 次。

**6. 隐私安全**

简历数据全程在本机处理，通过本地模型（Ollama）完成推理，不经过任何云端 API。MCP 模式通常依赖云端大模型，简历中的个人信息会上传到第三方服务。

### 本方案的局限性

- **开发成本高**：需要完整实现三层架构（浏览器层、智能层、编排层），MCP 方案开箱即用
- **本地模型能力上限**：7B/8B 模型在复杂非标准表单、动态加载页面上的理解能力不及 GPT-4/Claude 等云端大模型
- **灵活性受限**：状态机设计过于刚性时，遇到意料之外的页面结构可能不如纯 LLM agent 灵活（通过"未知页面 → 人工介入"兜底缓解）

### 结论

本方案的设计哲学是：**用代码解决确定性问题，用 LLM 解决语义理解问题**。相比 LLM + Playwright MCP 的"全权委托"模式，这种分层策略在批量、稳定、隐私优先的简历投递场景下更具优势。两者不互斥 — 本方案本身也可以被封装为一个 MCP Server，对外暴露 `apply_to_job(url)` 等高层 tool。
