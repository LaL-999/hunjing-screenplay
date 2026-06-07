<div align="center">

# 浑晶 · 剧创态

#### 由小说,至剧本。

**HunJing · Screenplay Mode** — 一款给文学作者用的 AI 改编工作台

[![Status](https://img.shields.io/badge/状态-218%2F218%20通过-green)](#-质量基线)
[![vue-tsc](https://img.shields.io/badge/vue--tsc-0%20错-brightgreen)](#-质量基线)
[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.5-brightgreen)](https://vuejs.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](./LICENSE)

</div>

---

## 🎬 项目 Demo 视频

[![浑晶剧创态Demo演示](https://github.com/user-attachments/assets/0ce0ed86-f23e-4ae6-bd80-4a1cd256bed4)](https://b23.tv/9rgCfqI)

> 视频时长 3-5 分钟,演示从小说上传到剧本生成 + AI 优化 + 版本切换的完整闭环。
> 🔗 B 站直链:https://b23.tv/9rgCfqI

---

## 🌟 项目定位

**七牛云 1024 暑期实训营 · 题目三「AI 小说转剧本工具」**

把 ≥ 3 章节的小说**自动转换为结构化剧本(YAML)**,作者拿到的是**可编辑、可继续打磨的剧本初稿**,而不是死板的"AI 自动稿"。

剧创态是**浑晶平台**(独立开发,4 个月迭代)在已有 4 种创作态之外新增的**第 5 种创作态**。

---

## 💎 核心差异化

### 1. 作者主权:5 种专业改编手法,不替作者拍板 ⭐ 核心创新

别的 AI 工具遇到内心独白会**偷偷选 1 种处理方式**。我们提供 **5 种专业改编手法 + 利弊对照**,让作者像真正的编剧那样自己选:

| 手法 | 何时用 | 代表效果 |
|---|---|---|
| 🟣 V.O. 画外音 | 角色独特叙述声音 | 主观浸入感 |
| 🔵 动作外化 | 心理可以被身体表达 | 纯视觉、剧本化 |
| 🟤 **潜台词** ⭐ | 角色不愿直说 | 戏剧张力 + 高级感 |
| 🟢 **意象化** ⭐ | 抽象情绪需要具体载体 | 镜头语言 + 余韵 |
| ⚫ 删除 | 后续场景能替代 | 节奏紧凑 |

### 2. 人机协作优化引擎(AI 不仅诊断,还能动手改)

**单场精修**(scene 卡 → AI 优化按钮) + **整本重排**(结构报告 → 委托 AI 按诊断重写)
共用同一 LLM 引擎,产物自动入版本树,可一键回滚 / 横向对比。

### 3. 版本树(每一稿都可回溯)

```
稿 1 · 初稿
  └─ 稿 2 · 单场精修 · 第 1 场 · 3 处改动
      └─ 稿 3 · 单场精修 · 第 1 场 · 1 处改动
  └─ 稿 4 · 整本重排 · 9 处改动     (从稿 1 分叉)
```

每一稿独立保存 yaml + change_log + AI 总体思路,作者**可以横向比对接受/拒绝**。

### 4. 多维度自评分体系(AI 自检后告诉你哪里弱)

- **fidelity 4 维**:对白覆盖度 / 角色一致性 / 元素密度 / 决策完整度 — 每场打分
- **structure 3 维**:三幕分布 / 张力曲线 / 关键节点(触发事件 · 中点反转 · 高潮)
- **整体健康**:结构优秀 / 良好 / 节奏不均 / 曲线偏平 4 档

### 5. V.O. vs O.S. 工业级声音区分

剧本工业的两种"画外声"必须区分,因为导演看了立刻知道**要不要现场录音**:

| 类型 | 含义 | 录制方式 |
|---|---|---|
| **V.O.** Voice-Over | 内心独白 / 全知旁白 | 后期配音 |
| **O.S.** Off-Screen | 角色在场但镜头没拍到 | 现场录音 |

### 6. 一键导出 3 种行业格式 ⭐ 真正能拿走的剧本

不只在线展示,作者可以**直接下载文件去 Final Draft 继续打磨**:

| 格式 | 用途 |
|---|---|
| **`.fountain`** | 行业标准。Final Draft / WriterDuet / Highland 等专业软件可直接打开 |
| **`.txt`** | 中文友好排版,适合微信发送 / 打印 / 跟搭档对稿 |
| **`.yaml`** | 原始结构化数据,给工具链 / 二次开发 / 版本管理 |

---

## 🚀 三步上手(评委复现指南)

### 1. 克隆仓库

```bash
git clone https://github.com/LaL-999/hunjing-screenplay.git
cd hunjing-screenplay
```

### 2. 一键启动

**Windows**:双击 `start.bat`

启动器会自动:
- ✅ 检测 Python 3.11+ / Node 18+
- ✅ 首次运行自动 `pip install` + `npm install`
- ✅ 启动后端(:8003) + 前端(:5174)两个独立窗口
- ✅ 等后端 `/health` 通过后**自动打开浏览器**

**手动方式**:
```bash
# Terminal 1
cd backend && pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8003

# Terminal 2
cd frontend && npm install
npm run dev
```

### 3. 配置 LLM Key(可选)

```bash
cp backend/.env.example backend/.env
# 编辑 .env,填入 DEEPSEEK_API_KEY
```

未配 LLM 时,文件解析 / 校验 / CLI / 结构报告等**非 LLM 功能**可用;LLM 相关功能会返 502 友好提示。

---

## 📊 业务流程

```
┌─────────────┐  上传   ┌──────────────┐
│ .txt/.epub  ├────────►│ 章节切分     │
│ .docx 小说  │  解析   │ + 段落落库   │
└─────────────┘         └──────┬───────┘
                               │
                       ┌───────▼──────────┐
                       │ 故事圣经抽取     │ ← 多 Agent 流水线
                       │ (角色 + 地点 +   │
                       │  关键事件)       │
                       └───────┬──────────┘
                               │
              ┌────────────────┴────────────────┐
              │                                 │
       ┌──────▼──────┐                  ┌──────▼─────────┐
       │ 场景切分    │                  │ 元素抽取       │
       │ (heading +  │                  │ (action /      │
       │  范围)      │                  │  dialogue /    │
       └──────┬──────┘                  │  V.O.)         │
              │                          └──────┬─────────┘
              │                                 │
              └────────────┬────────────────────┘
                           │
                    ┌──────▼──────────┐
                    │ 对白归属精修    │ ← 代词消解
                    └──────┬──────────┘
                           │
                    ┌──────▼──────────┐
                    │ 改编决策建议    │ ← 5 种手法
                    │ (差异化创新)    │
                    └──────┬──────────┘
                           │
                    ┌──────▼──────────┐
                    │ YAML 组装 + 校验 │
                    └──────┬──────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
       ┌──────▼──────┐          ┌──────▼──────┐
       │ fidelity    │          │ structure   │
       │ 4 维评分    │          │ 报告 + 张力 │
       └─────────────┘          └─────────────┘
                           │
              ┌────────────┴────────────┐
              │ 🤖 AI 优化(可选)        │
              │ • 单场精修               │
              │ • 整本重排(可加场)      │
              └─────────────────────────┘
                           │
                    ┌──────▼──────────┐
                    │ 版本树存档      │
                    └─────────────────┘
```

---

## 🏗️ 技术架构

| 层 | 技术 | 作用 |
|---|---|---|
| 前端 | Vue 3.5 + TypeScript 5.5 + Vite 5.4 + Pinia + Vue Router | SPA 双栏编辑器 |
| 后端 | FastAPI 0.115 + Python 3.11 + Pydantic 2.x | 流水线 + 持久化 |
| 持久化 | SQLite + 双层 schema 校验(JSON Schema + 引用完整性)| 单文件数据库 |
| LLM | DeepSeek V3 (OpenAI 兼容协议)| 切分 / 抽取 / 决策 / 优化 |
| 解析 | ebooklib + python-docx + 自研 txt 分章 | 多格式入库 |
| Schema | JSON Schema Draft 2020-12 + PyYAML | 双层校验闭环 |

### 6 个 LLM Agent 流水线

| Agent | 任务 | Prompt |
|---|---|---|
| `scene_splitter` | 章节 → 场景边界 + heading | `prompts/scene_splitter.md` |
| `element_extractor` | 场景原文 → action/dialogue/V.O. 元素 | `prompts/element_extractor.md` |
| `dialogue_attributor` | 代词消解,精修对白归属 | `prompts/dialogue_attributor.md` |
| `adaptation_decision` ⭐ | 内心独白 → 5 备选 + 利弊 | `prompts/adaptation_decision.md` |
| `screenplay_optimizer` ⭐ | 人机协作重写优化 | `prompts/screenplay_optimizer.md` |
| `story_bible_extractor` | 角色 + 地点 + 事件抽取 | `prompts/story_bible_extractor.md` |

每个 agent **解耦独立可单测**,任何一个失败有兜底降级,绝不阻断主流程。

---

## ✅ 质量基线

- **后端测试**:**234 / 234 通过**(`pytest tests/`)
- **前端类型**:**vue-tsc 0 错**
- **代码量**:后端 ~6500 行 / 前端 ~5800 行 / 文档 ~1500 行
- **commit 数**:55+(从 0 commit 开始,3 天内累积)
- **合规审计**:本仓库 100% 全新代码,0 行复用浑晶平台代码,
  仅借鉴**设计思想** — 详见 [`docs/INTEGRATION_NOTES.md`](./docs/INTEGRATION_NOTES.md)

---

## 📂 仓库导览

```
hunjing-screenplay/
├── README.md                     ← 你正在看
├── start.bat                     ← Windows 一键启动
├── LICENSE
├── backend/
│   ├── app/
│   │   ├── main.py               ← FastAPI 入口
│   │   ├── routers/              ← 12 个 endpoint 路由
│   │   ├── services/
│   │   │   └── pipeline/         ← 6 个 LLM Agent
│   │   ├── prompts/              ← LLM 系统提示词(可读 .md)
│   │   ├── schemas/
│   │   │   └── screenplay.json   ← 剧本 YAML 严格 schema
│   │   └── db/
│   ├── tests/                    ← 218 pytest
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── views/                ← HomeView + ScreenplayEditorView
│   │   ├── components/           ← 9 个核心组件
│   │   ├── stores/               ← Pinia store
│   │   └── styles/               ← 文学产品视觉令牌
│   └── package.json
└── docs/
    ├── SCHEMA_DESIGN.md          ← YAML schema 深度文档
    ├── INTEGRATION_NOTES.md      ← 与浑晶平台关系
    └── 剧本术语速查.md            ← V.O./O.S./INT./EXT. 等术语
```

---

## 🎯 解决了哪些"AI 改编"行业痛点

| 痛点 | 业界常见做法 | 我们的做法 |
|---|---|---|
| 内心独白怎么改 | AI 偷偷选 1 种 | **给 5 种 + 利弊,作者拍板** |
| 改完看不出区别 | 直接覆盖 | **版本树 + change_log + 一键回滚** |
| 不知道哪里弱 | 没有评估 | **fidelity 4 维 + 结构 3 维 + 文字诊断** |
| 改不了还得手敲 | 只输出 | **AI 优化引擎(单场 / 整本)** |
| 拿不走只能在线看 | 锁在工具里 | **3 格式一键导出(.fountain / .txt / .yaml)** |
| V.O. / O.S. 分不清 | 都标 V.O. | **工业级 voice_source 区分** |
| 太短像 15 秒短切片 | 直接交付 | **prompt 加 cinema 铁律:对话回合数 ≥ 4 + 反应动作 + 拉扯感** |

---

## 🛣️ 路线图

| 阶段 | 内容 | 状态 |
|---|---|---|
| PR#1-2 | 仓库脚手架 + YAML schema 双层校验 | ✅ |
| PR#3-4 | 小说摄入 + 故事圣经抽取 | ✅ |
| PR#5-9 | 5 Agent 流水线 + 改编决策 | ✅ |
| PR#10 | YAML 组装 + 失败重试 | ✅ |
| PR#11 | 双栏对照编辑器 | ✅ |
| PR#12 | fidelity 4 维评分 | ✅ |
| PR#13 | 三幕分区 + 张力曲线 | ✅ |
| PR#15 | 小说上传 UI | ✅ |
| PR#16 | 人机协作优化 + UI 大改造 + 5 种决策升级 | ✅ |
| PR#17 | 一键导出 3 种行业格式(Fountain / TXT / YAML) | ✅ |
| PR#14 | README + demo 视频 | ✅(本文) |
| 未来 | 多角色独立 Agent(角色腔调建模) | ⏳ |

---

## 📜 与浑晶平台关系(合规声明)

| 维度 | 说明 |
|---|---|
| 本仓库 | 七牛云比赛窗口内(2026/06/05 - 2026/06/07)**100% 全新提交** |
| 代码复用 | **0 行**复用浑晶代码 |
| 借鉴 | 多 Agent 编排 / outline 图纸法 / canonical 评分 等**设计思想** |
| 运行依赖 | **不依赖**浑晶在线运行,本仓库独立 |
| 未来整合 | 故事圣经 JSON 与浑晶兼容,未来可一键导入导出 |

📄 详细:[`docs/INTEGRATION_NOTES.md`](./docs/INTEGRATION_NOTES.md)

---

## 📞 联系

- **作者** · LaL-999
- **GitHub** · [LaL-999/hunjing-screenplay](https://github.com/LaL-999/hunjing-screenplay)
- **比赛信息** · [七牛云 1024 暑期实训营 · 题目三](https://hr.qiniu.com)

---

<div align="center">

**一份小说,五种手法,十次优化。**
**让作者主权回到作者手中。**

</div>
