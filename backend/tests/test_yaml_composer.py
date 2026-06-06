"""yaml_composer 测试 — PR#10 commit 1(纯组装层)。

测试矩阵(23 case):

ID 编号(6):
  1. char_NNN 按 bible 顺序编号
  2. loc_NNN 按场景首次出现顺序 + 同名复用
  3. scene_NNN 跨 chapter 全局连续
  4. el_NNN_MMM 双段编号正确
  5. dec_NNN 全局连续
  6. aka 映射到主 name 的 char_id

scenes / elements(5):
  7. characters_present name → char_id 转换 + 去重
  8. dialogue / voiceover character_name → character_id 转换
  9. action / parenthetical 不需要 character_name
 10. dialogue 角色未在 bible → 跳过 + warning
 11. 整场 elements 全被过滤 → scene 跳过 + warning(后续 scene_NNN 不空洞)

decisions(3):
 12. element_index 0-based → element_id 正确
 13. 关联 element 被过滤 → decision 跳过 + warning
 14. 本场被跳过 → 关联 decisions 跳过 + warning

可选字段(4):
 15. transition_to_next 空字符串 → 不写入 yaml(避免 schema 枚举失败)
 16. transition_to_next 有值 → 写入
 17. summary / source 写入正确
 18. 中文 location 在 yaml 输出不被 escape

致命错误(3):
 19. 空 bible.characters → ComposeError
 20. 空 scenes 输入 → ComposeError
 21. 所有 scene 都被过滤 → ComposeError

最终通过校验(2):
 22. 组装后 yaml_validator.validate_screenplay_yaml 通过
 23. meta.schema_version / generated_by.platform / stats 正确
"""
from __future__ import annotations

import pytest

from app.services.pipeline.adaptation_decision import (
    AdaptationDecision,
    AdaptationOption,
)
from app.services.pipeline.element_extractor import ScreenplayElement
from app.services.pipeline.scene_splitter import SceneHeading
from app.services.pipeline.yaml_composer import (
    ComposeError,
    ComposeInput,
    SceneAssembleData,
    assemble_screenplay,
)
from app.services.yaml_validator import validate_screenplay_yaml


# ============================================================
# Helpers
# ============================================================


def _make_bible(
    chars: list[dict] | None = None,
    locs: list[dict] | None = None,
) -> dict:
    """造一个最小可用的 bible(默认 2 角色)。"""
    if chars is None:
        chars = [
            {"name": "林墨", "aka": ["阿墨"], "description": "主角,记者"},
            {"name": "苏清", "aka": ["小清"], "description": "女主角"},
        ]
    return {
        "characters": chars,
        "locations": locs or [],
    }


def _scene(
    chapter_n: int,
    scene_n: int,
    location: str,
    int_ext: str = "INT",
    time: str = "日",
    summary: str = "",
    chars_present: list[str] | None = None,
    elements: list[ScreenplayElement] | None = None,
    decisions: list[AdaptationDecision] | None = None,
    transition: str = "",
    paragraph_range: tuple[int, int] = (1, 5),
) -> SceneAssembleData:
    return SceneAssembleData(
        chapter_number=chapter_n,
        scene_index_in_chapter=scene_n,
        heading=SceneHeading(int_ext=int_ext, location_name=location, time_of_day=time),
        summary=summary,
        characters_present_names=chars_present or [],
        paragraph_range=paragraph_range,
        elements=elements or [],
        decisions=decisions or [],
        transition_to_next=transition,
    )


def _action(text: str) -> ScreenplayElement:
    return ScreenplayElement(type="action", text=text)


def _dialogue(name: str, text: str, paren: str | None = None) -> ScreenplayElement:
    return ScreenplayElement(
        type="dialogue", text=text, character_name=name, parenthetical=paren
    )


def _voiceover(name: str, text: str, inner: bool = False) -> ScreenplayElement:
    return ScreenplayElement(
        type="voiceover", text=text, character_name=name, is_inner_monologue=inner
    )


