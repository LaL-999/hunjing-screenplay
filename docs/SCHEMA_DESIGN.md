# 剧本 YAML Schema 设计文档

> 本文档说明:**为什么剧本 YAML Schema 长成这个样子**。
> 评分逻辑提示:题目特别要求"额外写一篇文档,定义剧本的 YAML Schema。文档中需说明该 Schema 的设计原因" — 这是强信号,**评委不评你能不能写 YAML,评你为什么这么写**。

---

## 1. 核心设计原则(取舍清单)

| # | 原则 | 取舍 |
|---|---|---|
| 1 | **稳定 ID** | 每个 scene / element 有不变 `id`,支持"改某场再局部重生成" |
| 2 | **元素分型** | `action / dialogue / parenthetical / transition` + 难点项 `voiceover / flashback_start / flashback_end` |
| 3 | **结构与内容分离** | 场景头(`heading`)独立于正文(`elements`) |
| 4 | **可溯源** | 每场挂 `source.chapter` + `source.paragraph_range` |
| 5 | **保真度标记** | `fidelity` 字段,转换有损时主动标黄 |
| 6 | **改编决策保留** | `adaptation_decisions` 字段,记录每次"内心戏 → V.O. / 动作 / 删除"的选择 |
| 7 | **校验友好** | 配套 JSON Schema,机器可校验 |
| 8 | **为什么 YAML 而非 JSON** | 人类可读、可手改、能写注释 — 草稿气质契合 |

---

## 2. 为什么走 YAML(对比 Fountain / FDX / JSON)

### 2.1 Fountain(纯文本标记)

**优点**:工业界标准,人写人读,支持 Final Draft / Highland / Trelby 等工具导入。

**缺点**:
- 半结构化 — 程序读取时仍要正则识别"INT./EXT."、行首大写人名等
- 无稳定 id,改某场重生成时无法保证 elements 对齐
- 无"保真度 / 改编决策"等元数据

**结论**:Fountain 作为**导出格式**(supported),但**核心 schema 用 YAML** + 工具内可一键导出 Fountain。

### 2.2 FDX(Final Draft XML)

**优点**:工业用户友好。

**缺点**:
- XML 难读难手改 — 草稿气质完全错位
- 闭源标准,文档稀缺
- 我们的目标用户(小说作者)**没人用 Final Draft**,导出价值低

**结论**:不作为核心 schema,**未来加导出接口**(优先级低)。

### 2.3 JSON

**优点**:程序友好,前后端栈成熟。

**缺点**:
- 不能写注释 — 而剧本草稿**最需要注释**("此处考虑改为 V.O.")
- 引号 + 转义对中文长字符串极不友好(双引号 + `\"` 嵌套)
- 缺少 YAML 的 `|`(literal block)/ `>`(folded block),长段对白只能堆 `\n`

**结论**:JSON 适合"机器之间传输",不适合"作者改的草稿"。

### 2.4 YAML(我们的选择)

**优点**:
- **可注释**:`# 这场考虑改成 V.O.` 直接写在行末
- **长字符串友好**:`|` 保留换行,`>` 折叠段落
- **结构清晰**:缩进就是层级,中文场景下肉眼可读
- **可机读**:配套 JSON Schema 仍可强校验
- **可双向**:作者改 YAML 后回流 → 程序再处理 → 不失结构

**唯一痛点**:对缩进敏感 — 通过"编辑器渲染视图"屏蔽,作者不直接面对 YAML。

---

## 3. Schema 核心结构

```yaml
# YAML 顶层 — 4 段:meta / characters / locations / scenes
meta:                           # 剧本元数据
characters:                     # 人物档案(来自故事圣经)
locations:                      # 地点档案(来自故事圣经)
scenes:                         # 场景数组(剧本主体)
adaptation_decisions:           # 改编决策审计(创新点)
```

### 3.1 `meta` 段

```yaml
meta:
  schema_version: "1.0"
  title: "孤独的钟表匠"
  source:
    novel_title: "原小说标题"
    adapted_from_chapters: [1, 2, 3]
  logline: "三十岁钟表匠林深修复一只来自母亲遗物的怀表,故事在第三个雨夜揭开他童年的失踪谜团。"
  generated_by:
    platform: "浑晶 · 剧创态"
    schema_version: "1.0"
    model: "deepseek-chat"
    generated_at: "2026-07-15T14:30:00Z"
  stats:                         # 程序生成后填,作者参考
    total_scenes: 18
    total_pages_estimate: 22     # 1 页 ≈ 1 分钟剧本时长
    high_fidelity_scenes: 12
    medium_fidelity_scenes: 5
    low_fidelity_scenes: 1       # 标黄需复核
```

**为什么有 `stats`**:作者看到"18 场 / 22 分钟 / 1 场低保真"能秒判产物完整度,**不用翻完才知道哪里有问题** — 这是给作者的"产物体检报告"。

### 3.2 `characters` / `locations` 段

```yaml
characters:
  - id: char_001
    name: "林深"
    aka: ["林先生", "老板"]      # 别名,用于对白归属时辅助代词消解
    description: "三十岁,沉默寡言的钟表匠"
    first_appearance: scene_001
    arc_summary: "从封闭到坦诚"   # 可选,源自浑晶 character_drivers

locations:
  - id: loc_001
    name: "老城钟表铺"
    int_ext: INT                 # INT | EXT | INT/EXT
    description: "堆满旧钟的逼仄店面,煤油灯 + 怀旧氛围"
    first_appearance: scene_001
```

