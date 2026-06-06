"""剧本结构分析 — PR#13。

输入完整 Screenplay,输出:
  - 每场 tension 分(0.0-1.0,程序级启发式)
  - 三幕分区(act 1 / 2 / 3)
  - 关键节点定位(inciting incident / midpoint / climax)
  - 整体结构健康度评分

不调 LLM(同 PR#12 fidelity_scorer 一脉相承:可复现 / 免费 / 快)。

张力计算(每场,0-1):
  - 元素密度:(action+dialogue+VO+paren) / 段落数 → 0.0-0.4
  - 对白冲突信号:'!' / '?' / 短促对白 → 0.0-0.2
  - 内心独白存在:inner monologue 元素数 → 0.0-0.15
  - 角色对抗:在场角色数(≥3 = 多方对峙)→ 0.0-0.15
  - fidelity 影响(可选):fidelity.score 高低反向调节(low = 噪声大,稍降权重)→ 0.0-0.1

三幕划分(固定比例 + 拐点修正):
  - 默认 25% / 50% / 25% 切
  - 若 tension 峰值位于第二幕末尾(75%-85%),即视为"climax"
  - 第 1 幕末尾 = 第一个 tension >= 0.5 的场景之后,作为 inciting incident
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ============================================================
# 输入 / 输出
# ============================================================


@dataclass
class StructureSceneInput:
    """单场结构分析的最小输入(从 YAML 解析得到)。"""

    scene_id: str
    number: int                        # 全局 scene 序号
    element_count: int                 # action + dialogue + voiceover + paren 总数
    dialogue_chars: int                # dialogue + VO 总字数
    inner_monologue_count: int         # is_inner_monologue=True 的 VO 数
    characters_present_count: int      # 在场角色数
    text_corpus: str = ""              # 全场文本(用于冲突信号检测)
    fidelity_score: float | None = None  # PR#12 fidelity score(可空)
    paragraph_count: int = 1


@dataclass
class TensionPoint:
    """一场的张力评分结果。"""

    scene_id: str
    number: int
    tension: float                     # 0-1
    act: int                           # 1 / 2 / 3
    is_inciting_incident: bool = False
    is_midpoint: bool = False
    is_climax: bool = False
    breakdown: dict = field(default_factory=dict)  # 各信号的子分(给前端 tooltip)

    def to_dict(self) -> dict:
        out = {
            "scene_id": self.scene_id,
            "number": self.number,
            "tension": round(self.tension, 2),
            "act": self.act,
            "breakdown": {k: round(v, 2) for k, v in self.breakdown.items()},
        }
        if self.is_inciting_incident:
            out["is_inciting_incident"] = True
        if self.is_midpoint:
            out["is_midpoint"] = True
        if self.is_climax:
            out["is_climax"] = True
        return out


@dataclass
class ActSpan:
    """单幕的场号区间。"""

    act: int                           # 1 / 2 / 3
    start_scene_number: int            # 首场(含)
    end_scene_number: int              # 末场(含)
    scene_count: int
    avg_tension: float
    peak_tension: float

    def to_dict(self) -> dict:
        return {
            "act": self.act,
            "start_scene_number": self.start_scene_number,
            "end_scene_number": self.end_scene_number,
            "scene_count": self.scene_count,
            "avg_tension": round(self.avg_tension, 2),
            "peak_tension": round(self.peak_tension, 2),
        }


@dataclass
class StructureReport:
    """完整结构报告。"""

    points: list[TensionPoint]
    acts: list[ActSpan]
    overall_health: str                # excellent | good | uneven | flat
    overall_score: float               # 0-1
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "points": [p.to_dict() for p in self.points],
            "acts": [a.to_dict() for a in self.acts],
            "overall_health": self.overall_health,
            "overall_score": round(self.overall_score, 2),
            "notes": self.notes,
        }


# ============================================================
# 主入口
# ============================================================


def analyze_structure(scenes: list[StructureSceneInput]) -> StructureReport:
    """分析整本剧本的张力曲线 + 三幕分区。"""
    if not scenes:
        return StructureReport(
            points=[],
            acts=[],
            overall_health="flat",
            overall_score=0.0,
            notes=["无可分析的场景"],
        )

    # 1. 每场算 tension
    points: list[TensionPoint] = []
    for s in scenes:
        tension, breakdown = _score_tension(s)
        points.append(TensionPoint(
            scene_id=s.scene_id,
            number=s.number,
            tension=tension,
            act=1,   # 暂设 1,稍后修正
            breakdown=breakdown,
        ))

    # 2. 划分三幕
    _assign_acts(points)

    # 3. 找关键节点
    _mark_key_beats(points)

    # 4. 算每幕统计
    acts = _build_act_spans(points)

    # 5. 整体健康度
    overall_score, overall_health, notes = _judge_overall(points, acts)

    return StructureReport(
        points=points,
        acts=acts,
        overall_health=overall_health,
        overall_score=overall_score,
        notes=notes,
    )


# ============================================================
# 张力计算
# ============================================================


# 冲突信号关键词(中文优先)
_CONFLICT_KEYWORDS = re.compile(
    r"(怒|喊|吼|质问|愤怒|拒绝|逃|争|杀|死|崩溃|决裂|失控|揭穿|对峙|质疑|不!|不行|快跑|住手|滚)",
)


def _score_tension(s: StructureSceneInput) -> tuple[float, dict]:
    """张力评分(0-1)+ 子分细节。

    权重:
      density 0.40 / conflict 0.20 / monologue 0.15 / casting 0.15 / fidelity 0.10
    """
    # 元素密度(0-0.4)— 与 fidelity 同算法,但映射不同
    density_ratio = s.element_count / max(1, s.paragraph_count)
    if density_ratio <= 1.0:
        density = 0.10
    elif density_ratio <= 2.0:
        density = 0.20
    elif density_ratio <= 4.0:
        density = 0.30
    elif density_ratio <= 7.0:
        density = 0.40
    else:
        density = 0.32

    # 对白冲突信号(0-0.2)
    conflict = 0.0
    if s.text_corpus:
        exclaim_count = s.text_corpus.count("!") + s.text_corpus.count("!")
        question_count = s.text_corpus.count("?") + s.text_corpus.count("?")
        keyword_hits = len(_CONFLICT_KEYWORDS.findall(s.text_corpus))
        conflict = min(
            0.20,
            exclaim_count * 0.03 + question_count * 0.02 + keyword_hits * 0.04,
        )

    # 内心独白(0-0.15)— 内心戏 = 转折时刻
    monologue = min(0.15, s.inner_monologue_count * 0.06)

    # 角色对峙(0-0.15)
    if s.characters_present_count <= 1:
        casting = 0.04
    elif s.characters_present_count == 2:
        casting = 0.08
    elif s.characters_present_count >= 3:
        casting = 0.15
    else:
        casting = 0.04

    # fidelity 影响(0-0.1)— 高保真场景张力计算更可信
    if s.fidelity_score is not None:
        fid = max(0.0, min(1.0, s.fidelity_score)) * 0.10
    else:
        fid = 0.05    # 中性默认

    total = min(1.0, density + conflict + monologue + casting + fid)
    breakdown = {
        "density": density,
        "conflict": conflict,
        "monologue": monologue,
        "casting": casting,
        "fidelity": fid,
    }
    return total, breakdown


# ============================================================
# 三幕分区
# ============================================================


def _assign_acts(points: list[TensionPoint]) -> None:
    """按场号 25 / 50 / 25 比例切三幕(就地修改 point.act)。"""
    n = len(points)
    if n == 0:
        return
    # 边界(向上取整保证 act 1 + act 3 至少 1 场)
    act1_end = max(1, round(n * 0.25))
    act2_end = max(act1_end + 1, round(n * 0.75))
    for i, p in enumerate(points):
        if i < act1_end:
            p.act = 1
        elif i < act2_end:
            p.act = 2
        else:
            p.act = 3


def _build_act_spans(points: list[TensionPoint]) -> list[ActSpan]:
    """按 act 分组,统计 scene_count / avg_tension / peak_tension。"""
    acts: list[ActSpan] = []
    for act_no in (1, 2, 3):
        group = [p for p in points if p.act == act_no]
        if not group:
            continue
        nums = [p.number for p in group]
        tens = [p.tension for p in group]
        acts.append(ActSpan(
            act=act_no,
            start_scene_number=min(nums),
            end_scene_number=max(nums),
            scene_count=len(group),
            avg_tension=sum(tens) / len(tens),
            peak_tension=max(tens),
        ))
    return acts


# ============================================================
# 关键节点
# ============================================================


def _mark_key_beats(points: list[TensionPoint]) -> None:
    """标记 inciting incident(act 1 末尾 tension 峰)/ midpoint / climax(act 3)。"""
    if not points:
        return

    # Climax:act 3 的 tension 最高点
    act3 = [p for p in points if p.act == 3]
    if act3:
        peak = max(act3, key=lambda p: p.tension)
        # 若 act 3 平淡,看 act 2 末尾
        if peak.tension < 0.4:
            act2 = [p for p in points if p.act == 2]
            if act2:
                peak = max(act2[-3:] if len(act2) >= 3 else act2, key=lambda p: p.tension)
        peak.is_climax = True

    # Inciting incident:act 1 末尾的 tension 最高点
    act1 = [p for p in points if p.act == 1]
    if act1:
        ii = max(act1, key=lambda p: p.tension)
        ii.is_inciting_incident = True

    # Midpoint:act 2 中段的 tension 最高点
    act2 = [p for p in points if p.act == 2]
    if act2:
        mid_start = len(act2) // 3
        mid_end = len(act2) * 2 // 3
        candidates = act2[mid_start:mid_end + 1] or act2
        mp = max(candidates, key=lambda p: p.tension)
        mp.is_midpoint = True


# ============================================================
# 整体健康度
# ============================================================


def _judge_overall(
    points: list[TensionPoint],
    acts: list[ActSpan],
) -> tuple[float, str, list[str]]:
    """综合判定 + 写人话建议。

    评分维度(每项 0-1,等权重平均):
      curve_variation:全片张力方差(波动度)
      climax_position:climax 是否在末段
      act_balance:三幕场景数比例是否合理
    """
    notes: list[str] = []

    # 1. 波动度(方差)
    tensions = [p.tension for p in points]
    if len(tensions) < 2:
        variation = 0.5
    else:
        mean = sum(tensions) / len(tensions)
        variance = sum((t - mean) ** 2 for t in tensions) / len(tensions)
        # 期望方差 0.02-0.06,映射到 0-1
        variation = max(0.0, min(1.0, variance / 0.05))
        if variation < 0.3:
            notes.append("张力曲线偏平,情节节奏单一,建议加冲突或转折")
        elif variation > 0.95:
            notes.append("张力大起大落,部分场景可能过激")

    # 2. climax 位置
    climax_pos = 0.5
    for i, p in enumerate(points):
        if p.is_climax:
            ratio = (i + 1) / len(points)
            if ratio >= 0.7:
                climax_pos = 1.0
            elif ratio >= 0.55:
                climax_pos = 0.7
            else:
                climax_pos = 0.4
                notes.append("Climax 在前半段,后续情节缺乏推进")
            break

    # 3. 三幕比例
    if len(acts) < 3:
        balance = 0.3
        notes.append("场景过少,三幕结构不完整")
    else:
        c1, c2, c3 = (a.scene_count for a in acts[:3])
        total = c1 + c2 + c3
        # 期望比例约 25 / 50 / 25
        r1, r2, r3 = c1 / total, c2 / total, c3 / total
        ideal = [0.25, 0.50, 0.25]
        dev = abs(r1 - ideal[0]) + abs(r2 - ideal[1]) + abs(r3 - ideal[2])
        balance = max(0.0, 1.0 - dev * 2)
        if balance < 0.5:
            notes.append("三幕结构比例失衡(理想约 25/50/25),建议调整场分布")

    overall_score = (variation + climax_pos + balance) / 3

    if overall_score >= 0.75:
        health = "excellent"
        if not notes:
            notes.append("张力曲线流畅,三幕结构清晰,climax 落在末段。")
    elif overall_score >= 0.5:
        health = "good"
    elif overall_score >= 0.3:
        health = "uneven"
    else:
        health = "flat"

    return overall_score, health, notes