def _parenthetical(text: str) -> ScreenplayElement:
    return ScreenplayElement(type="parenthetical", text=text)


def _decision(
    element_index: int, original: str, recommended: str = "voiceover",
) -> AdaptationDecision:
    return AdaptationDecision(
        element_index=element_index,
        original_text=original,
        options=[
            AdaptationOption(
                type="voiceover", text=f"V.O.:{original}",
                pros="保留主观视角", cons="依赖画外音",
            ),
            AdaptationOption(
                type="action_externalize", text=f"动作:{original[:10]}",
                pros="更剧本化", cons="可能丢明确性",
            ),
            AdaptationOption(
                type="delete", rationale="后续对白可隐含",
            ),
        ],
        recommended=recommended,
    )


# ============================================================
# 1. ID 编号(6 case)
# ============================================================


def test_char_id_sequential_by_bible_order():
    """char_NNN 按 bible.characters 顺序编号。"""
    bible = _make_bible([
        {"name": "甲"},
        {"name": "乙"},
        {"name": "丙"},
    ])
    scenes = [_scene(1, 1, "客厅", elements=[_action("甲走进来。")])]
    result = assemble_screenplay(ComposeInput(novel_title="t", bible=bible, scenes=scenes))
    chars = result.yaml_dict["characters"]
    assert chars[0]["id"] == "char_001"
    assert chars[0]["name"] == "甲"
    assert chars[1]["id"] == "char_002"
    assert chars[1]["name"] == "乙"
    assert chars[2]["id"] == "char_003"
    assert chars[2]["name"] == "丙"


def test_loc_id_by_first_appearance_and_reused():
    """loc_NNN 按场景首次出现顺序;同名 location 复用同一 ID。"""
    scenes = [
        _scene(1, 1, "客厅", elements=[_action("入。")]),       # loc_001
        _scene(1, 2, "厨房", elements=[_action("洗碗。")]),     # loc_002
        _scene(1, 3, "客厅", elements=[_action("回。")]),       # loc_001 复用
        _scene(2, 1, "卧室", elements=[_action("睡。")]),       # loc_003
    ]
    result = assemble_screenplay(
        ComposeInput(novel_title="t", bible=_make_bible(), scenes=scenes)
    )
    assert result.location_id_map == {"客厅": "loc_001", "厨房": "loc_002", "卧室": "loc_003"}
    scenes_out = result.yaml_dict["scenes"]
    assert scenes_out[0]["heading"]["location_id"] == "loc_001"
    assert scenes_out[1]["heading"]["location_id"] == "loc_002"
    assert scenes_out[2]["heading"]["location_id"] == "loc_001"   # 复用
    assert scenes_out[3]["heading"]["location_id"] == "loc_003"


def test_scene_number_global_across_chapters():
    """scene_NNN 跨 chapter 全局连续(不会因为换章节重置)。"""
    scenes = [
        _scene(1, 1, "A", elements=[_action(".")]),
        _scene(1, 2, "B", elements=[_action(".")]),
        _scene(2, 1, "C", elements=[_action(".")]),   # 新章但 scene_003
    ]
    result = assemble_screenplay(
        ComposeInput(novel_title="t", bible=_make_bible(), scenes=scenes)
    )
    scenes_out = result.yaml_dict["scenes"]
    assert [s["id"] for s in scenes_out] == ["scene_001", "scene_002", "scene_003"]
    assert [s["number"] for s in scenes_out] == [1, 2, 3]


