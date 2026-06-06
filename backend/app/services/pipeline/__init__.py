"""多 Agent 转换流水线包(每个 agent 独立 PR 加入)。

PR#6:scene_splitter — 章节 → 场景边界 + heading
PR#7:element_extractor — 场景原文 → action / dialogue / parenthetical / voiceover 元素
PR#8:dialogue_attributor — 已抽 elements 的对白归属增强(代词消解 + 上下文推断)
PR#9:adaptation_decision — 内心独白 → V.O./动作外化/删除 3 备选(差异化创新核心)
PR#10:yaml_composer — PR#6-9 各 agent 产物 → 完整剧本 YAML(纯函数层)
后续 PR(各自独立):
  PR#10 commit 3:compose_service — 编排层(失败重试 / 降级 / 持久化)
  PR#12:fidelity_scorer — 每场质量打分
"""
from .adaptation_decision import propose_decisions
from .dialogue_attributor import refine_attribution
from .element_extractor import extract_elements
from .scene_splitter import split_chapter
from .yaml_composer import assemble_screenplay

__all__ = [
    "split_chapter",
    "extract_elements",
    "refine_attribution",
    "propose_decisions",
    "assemble_screenplay",
]
