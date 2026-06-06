"""多 Agent 转换流水线包(每个 agent 独立 PR 加入)。

PR#6:scene_splitter — 章节 → 场景边界 + heading
PR#7:element_extractor — 场景原文 → action / dialogue / parenthetical / voiceover 元素
PR#8:dialogue_attributor — 已抽 elements 的对白归属增强(代词消解 + 上下文推断)
后续 PR(各自独立):
  PR#9:adaptation_decision — 内心独白 → V.O./动作外化/删除 3 选项
  PR#10:yaml_composer — 所有元素 → 完整剧本 YAML
  PR#12:fidelity_scorer — 每场质量打分
"""
from .dialogue_attributor import refine_attribution
from .element_extractor import extract_elements
from .scene_splitter import split_chapter

__all__ = ["split_chapter", "extract_elements", "refine_attribution"]