def test_element_id_two_segment_pattern():
    """el_NNN_MMM:NNN 是 scene 全局编号,MMM 是 scene 内 1-based 序号。"""
    scenes = [
        _scene(1, 1, "A", elements=[_action("1"), _action("2"), _action("3")]),
        _scene(1, 2, "B", elements=[_action("a"), _action("b")]),
    ]
    result = assemble_screenplay(
        ComposeInput(novel_title="t", bible=_make_bible(), scenes=scenes)
    )
    scenes_out = result.yaml_dict["scenes"]
    s1_ids = [e["id"] for e in scenes_out[0]["elements"]]
    s2_ids = [e["id"] for e in scenes_out[1]["elements"]]
    assert s1_ids == ["el_001_001", "el_001_002", "el_001_003"]
    assert s2_ids == ["el_002_001", "el_002_002"]


def test_decision_id_sequential():
    """dec_NNN 全局连续(不论分布在哪 scene)。"""
    scenes = [
        _scene(1, 1, "A",
               elements=[_voiceover("林墨", "想着她", inner=True)],
               decisions=[_decision(0, "想着她")]),
        _scene(1, 2, "B",
               elements=[_voiceover("苏清", "走吧", inner=True),
                         _voiceover("苏清", "去吧", inner=True)],
               decisions=[_decision(0, "走吧"), _decision(1, "去吧")]),
    ]
    result = assemble_screenplay(
        ComposeInput(novel_title="t", bible=_make_bible(), scenes=scenes)
    )
    decs = result.yaml_dict["adaptation_decisions"]
    assert [d["id"] for d in decs] == ["dec_001", "dec_002", "dec_003"]


def test_aka_maps_to_main_char_id():
    """aka 别名能映射到主 name 的同一 char_id。"""
    bible = _make_bible([
        {"name": "林墨", "aka": ["阿墨", "小林"]},
    ])
    scenes = [
        _scene(1, 1, "A",
               chars_present=["阿墨", "小林"],
               # dialogue 用 aka "小林" 也应该映射成 char_001
               elements=[_dialogue("小林", "我来了。")]),
    ]
    result = assemble_screenplay(
        ComposeInput(novel_title="t", bible=bible, scenes=scenes)
    )
    # name + aka 都映射到 char_001
    assert result.character_id_map["林墨"] == "char_001"
    assert result.character_id_map["阿墨"] == "char_001"
    assert result.character_id_map["小林"] == "char_001"
    # characters_present 去重(两个 aka 实际同人)
    scenes_out = result.yaml_dict["scenes"]
    assert scenes_out[0]["characters_present"] == ["char_001"]
    # dialogue 用 aka 也成功映射
    assert scenes_out[0]["elements"][0]["character_id"] == "char_001"


# ============================================================
# 2. scenes / elements(5 case)
# ============================================================


def test_characters_present_name_to_id_and_dedup():
    """characters_present 把 name 转 char_id + 去重(去重发生在转 ID 后)。"""
    scenes = [_scene(1, 1, "A",
                     chars_present=["林墨", "苏清", "林墨"],   # 重复
                     elements=[_action(".")])]
    result = assemble_screenplay(
        ComposeInput(novel_title="t", bible=_make_bible(), scenes=scenes)
    )
    scenes_out = result.yaml_dict["scenes"]
    assert scenes_out[0]["characters_present"] == ["char_001", "char_002"]


def test_dialogue_voiceover_character_name_to_id():
    """dialogue / voiceover 的 character_name 转 character_id。"""
    scenes = [_scene(1, 1, "A", elements=[
        _dialogue("林墨", "你来了。", paren="低声"),
        _voiceover("苏清", "他终于到了。"),
    ])]
    result = assemble_screenplay(
        ComposeInput(novel_title="t", bible=_make_bible(), scenes=scenes)
    )
    els = result.yaml_dict["scenes"][0]["elements"]
    assert els[0]["type"] == "dialogue"
    assert els[0]["character_id"] == "char_001"
    assert els[0]["parenthetical"] == "低声"
    assert els[1]["type"] == "voiceover"
    assert els[1]["character_id"] == "char_002"