**为什么独立成段**:**结构与内容分离铁律**。同一个角色出现在 15 个场景里,改 description 一次即可,scene 里只引 `char_001`。

**`aka` 字段为什么必要**:小说里"林深"、"林先生"、"他"、"老板"指同一人 — 对白归属需要 alias 表辅助。这个字段是产物质量的关键。

### 3.3 `scenes` 段(核心)

```yaml
scenes:
  - id: scene_001
    number: 1
    heading:                     # 场景头(场景标题三件套)
      int_ext: INT
      location_id: loc_001
      time_of_day: 日             # 日 | 夜 | 黄昏 | 黎明 | 连续(连接上一场)
    summary: "林深修表时,陌生女子推门而入。"
    characters_present: [char_001, char_002]  # 本场出场角色
    source:                      # 可溯源(关键)
      chapter: 1
      paragraph_range: [3, 9]
    fidelity:                    # 保真度(关键创新)
      level: high                # high | medium | low
      reason: "原文动作明确,几乎无需改编"
      issues: []                 # low 时填具体问题
    transition_to_next: CUT_TO   # 与下场的过渡(CUT_TO | FADE_OUT | DISSOLVE_TO | MATCH_CUT)
    elements:                    # 本场元素数组
      - type: action             # 动作
        id: el_001_001
        text: "林深低头打磨齿轮。门铃响。他没抬头。"
      - type: dialogue           # 对白
        id: el_001_002
        character_id: char_002
        parenthetical: "(声音发抖)"   # 表演提示,圆括号
        text: "你能修好它吗?"
      - type: voiceover          # 画外音(内心独白外化)
        id: el_001_003
        character_id: char_001
        text: "我一眼认出那是父亲的怀表。"
        adaptation_note: |
          原文为内心独白。
          作者:此条若不想要,可换为 action 外化(LLM 已生成备选:见 adaptation_decisions[0])
      - type: parenthetical      # 独立的表演说明
        id: el_001_004
        text: "门外雨声渐大。"
      - type: transition         # 过渡指示
        id: el_001_005
        text: "CUT TO:"
```

**为什么 `voiceover` 单独成型**:**剧本与小说最大的语法差** = 内心戏处理。Schema 显式编码 V.O. 类型,避免把内心戏混在 `action` 里(那就退化成"小说式叙述")。

**为什么 `adaptation_note` 字段**:每条 V.O. 旁边附 LLM 推荐"作者可改为 X / Y"。这是 **chat 标的 D3 加分项**,我们做满。

**为什么 `parenthetical` 独立类型**:不只是对白的子项 — 还能作为独立的"场景中插入的表演说明"使用(如"门外雨声渐大"),给场景写氛围。

### 3.4 `adaptation_decisions` 段(差异化创新)

```yaml
adaptation_decisions:
  - id: dec_001
    scene_id: scene_001
    element_id: el_001_003
    original_text: |
      林深心里咯噔一下。他知道,那是父亲三十年前丢失的怀表。
      记忆涌上来 ——
    options:                     # LLM 给作者的 3 选项
      - type: voiceover
        text: "我一眼认出那是父亲的怀表。"
        pros: "保留主观视角,情感直接"
        cons: "依赖 V.O.,部分导演不喜欢"
      - type: action_externalize
        text: "林深的手指猛地一颤,齿轮跌在桌上,发出脆响。"
        pros: "纯视觉,更剧本化"
        cons: "丢失'认出'的明确性,需后续场景补"
      - type: delete
        rationale: "若紧接的对白能体现父子线,此条可删"
    chosen: voiceover            # 作者选择
    chosen_at: "2026-07-15T15:02:00Z"
```

**为什么这个 schema 字段必要**:
1. **审计**:作者哪些场改成什么,记录在产物里
2. **可回滚**:作者后悔了能看 LLM 备选
3. **训练数据**:积累后可微调"什么样的内心戏适合什么改编"
4. **演示亮点**:demo 视频里这是**最容易打动评委**的画面

---

## 4. JSON Schema 校验配套(加分项)

附 `schema.json` 严格校验:
- `scene.id` 必须 `^scene_\d{3,4}$` 模式
- `element.type` 枚举 6 种,不可扩展(防 LLM 幻觉新类型)
- `fidelity.level` 必须三选一
- `character_id` 必须在 `characters[].id` 中存在
- `location_id` 必须在 `locations[].id` 中存在

**校验机制**:每次 LLM 生成 YAML → `yaml.safe_load` → `jsonschema.validate`。失败 → 局部修复 prompt → 重试 2 次。

---

## 5. 为什么不做的事(刻意取舍)

| 不做 | 原因 |
|---|---|
| 镜头号 / 分镜稿 | 剧本是给导演的图纸,不是给摄影师的分镜 — 越界 |
| 字幕时间码 | 剧本到字幕是后期工作 — 越界 |
| 音乐 / 音效详细标注 | 编剧只标"音乐起",具体音效是后期 |
| 角色情绪量化(0-100) | 不可量化,留给演员发挥 |
| 自动化 PDF 排版 | 工程量大,导出 `.fountain` 后用 Highland / Beat 等成熟工具排版即可 |

---

## 6. 演进路线(schema_version 字段)

| 版本 | 计划新增 |
|---|---|
| 1.0(MVP) | 当前文档定义的所有字段 |
| 1.1 | 多语言剧本(双语对白)|
| 1.2 | 场景 reorder 历史(版本控制) |
| 2.0 | 协作签注(评论 / 修改建议) |

**`meta.schema_version` 必填**,程序读 YAML 时按 version 走兼容路径。
