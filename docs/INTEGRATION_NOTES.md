# 浑晶 ⇄ 剧创态(参赛仓库)集成边界说明

> 本文档说明:**本参赛仓库 `huimeng-screenplay` 与父平台「浑晶」之间的代码 / 语义 / 数据边界**。
> 撰写目的:符合七牛云比赛合规要求(临尾突击 / 复用未注明 = 无效作品),提前透明声明哪些是窗口内全新开发、哪些是父平台外部依赖。
> 撰写时间:开题瞬间(将作为参赛仓库的**第 1 个 commit**)。

---

## 1. 父平台「浑晶」简介

- **作品定位**:AI 灵魂续写平台,作者使用 LLM 进行小说生成 / 改编 / 推演
- **独立开发**:作者本人(独立开发者),2026 年完整迭代周期 4+ 月
- **技术栈**:Vue 3 + TypeScript + FastAPI + SQLite + DeepSeek V3 + Qwen-VL Vision + 自研多 Agent 编排(director / agent / composer / canonical_guardian)
- **现有创作态**:
  - **初始态**:从故事内核 / 角色驱动 / 知识边界 / 伏笔账本 / 视角扩展开始生成
  - **中间态**:上传现有作品(.txt / .epub / .docx),AI 自动抽取人物 / 关系 / 事件
  - **末尾态**:接续原作末段语体,自然延展
  - **漫创态**:AI 转漫画(漫画家 / 镜头 / 场景调度)
- **本次新增**:**剧创态** — 小说 → 结构化剧本 YAML(本参赛仓库实现)

## 2. 比赛合规边界声明(关键)

| 维度 | 说明 |
|---|---|
| **本仓库代码** | **窗口内 100% 全新提交**,从 0 commit 开始,每个 commit 时间戳落在赛题窗口内 |
| **复用父平台代码** | **无**(0 行)— 不搬旧代码进本仓库 |
| **借鉴父平台架构思路** | 有 — 多 Agent 编排 / outline 图纸方法论 / canonical 评分等**设计思想**借鉴,但代码全部重写,API 完全独立 |
| **接口语义同构** | 有 — 故事圣经 JSON / 反事实改编决策 / fidelity 评分 等数据格式与父平台保持兼容,这样未来浑晶用户能一键导入 / 导出 |
| **运行时依赖父平台** | **无** — 本仓库独立可跑,不依赖浑晶 backend 在线 |

## 3. 数据流边界

```
┌─────────────────────┐              ┌─────────────────────────┐
│  浑晶平台(外部)     │              │ 本参赛仓库 huimeng-screenplay │
│                      │              │                              │
│ ① 用户上传小说       │              │ ② 用户上传小说              │
│ ② 中间态抽取人物事件 │ ─ JSON 导出 ─▶│ ② 本地抽取人物事件          │
│ ③ outline 推演       │              │ ③ 剧本场景切分              │
│ ④ narrative 生成     │              │ ④ 逐场 prose → 剧本元素     │
│                      │              │ ⑤ YAML Schema 校验          │
│                      │              │ ⑥ 双栏编辑 + fidelity 评分  │
│                      │              │ ⑦ 导出 .yaml / .fountain / .pdf │
└─────────────────────┘              └─────────────────────────┘
```

**关键合规点**:本仓库**自带完整的人物/事件抽取**,不依赖浑晶运行时。但**接口 JSON 格式**与浑晶兼容,从而:
- 浑晶用户可一键导出故事圣经到本工具
- 本工具的剧本产物可一键回流浑晶(未来)

## 4. 借鉴父平台架构思想(全部代码重写)

### 4.1 Outline-First 图纸法

**借鉴自浑晶**:`outline_generator.create_outline_draft` 设计哲学 — "不要一锤子让 LLM 写,先生成全篇 outline 图纸,再逐幕落地"。

**剧创态如何应用**:
- 第 1 步:LLM 生成全剧本 outline(每场 heading / characters / summary / key_actions),用户审核
- 第 2 步:逐场转换 prose → 剧本元素(action / dialogue / parenthetical / V.O.)

**代码独立性**:借鉴方法论,不复用代码。`backend/app/services/screenplay_planner.py` 全新实现。

### 4.2 多 Agent 编排

**借鉴自浑晶**:director-agent-composer 三角架构 — director 给 plan,agent 演角色,composer 拼叙事。

**剧创态如何应用**:
- **scene_splitter**(同构 director):判定场景边界 + 输出 scene heading
- **element_extractor**(同构 agent):每场内提取 action / dialogue / parenthetical
- **screenplay_composer**(同构 composer):拼成完整 YAML + 失败重试

**代码独立性**:全新 prompt 设计,全新 Python 模块,不 import 浑晶任何文件。

### 4.3 Canonical Guardian 评分体系

**借鉴自浑晶**:12 维 LLM-as-judge 给作品打分。

**剧创态如何应用**:为每场剧本产物算 **fidelity score**(high / medium / low),标黄提示作者复核。维度:
- 内心戏是否合理外化
- 对白归属是否准确
- 场景边界是否清晰
- 时空过渡是否顺滑

**代码独立性**:`backend/app/services/fidelity_scorer.py` 全新实现,prompt 完全重写。

### 4.4 反事实改编决策

**借鉴自浑晶**:反事实工作台让用户改写角色 / 事件 / 世界观。

**剧创态如何应用**(**核心差异化创新**):
遇到内心独白,**不自动决策**,而是给作者 3 选项:
1. 转 V.O.(画外音)
2. 动作外化(转可见动作)
3. 删除(承认无法剧本化)

每个选项 LLM 输出预览,作者拍板。

**代码独立性**:`backend/app/services/adaptation_decision.py` 全新实现。

## 5. 第三方依赖(全部在 README 列明)

| 依赖 | 用途 | License |
|---|---|---|
| FastAPI | 后端 HTTP 框架 | MIT |
| SQLite (stdlib) | 本地数据持久化 | Public Domain |
| OpenAI Python SDK | 调 DeepSeek OpenAI 兼容端点 | Apache 2.0 |
| Vue 3 + TypeScript | 前端 UI | MIT |
| Vite | 前端构建 | MIT |
| Pydantic | API schema 校验 | MIT |
| PyYAML | YAML 生成 + 解析 | MIT |
| jsonschema | JSON Schema 机器校验 | MIT |
| python-docx / ebooklib | .docx / .epub 解析 | MIT |

**LLM 模型**:DeepSeek V3 (`deepseek-chat`) via OpenAI 兼容协议。在 README 详细列明 API 端点 + 模型版本。

## 6. 部署边界

| 维度 | 说明 |
|---|---|
| **本地运行** | `backend/` + `frontend/` 各自跑,5173 / 8001 端口 |
| **依赖浑晶在线** | ❌ 否 — 本仓库自带完整功能 |
| **是否公开 demo 站** | 时间允许会部署,优先保证本地一键复现 + README 清晰 |

## 7. 复用注明(每个 PR 描述里的强制写法)

凡是借鉴浑晶**设计思想**的 PR(代码全新),PR 描述里加固定段:

```markdown
### 复用声明
本 PR 的【模块名】借鉴自父平台浑晶的【对应模块名】设计思想,但**代码全部窗口内全新提交**。
- 浑晶对应模块:`backend/app/services/<original>.py`
- 借鉴的核心思想:【一句话】
- 本 PR 代码与浑晶的关系:**0 行复用,prompt 重写,模块独立**
```

这样合规 + 评委一眼能看出"作者了解父平台架构,选择独立实现而非搬运"— **变合规风险为加分项**。