def test_action_parenthetical_no_character_required():
    """action / parenthetical 无 character_name 也合法。"""
    scenes = [_scene(1, 1, "A", elements=[
        _action("林墨走进房间。"),
        _parenthetical("(场内一片寂静)"),
    ])]
    result = assemble_screenplay(
        ComposeInput(novel_title="t", bible=_make_bible(), scenes=scenes)
    )
    els = result.yaml_dict["scenes"][0]["elements"]
    assert els[0]["type"] == "action"
    assert "character_id" not in els[0]
    assert els[1]["type"] == "parenthetical"
    assert "character_id" not in els[1]


def test_unknown_character_in_dialogue_skipped_with_warning():
    """dialogue 角色不在 bible → 跳过 + warning,其他元素正常。"""
    scenes = [_scene(1, 1, "A", elements=[
        _action("林墨进来。"),
        _dialogue("张三", "我是路人。"),       # 不在 bible
        _dialogue("林墨", "你好。"),
    ])]
    result = assemble_screenplay(
        ComposeInput(novel_title="t", bible=_make_bible(), scenes=scenes)
    )
    els = result.yaml_dict["scenes"][0]["elements"]
    assert len(els) == 2   # 张三那条被过滤
    assert els[0]["type"] == "action"
    assert els[1]["character_id"] == "char_001"
    # warning 记录
    warning_msgs = [w.message for w in result.warnings if w.layer == "element"]
    assert any("张三" in m for m in warning_msgs)


def test_scene_all_elements_filtered_skipped_no_id_hole():
    """整场 elements 全过滤 → 跳过本场,后续 scene_NNN 不留空洞。"""
    scenes = [
        _scene(1, 1, "A", elements=[_action("1.")]),       # scene_001
        _scene(1, 2, "B", elements=[                        # 整场都被过滤
            _dialogue("张三", "无效"),
            _dialogue("李四", "也无效"),
        ]),
        _scene(1, 3, "C", elements=[_action("2.")]),       # 应该是 scene_002,不是 scene_003
    ]
    result = assemble_screenplay(
        ComposeInput(novel_title="t", bible=_make_bible(), scenes=scenes)
    )
    scenes_out = result.yaml_dict["scenes"]
    assert len(scenes_out) == 2
    assert [s["id"] for s in scenes_out] == ["scene_001", "scene_002"]
    # scene_id_map 只有入选的 2 个
    assert 0 in result.scene_id_map
    assert 1 not in result.scene_id_map   # 被跳过
    assert 2 in result.scene_id_map
    # warning 记录
    scene_warnings = [w for w in result.warnings if w.layer == "scene"]
    assert any("跳过本场" in w.message for w in scene_warnings)


# ============================================================
# 3. decisions(3 case)
# ============================================================


def test_decision_element_index_to_element_id():
    """decision.element_index(0-based scene 内下标)→ element_id 正确。"""
    scenes = [_scene(1, 1, "A",
                     elements=[
                         _action("林墨入。"),                                # idx 0
                         _voiceover("林墨", "她还在", inner=True),            # idx 1
                         _dialogue("苏清", "等你很久了。"),                   # idx 2
                     ],
                     decisions=[_decision(1, "她还在")])]
    result = assemble_screenplay(
        ComposeInput(novel_title="t", bible=_make_bible(), scenes=scenes)
    )
    decs = result.yaml_dict["adaptation_decisions"]
    assert len(decs) == 1
    # element_index=1 对应 scene 内第 2 个 element → el_001_002
    assert decs[0]["element_id"] == "el_001_002"
    assert decs[0]["scene_id"] == "scene_001"
    assert decs[0]["original_text"] == "她还在"


