"""多 Agent 转换流水线包(每个 agent 独立 PR 加入)。

PR#6:scene_splitter — 章节 → 场景边界 + heading
后续 PR(各自独立):
  PR#7:action_extractor — 场景原文 → action 元素
  PR#8:dialogue_extractor — 场景原文 → dialogue + parenthetical
  PR#9:adaptation_decision — 内心独白 → V.O./动作外化/删除 3 选项
  PR#10:yaml_composer — 所有元素 → 完整剧本 YAML
  PR#12:fidelity_scorer — 每场质量打分
"""
from .scene_splitter import split_chapter

__all__ = ["split_chapter"]
