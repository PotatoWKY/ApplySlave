# 竞品对标分析 v2

> 基于新架构（ATS API + Mac App）的更新版本

---

## 一、重新定位

v2 的 Hamster 不再跟 AIHawk 直接竞争（AIHawk 是 LinkedIn Easy Apply 工具）。新的竞争维度：

1. **合规、零封号风险** vs AIHawk 的 LinkedIn ToS 违规
2. **原生 Mac App 体验** vs 所有现有工具的 Chrome 扩展 / CLI 形态
3. **本地模型 + 一键安装** vs 所有工具的云端 AI 或复杂安装
4. **面向"外部申请"场景** vs 现有工具专注的 "Easy Apply"

---

## 二、关键数据参考

### 面试转化率对比

| 申请渠道 | 面试率 | 数据源 |
|---------|-------|--------|
| LinkedIn Easy Apply | 2-3% | [gighq.ai](https://www.gighq.ai/how-to-navigate-linkedin-in-2026/), [tryapt.ai](https://www.tryapt.ai/blog/linkedin-easy-apply-vs-company-website) |
| 公司官网直接申请 | 8-12% | 同上 |

直接申请公司官网的转化率是 Easy Apply 的 **3-4 倍**。这是 v2 方向的核心数据支撑。

### LinkedIn 封号风险

- 2026 年 [23% 自动化用户遭遇账号限制](https://www.outx.ai/blog/linkedin-automation-safety-guide-best-practices-2026)
- Quora 上有用户反馈 5-7 个连接请求就被限制
- LinkedIn 官方明确表示不允许第三方自动化工具（[Business Insider](https://www.businessinsider.com/using-ai-apply-jobs-aihawk-linkedin-risks-rewards-resume-application-2024-11)）

---

## 三、竞品矩阵（v2 更新）

### 3.1 商业产品

| 产品 | 定价 | 平台形态 | 风险 / 限制 |
|------|------|---------|------------|
| [JobCopilot](https://jobcopilot.com) | $8.90-12.90/周 | 云端 + 浏览器扩展 | 简历上传云端，有隐私风险 |
| [LazyApply](https://lazyapply.com) | $99/年起 | Chrome 扩展 | 只做 LinkedIn/Indeed，用户评价差（52% 最低评分） |
| [Sonara](https://sonara.ai) | $19.99/月起 | 云端全自动 | 质量低，2024 年一度关闭 |
| [LoopCV](https://loopcv.pro) | $20-60/月 | 云端 + AI | 有 A/B 测试，数据驱动 |
| [Jobright](https://jobright.ai) | $19.99/月 | 云端 AI Agent | 全流程自动化 |
| [Apply Bot](https://apply-bot.com) | — | Chrome 扩展 + MCP Server | 用 LLM 完全驱动，不稳定 |
| [Scale.jobs](https://scale.jobs) | $299-1099 一次性 | 真人代投 | 人工，质量最高但最贵 |

**共性**：
- 全部依赖云端 AI（简历上传风险）
- 大多针对特定平台（LinkedIn / Indeed）硬编码
- 按月订阅，长期成本高

### 3.2 开源项目

| 项目 | Stars | 技术栈 | v2 的差异化 |
|------|-------|--------|------------|
| [AIHawk](https://github.com/feder-cr/Jobs_Applier_AI_Agent_AIHawk) | 25k+ | Python + Selenium + GPT | 我们走 ATS API，不碰 LinkedIn ToS 灰色地带 |
| [EasyApplyBot](https://github.com/madingess/EasyApplyBot) | 160+ | Python + Selenium | LinkedIn 专用，我们覆盖范围广 |
| [Auto_job_applier_linkedIn](https://github.com/GodsScion/Auto_job_applier_linkedIn) | — | Python | 同上 |
| [auto-apply](https://github.com/simonfong6/auto-apply) | — | Python | 硬编码 ATS，不灵活 |
| [Apply Bot](https://apply-bot.com) | — | Playwright MCP + LLM | LLM 全权决策，不稳定 |

### 3.3 AIHawk 的局限（v2 重新审视）

AIHawk 技术路线本质问题：

1. **只能处理 LinkedIn Easy Apply** — 跳转到公司官网就无能为力
2. **硬编码每个平台** — 扩展到新平台成本极高，所以第三方 plugins 被移除
3. **LinkedIn ToS 违规** — 用户自担封号风险
4. **Python 脚本形态** — 普通用户跑不起来（BI 报道里专门提到需要 Python 背景）

---

## 四、Hamster v2 的独特定位

```
合规的 ATS API（零封号风险）
    + 跨平台桌面 App（macOS + Windows + Linux）
    + 本地 LLM（隐私 + 零成本）
    + LLM 驱动的通用表单适配（覆盖任何外部页面）
    + 一键安装（.dmg / .exe / .AppImage 下载即用）
    = 市场空白
```

### 4.1 对标矩阵

| 维度 | AIHawk | Apply Bot | JobCopilot | **Hamster v2** |
|------|--------|-----------|------------|-------------------|
| 合规 | ❌ 违反 LinkedIn ToS | ⚠️ 看 LLM 操作 | ✅ | ✅ 用公开 API |
| 封号风险 | 高 | 中 | 低 | **零** |
| 隐私 | ⚠️ 用户选 LLM | ⚠️ 用户选 LLM | ❌ 云端 | **✅ 本地模型** |
| 运行成本 | API 费用 | API 费用 | $20-50/月 | **$0** |
| 用户门槛 | 需要 Python | 需要 Chrome | 需要注册付费 | **双击 .dmg/.exe** |
| 跨平台 | macOS/Linux（CLI） | 浏览器扩展 | Web/扩展 | **✅ Mac + Win + Linux 原生** |
| 外部页面支持 | ❌ | ✅ | 部分 | **✅ 全面** |
| 面试转化率（数据）| 2-3%（Easy Apply） | 不定 | 不定 | **8-12%（外部申请）** |
| App 体积 | - | - | - | **~500MB（Tauri 比 Electron 小 5-10 倍）** |

---

## 五、核心叙事

给不同用户的一句话定位：

- **对开发者 / Reddit / HN 社区**：
  > "AIHawk 让你在 LinkedIn 上刷 Easy Apply，我们让你用 AI 填完所有公司官网的申请表。本地跑，零封号风险，Mac 原生 app。"

- **对非技术用户**：
  > "找工作投简历太烦？下载这个 App，填好信息一次，它帮你自动投递到 Greenhouse、Lever 等数千家公司官网。完全本地运行，你的简历不会泄露。"

- **对隐私敏感用户**：
  > "不像 JobCopilot / LazyApply 那些云端工具，你的简历永远不会离开你的电脑。AI 在本地跑，数据你自己掌控。macOS、Windows、Linux 都支持。"

---

## 六、风险评估

| 风险 | 影响 | 缓解 |
|------|------|------|
| 打包工程量大 | 可能延期 | 分两阶段，先做 CLI 再做 Desktop App |
| 本地模型能力上限 | 复杂表单可能失败 | 加人工介入兜底 + 持续 prompt 优化 |
| 代码签名费用 | macOS $99/年 + Windows 证书 | 可以先发无签名版本，用户手动绕过 |
| Playwright Chromium 打包大 | 下载体积 500MB+ | 可接受（Docker Desktop 都 600MB） |
| 公司官网反爬 | 可能被封 IP | 单用户场景频率低，风险远低于 LinkedIn |
| ATS API 变更 | 需要持续维护 | 每个 source 独立 package，改动范围小 |
| WebView 跨平台差异 | macOS Safari vs Windows Chromium | 前端代码简单，兼容性压力小 |
| 三平台 CI 配置 | 初期 CI 不稳定 | GitHub Actions 有成熟 Tauri action |

---

## 七、结论

v2 架构定位清晰：做所有现有工具都做不了的事——合规、隐私友好、用户友好、跨平台的一键式桌面 app。

核心差异化不是"更好的 LinkedIn 自动化"（那是 AIHawk 的战场），而是**根本不碰 LinkedIn 这个雷区，做一个更有价值的场景（公司官网申请），并且覆盖 macOS + Windows + Linux 三个平台**。