def test_decision_with_filtered_element_skipped():
    """decision 关联的 element 已被过滤 → decision 跳过 + warning。"""
    scenes = [_scene(1, 1, "A",
                     elements=[
                         _action("入。"),
                         _voiceover("张三", "我是路人", inner=True),         # 张三不在 bible → 过滤
                         _action("出。"),
                     ],
                     decisions=[_decision(1, "我是路人")])]
    result = assemble_screenplay(
        ComposeInput(novel_title="t", bible=_make_bible(), scenes=scenes)
    )
    decs = result.yaml_dict.get("adaptation_decisions", [])
    assert decs == []   # decision 被跳过
    dec_warnings = [w for w in result.warnings if w.layer == "decision"]
    assert any("element 已被过滤" in w.message for w in dec_warnings)


def test_decision_orphaned_when_scene_skipped():
    """整场被跳过 → 关联的 decisions 一并跳过 + warning。"""
    scenes = [
        _scene(1, 1, "A", elements=[_dialogue("张三", "无效")],   # 整场过滤
               decisions=[_decision(0, "orphan")]),
        _scene(1, 2, "B", elements=[_action(".")]),
    ]
    result = assemble_screenplay(
        ComposeInput(novel_title="t", bible=_make_bible(), scenes=scenes)
    )
    decs = result.yaml_dict.get("adaptation_decisions", [])
    assert decs == []
    dec_warnings = [w for w in result.warnings if w.layer == "decision"]
    assert any("本场已跳过" in w.message for w in dec_warnings)


# ============================================================
# 4. 可选字段(4 case)
# ============================================================


def test_empty_transition_not_written():
    """transition_to_next 空字符串 → 不写入 yaml(避免 schema 枚举校验失败)。"""
    scenes = [_scene(1, 1, "A", elements=[_action(".")], transition="")]
    result = assemble_screenplay(
        ComposeInput(novel_title="t", bible=_make_bible(), scenes=scenes)
    )
    assert "transition_to_next" not in result.yaml_dict["scenes"][0]


def test_valid_transition_written():
    """transition_to_next 有值且合法 → 写入。"""
    scenes = [_scene(1, 1, "A", elements=[_action(".")], transition="FADE_OUT")]
    result = assemble_screenplay(
        ComposeInput(novel_title="t", bible=_make_bible(), scenes=scenes)
    )
    assert result.yaml_dict["scenes"][0]["transition_to_next"] == "FADE_OUT"


def test_summary_and_source_written():
    """summary + source(chapter + paragraph_range)写入正确。"""
    scenes = [_scene(2, 3, "A",
                     summary="林墨与苏清重逢",
                     elements=[_action(".")],
                     paragraph_range=(15, 28))]
    result = assemble_screenplay(
        ComposeInput(novel_title="t", bible=_make_bible(), scenes=scenes)
    )
    scene_out = result.yaml_dict["scenes"][0]
    assert scene_out["summary"] == "林墨与苏清重逢"
    assert scene_out["source"] == {"chapter": 2, "paragraph_range": [15, 28]}


def test_chinese_location_not_escaped_in_yaml():
    """中文 location 在 yaml 输出不被转义。"""
    scenes = [_scene(1, 1, "县城旧医院", elements=[_action(".")])]
    result = assemble_screenplay(
        ComposeInput(novel_title="中文小说", bible=_make_bible(), scenes=scenes)
    )
    # 直接检查文本里有中文(allow_unicode=True 应保证)
    assert "县城旧医院" in result.yaml_text
    assert "中文小说" in result.yaml_text
    # 不应该出现 \u 转义
    assert "\\u" not in result.yaml_text


# ============================================================
# 5. 致命错误(3 case)
# ============================================================


def test_empty_bible_characters_raises():
    """空 bible.characters → ComposeError。"""
    bible = {"characters": [], "locations": []}
    scenes = [_scene(1, 1, "A", elements=[_action(".")])]
    with pytest.raises(ComposeError, match="characters"):
        assemble_screenplay(
            ComposeInput(novel_title="t", bible=bible, scenes=scenes)
        )


def test_empty_scenes_raises():
    """空 scenes 输入 → ComposeError。"""
    with pytest.raises(ComposeError, match="场景"):
        assemble_screenplay(
            ComposeInput(novel_title="t", bible=_make_bible(), scenes=[])
        )


