# 竞品对标分析

> 最后更新：2026-02-13

---

## 一、市场概览

简历自动投递赛道已被充分验证，存在大量商业产品和开源项目。核心需求明确：求职者希望减少重复填表的时间，批量投递以提高面试概率。

市场参与者可分为三类：
1. **商业 SaaS / Chrome 扩展** — 订阅制，云端处理，开箱即用
2. **开源工具** — 免费，社区驱动，需要自行配置
3. **真人代投服务** — 人工操作，质量最高，价格最贵

---

## 二、商业产品对标

| 产品 | 定价 | 投递量 | 技术路线 | 平台覆盖 | 核心特点 |
|------|------|--------|---------|---------|---------|
| [JobCopilot](https://jobcopilot.com) | $8.90-12.90/周 | 50个/天 | 云端 AI + 浏览器扩展 | 40万+公司官网 | 全自动投递，AI 生成 cover letter |
| [LazyApply](https://lazyapply.com) | $99/年起，终身 $149 | 150个/天 | Chrome 扩展 + AI 填表 | LinkedIn, Indeed, ZipRecruiter | 批量投递，JobGPT 生成回答 |
| [Sonara](https://sonara.ai) | $19.99/月起 | 10个/周 ~ 84个/月 | 云端全自动 | 多平台 | 7x24 后台运行，零操作 |
| [LoopCV](https://loopcv.pro) | $20/月(Standard), $60/月(Premium) | 最多 300个/月 | AI + 数据分析 | 20+ 招聘平台 | 简历 A/B 测试，转化率分析 |
| [Jobright](https://jobright.ai) | $19.99/月 | AI Agent 全流程 | AI Agent | 多平台 | 搜索→定制简历→投递一体化 |
| [AiApply](https://aiapply.com) | $12-23/周 | 按计划不同 | AI + 浏览器扩展 | 多平台 | 简历优化 + 自动投递 |
| [Simplify](https://simplify.jobs) | 免费增值 | 不限（手动提交） | Chrome 扩展 | 支持站点 | 一键填表，不自动提交 |
| [Scale.jobs](https://scale.jobs) | $299-1099 一次性 | 人工投递 | 真人操作 | 不限 | 90% 三个月内找到工作 |

### 商业产品共性问题

- **隐私风险**：简历数据上传至云端第三方服务器
- **投递质量参差**：LazyApply 52% 用户给最低评分，常见填错字段、答非所问
- **平台依赖**：大多针对特定招聘平台做适配，通用性有限
- **持续付费**：月均 $20-60，求职期间持续产生费用

---

## 三、开源项目对标

### 3.1 AIHawk（最主要竞品）

| 维度 | 详情 |
|------|------|
| 仓库 | [feder-cr/Jobs_Applier_AI_Agent_AIHawk](https://github.com/feder-cr/Jobs_Applier_AI_Agent_AIHawk) |
| Stars | 25,000+ |
| 技术栈 | Python + Selenium + OpenAI/Ollama/Gemini |
| 媒体报道 | Business Insider, TechCrunch, Wired, The Verge, Vanity Fair |
| 许可证 | AGPL-3.0（后转为移除第三方插件） |

#### 技术路线分析

AIHawk 采用**硬编码适配**路线：

- **起源**：LinkedIn Easy Apply 专用工具，通过 Selenium 硬编码 LinkedIn 页面的 CSS selector / XPath 定位元素
- **现状**：主仓库声称支持多平台（"scrapes job listings from corporate sites"），通过插件体系扩展，但第三方 provider plugins 已因版权问题从仓库移除
- **LLM 角色**：仅用于回答申请表单中的开放式问题 + 动态生成定制简历，不参与页面理解和导航
- **限制**：账号语言必须设为英文；每支持一个新平台需要编写一套完整的硬编码适配

#### AIHawk 的优势

1. 社区规模大（25k+ stars），问题修复快
2. LinkedIn Easy Apply 场景下非常稳定（硬编码 = 确定性高）
3. 支持 OpenAI / Ollama / Gemini 多种 LLM 后端
4. 动态简历生成功能成熟
5. 媒体背书带来的信任度

#### AIHawk 的局限

1. **平台锁定**：核心功能仅覆盖 LinkedIn Easy Apply，外部公司页面无法处理
2. **扩展成本高**：每个新平台需要完整的硬编码适配，维护负担重
3. **脆弱性**：LinkedIn 改版会导致 selector 失效，需要频繁更新
4. **无法处理外部跳转**：点击 "Apply" 跳转到公司官网（Greenhouse / Lever / Workday 等）后无能为力
5. **插件生态受损**：第三方插件因版权问题被移除，多平台支持实质上倒退

### 3.2 其他开源项目

| 项目 | Stars | 技术栈 | 覆盖范围 | 状态 |
|------|-------|--------|---------|------|
| [EasyApplyBot](https://github.com/madingess/EasyApplyBot) | 160+ | Python + Selenium | LinkedIn Easy Apply | 维护中 |
| [Auto_job_applier_linkedIn](https://github.com/GodsScion/Auto_job_applier_linkedIn) | — | Python | LinkedIn | 维护中 |
| [EasyApplyJobsBot](https://github.com/wodsuz/EasyApplyJobsBot) | — | Python | LinkedIn + Glassdoor | 维护中 |
| [auto-apply](https://github.com/simonfong6/auto-apply) | — | Python | Greenhouse, Lever, Workday, Jobvite | 硬编码适配 |
| [Apply Bot](https://apply-bot.com) | — | Playwright MCP + LLM | 通用（LLM 驱动） | 活跃 |

### 3.3 Apply Bot（技术路线最接近的竞品）

Apply Bot 是目前唯一采用 LLM + Playwright MCP 路线的产品：

- 浏览器扩展 + MCP Server + Playwright + 用户自己的 LLM
- 完全由 LLM 全权决策（纯 agent loop）
- 自然语言控制（"Apply to Software Engineer positions in Vancouver"）
- 无状态机、无结构化 DOM 提取、无确定性流程控制

---

## 四、对标矩阵：本项目 vs 竞品

| 维度 | 本项目 (ApplySlave) | AIHawk | Apply Bot | 商业产品 |
|------|-------------------|--------|-----------|---------|
| **技术路线** | 硬编码入口 + LLM 通用适配 | 全硬编码 | 全 LLM 驱动 | 云端 AI / 扩展 |
| **LinkedIn 支持** | ✅ 硬编码（稳定） | ✅ 硬编码（稳定） | ✅ LLM 驱动 | ✅ 平台适配 |
| **外部公司页面** | ✅ LLM 通用理解 | ❌ 不支持 | ✅ LLM 驱动 | 部分支持 |
| **LLM 角色** | 语义理解顾问 | 问题回答 + 简历生成 | 全权决策者 | 云端 AI |
| **流程控制** | 状态机驱动 | 硬编码脚本 | LLM 自由决策 | 平台各异 |
| **隐私** | ✅ 本地模型，数据不出机 | ⚠️ 支持 Ollama 但默认 OpenAI | ❌ 依赖用户 LLM 配置 | ❌ 云端处理 |
| **运行成本** | $0（本地模型） | API 费用（或 Ollama 免费） | API 费用 | $20-60/月 |
| **可调试性** | ✅ 状态机可追踪 | ⚠️ 脚本日志 | ❌ LLM 黑盒 | ❌ 不透明 |
| **投递质量** | 中高（结构化匹配） | 中（硬编码稳定但范围窄） | 中低（LLM 可能跑偏） | 中低（用户差评多） |
| **开发成本** | 高（三层架构） | 中（单平台硬编码） | 低（MCP 开箱即用） | 零（付费使用） |

---

## 五、关键洞察

### 5.1 市场空白

目前没有产品同时满足以下条件：
1. LinkedIn 入口稳定可靠（硬编码）
2. 外部公司页面通用适配（LLM 驱动）
3. 数据完全本地化（隐私安全）
4. 零运行成本（本地模型）

AIHawk 做到了 1 但做不到 2。Apply Bot 做到了 2 但 1 不够稳定。商业产品都做不到 3 和 4。

### 5.2 真实数据参考

- LinkedIn Easy Apply 面试率：2-3%（[来源](https://www.gighq.ai)）
- 公司官网直接申请面试率：8-12%（同上）
- 说明：能处理外部公司页面的投递，面试转化率是 Easy Apply 的 3-4 倍

### 5.3 本项目的差异化定位

```
AIHawk 的稳定性（LinkedIn 硬编码）
    + Apply Bot 的通用性（LLM 驱动外部页面）
    + 本地模型的隐私性（数据不出机）
    + 状态机的可控性（确定性流程）
    = ApplySlave 的独特价值
```

### 5.4 风险与挑战

1. **本地模型能力上限**：7B/8B 模型在复杂非标准表单上的理解能力不及 GPT-4/Claude
2. **开发工作量大**：三层架构 + LinkedIn 硬编码 + LLM 通用适配，工程量显著高于竞品
3. **LinkedIn 反自动化**：LinkedIn 持续加强反 bot 检测，硬编码方案需要持续维护
4. **社区竞争**：AIHawk 已有 25k+ stars 和媒体背书，新项目需要明确的差异化叙事

---

## 六、结论

赛道拥挤但存在明确的技术空白。本项目的"两段式架构"（LinkedIn 硬编码入口 + LLM 通用外部适配）是目前市场上没有的组合。结合本地模型的隐私优势和状态机的可控性，在开源社区有差异化竞争力。

核心叙事：**AIHawk 只能帮你点 Easy Apply，我们能帮你走完整个申请流程 — 包括跳转到公司官网之后的部分。**
