# 浑晶 · 剧创态 — HunJing Screenplay Mode

> **七牛云 1024 暑期实训营 · 题目三「AI 小说转剧本工具」**
> 把 ≥ 3 章节的小说自动转换为结构化剧本(YAML 格式),让作者快速获得可编辑、可进一步打磨的剧本初稿。

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen)]()
[![License](https://img.shields.io/badge/license-MIT-blue)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/vue-3.5-brightgreen)](https://vuejs.org/)

---

## 📖 项目简介

**剧创态(Screenplay Mode)** 是 **浑晶平台**(独立开发,4 个月迭代)新增的**第 5 种创作态**,与现有 4 态(初始态 / 中间态 / 末尾态 / 漫创态)并列。本工具帮助小说作者把作品自动改编为结构化剧本初稿,降低改编门槛。

### 与浑晶平台关系(合规声明)

| 维度 | 说明 |
|---|---|
| **本仓库** | 七牛云比赛窗口内(2026/06/05 - 2026/06/07)**100% 全新提交**,从 0 commit 开始 |
| **代码复用** | **0 行**复用浑晶代码 — 本仓库完全独立可运行 |
| **借鉴设计思想** | 借鉴浑晶的多 Agent 编排 / outline 图纸法 / canonical 评分体系等**设计思想**,但代码全部重写 |
| **运行依赖** | **不依赖**浑晶在线运行 — 本仓库自带完整人物 / 事件抽取能力 |
| **接口兼容** | 故事圣经 JSON 格式与浑晶兼容,未来可一键导入导出 |

📄 详细边界说明:[`docs/INTEGRATION_NOTES.md`](./docs/INTEGRATION_NOTES.md)

---

## ✨ 核心功能

1. **小说摄入**:支持 `.txt` / `.epub` / `.docx` 上传,自动分章 + 段落索引
2. **故事圣经抽取**:LLM 自动识别人物 / 地点 / 关系 / 事件(也支持手动导入 JSON)
3. **场景切分**:按"地点 × 时间 × 事件"跃迁判定 scene 边界,而非简单按章节
4. **逐场转换**:prose → 剧本元素(action / dialogue / parenthetical / V.O. / 闪回)
5. **改编决策摊给作者** ⭐(差异化创新):
   遇到内心独白,**不偷偷决定** — 给作者 3 备选(V.O. / 动作外化 / 删除),各自附利弊,作者拍板
6. **保真度评分**:每场 high / medium / low,low 标黄提醒作者复核
7. **YAML Schema 校验**:严格 JSON Schema 校验 + 失败自动重试
8. **双栏对照编辑器**:左原文 / 右剧本,溯源高亮
9. **剧本结构报告**:三幕分区 + 张力曲线 + 关键场景诊断

📄 Schema 设计文档(题目核心交付物):[`docs/SCHEMA_DESIGN.md`](./docs/SCHEMA_DESIGN.md)

---

## 🚀 快速开始

### 环境要求

| 工具 | 版本 |
|---|---|
| Python | 3.11+ |
| Node.js | 18+ |
| DeepSeek API key | 必填(见 §配置) |

### 1. 配置 API key

```bash
cp backend/.env.example backend/.env
# 编辑 backend/.env,填入 DEEPSEEK_API_KEY
```

### 2. 启动 backend

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8003
```

后端启动后,健康检查:`http://localhost:8003/health` 应返回 `{"status":"ok"}`

### 3. 启动 frontend

```bash
cd frontend
npm install
npm run dev
```

打开浏览器:`http://localhost:5174`

### 4. 端到端 API 示例(无需前端,curl 即可演示)

启动后端后,以下三步即可走完整套流水线:

```bash
# 1) 摄入小说(返 novel_id)
curl -X POST http://localhost:8003/novels \
  -F "file=@your_novel.txt"

# 2) 自动抽取故事圣经(可选,compose 会自动触发)
curl -X POST http://localhost:8003/novels/{novel_id}/story-bible/auto

# 3) 一键编排:小说 → 剧本 YAML(差异化创新核心 — 改编决策摊给作者)
curl -X POST http://localhost:8003/novels/{novel_id}/compose-screenplay \
  -H "Content-Type: application/json" \
  -d '{}'                                      # 全选项默认即可

# 后续查询(秒响应,无需 LLM)
curl http://localhost:8003/novels/{novel_id}/screenplay     # 最新版本
curl http://localhost:8003/screenplays/{screenplay_id}      # 特定版本
```

`POST /compose-screenplay` 返回完整 YAML + stats + warnings + failed_chapters。
所有 4 个 LLM agent(scene_splitter / element_extractor / dialogue_attributor /
adaptation_decision)按 PR#6-9 编排串联,任一 agent 失败都有降级路径,**不会**
让单点 LLM 嘴瓢导致整本剧本崩盘。详见 [`docs/SCHEMA_DESIGN.md`](./docs/SCHEMA_DESIGN.md)。

---

## 🏗 技术栈

| 层 | 技术 |
|---|---|
| **后端** | Python 3.11 / FastAPI / SQLite / Pydantic |
| **前端** | Vue 3 / TypeScript / Vite |
| **LLM** | DeepSeek V3 (`deepseek-chat`) via OpenAI 兼容协议 |
| **解析** | ebooklib(.epub)/ python-docx(.docx)/ 自研 txt 分章 |
| **校验** | jsonschema(严格 JSON Schema 机器校验) |
| **YAML** | PyYAML 6.x |

### 完整第三方依赖

详见 [`backend/requirements.txt`](./backend/requirements.txt) 和 [`frontend/package.json`](./frontend/package.json)。

---

## 📁 项目结构

```
hunjing-screenplay/
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── main.py          # 入口 + /health
│   │   ├── config.py        # 配置 + .env 加载
│   │   ├── routers/         # API 路由
│   │   ├── services/        # 业务逻辑(场景切分 / 转换 / 评分)
│   │   ├── schemas/         # Pydantic + JSON Schema
│   │   └── prompts/         # LLM prompt 模板
│   ├── tests/               # pytest 测试集
│   ├── .env.example
│   └── requirements.txt
│
├── frontend/                # Vue 3 + Vite 前端
│   ├── src/
│   │   ├── App.vue
│   │   ├── main.ts
│   │   ├── views/           # 页面(双栏编辑器 / 结构报告)
│   │   ├── components/      # 复用组件
│   │   └── api/             # HTTP 客户端
│   ├── package.json
│   └── vite.config.ts
│
└── docs/
    ├── INTEGRATION_NOTES.md # 与浑晶的边界声明(合规)
    ├── SCHEMA_DESIGN.md     # YAML Schema 设计文档(题目要求)
    └── DEMO_VIDEO_SCRIPT.md # demo 视频讲解脚本
```

---

## 🎥 Demo 视频

📺 演示视频:_待录制(Day 3 最后阶段上传 bilibili)_

视频覆盖:
1. 摄入 → 自动分章
2. 故事圣经抽取(人物 / 关系 / 事件)
3. 场景切分演示
4. 逐场转换(重点演示内心戏处理 ⭐)
5. YAML 产物 + 校验报告
6. 双栏对照编辑 + 单场重生成
7. 保真度评分 + 结构报告

---

## 🛠 开发节奏(过程合规)

按七牛云比赛规范,所有 commit 时间戳落在 **2026/06/05 - 2026/06/07** 窗口内。

| 日期 | 完成 PR |
|---|---|
| 2026/06/05 | PR#1-3(基础脚手架 + Schema 文档)|
| 2026/06/06 | PR#4-10(故事圣经 + 场景切分 + 逐场转换流水线)|
| 2026/06/07 | PR#11-14(UI + fidelity + 结构报告 + demo)|

每个 PR 详见 [Pull Requests](https://github.com/YOUR_USER/hunjing-screenplay/pulls)。

---

## 📜 License

[MIT](./LICENSE) © 2026 浑晶 · 剧创态

---

## 🙏 致谢

- 父平台 **浑晶**:为本工具贡献了多 Agent 编排 / outline 图纸法 / canonical 评分等设计思想
- **DeepSeek**:V3 模型提供商
- **七牛云 1024 实训营**:本项目的起点