def test_all_scenes_filtered_raises():
    """所有 scene 都被过滤 → ComposeError(不能产出空 scenes 数组)。"""
    # 所有场景的角色都不在 bible,且没有 action 类元素
    scenes = [
        _scene(1, 1, "A", elements=[_dialogue("张三", "无效")]),
        _scene(1, 2, "B", elements=[_dialogue("李四", "也无效")]),
    ]
    with pytest.raises(ComposeError, match="所有场景"):
        assemble_screenplay(
            ComposeInput(novel_title="t", bible=_make_bible(), scenes=scenes)
        )


# ============================================================
# 6. 最终通过校验(2 case)
# ============================================================


def test_assembled_yaml_passes_full_validator():
    """组装后的 yaml_text 通过 yaml_validator 的双层校验(schema + reference)。"""
    bible = _make_bible([
        {"name": "林墨", "aka": ["阿墨"], "description": "记者"},
        {"name": "苏清", "description": "钢琴家"},
    ], locs=[
        {"name": "县城旧医院", "description": "废弃多年"},
    ])
    scenes = [
        _scene(1, 1, "县城旧医院", int_ext="INT", time="夜",
               summary="林墨深夜潜入旧医院",
               chars_present=["林墨"],
               elements=[
                   _action("林墨打开手电,光柱扫过墙壁。"),
                   _voiceover("林墨", "她真的来过这里。", inner=True),
                   _dialogue("林墨", "苏清?", paren="低声"),
               ],
               decisions=[_decision(1, "她真的来过这里。")],
               transition="CUT_TO",
               paragraph_range=(1, 8)),
        _scene(1, 2, "县城旧医院", int_ext="INT", time="深夜",
               summary="苏清现身",
               chars_present=["林墨", "苏清"],
               elements=[
                   _action("门吱呀一声打开。"),
                   _dialogue("苏清", "你来晚了。"),
                   _dialogue("林墨", "对不起。"),
               ],
               transition="FADE_OUT",
               paragraph_range=(9, 20)),
    ]
    result = assemble_screenplay(ComposeInput(
        novel_title="孤院",
        bible=bible,
        scenes=scenes,
        adapted_from_chapters=[1],
        model_name="deepseek-chat",
    ))
    # 关键:跑双层校验
    vr = validate_screenplay_yaml(result.yaml_text)
    assert vr.valid is True, (
        f"组装后的 YAML 应通过校验,但有错: "
        f"{[(i.layer, i.path, i.message) for i in vr.errors()]}"
    )


def test_meta_fields_correct():
    """meta.schema_version / generated_by.platform / stats / source 字段正确。"""
    scenes = [_scene(1, 1, "A", elements=[_action(".") for _ in range(50)])]
    result = assemble_screenplay(ComposeInput(
        novel_title="测试",
        bible=_make_bible(),
        scenes=scenes,
        adapted_from_chapters=[1, 3, 2, 1],   # 含重复 + 乱序
        model_name="deepseek-chat",
    ))
    meta = result.yaml_dict["meta"]
    assert meta["schema_version"] == "1.0"
    assert meta["title"] == "测试"
    assert meta["generated_by"]["platform"] == "hunjing-screenplay@0.1.0"
    assert meta["generated_by"]["model"] == "deepseek-chat"
    assert meta["generated_by"]["schema_version"] == "1.0"
    # generated_at 是 ISO date-time
    assert "T" in meta["generated_by"]["generated_at"]
    assert meta["generated_by"]["generated_at"].endswith("Z")
    # stats
    assert meta["stats"]["total_scenes"] == 1
    assert meta["stats"]["total_pages_estimate"] >= 1
    # source 去重 + 排序
    assert meta["source"]["novel_title"] == "测试"
    assert meta["source"]["adapted_from_chapters"] == [1, 2, 3]
