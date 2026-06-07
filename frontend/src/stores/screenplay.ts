/**
 * 剧本 Pinia store — 集中管理当前编辑的剧本状态。
 *
 * 数据来源:GET /novels/{id}/screenplay 返 YAML 字符串,
 * 前端用 js-yaml 解析为 Screenplay 对象后存这里。
 */

import yaml from "js-yaml";
import { defineStore } from "pinia";
import { computed, ref } from "vue";

import {
  composeScreenplay,
  getChapterParagraphs,
  getLatestScreenplay,
  getNovel,
  getScreenplayById,
  getStructureReport,
  listScreenplayVersions,
  optimizeScreenplay,
  type ComposeRequest,
} from "../api/client";
import type {
  AdaptationDecision,
  AdaptationOptionType,
  ComposeWarning,
  OptimizeRequest,
  OptimizeResponse,
  Scene,
  Screenplay,
  ScreenplayElement,
  ScreenplayVersion,
  StructureReport,
} from "../types/screenplay";

export type LoadingState = "idle" | "loading" | "composing" | "error" | "ready";

export const useScreenplayStore = defineStore("screenplay", () => {
  // ============================================================
  // 状态
  // ============================================================
  const novelId = ref<string | null>(null);
  const novelTitle = ref<string>("");
  const screenplayId = ref<string | null>(null);
  const screenplay = ref<Screenplay | null>(null);
  const rawYaml = ref<string>("");
  const warnings = ref<ComposeWarning[]>([]);
  const failedChapters = ref<number[]>([]);
  const stats = ref<Record<string, unknown>>({});
  const loadingState = ref<LoadingState>("idle");
  const lastError = ref<string>("");

  // 结构报告(PR#13,按需加载)
  const structureReport = ref<StructureReport | null>(null);
  const structureLoading = ref<boolean>(false);

  // 优化版本树(PR#16)
  const versions = ref<ScreenplayVersion[]>([]);
  const optimizingState = ref<"idle" | "running" | "done" | "error">("idle");
  const lastOptimizeResult = ref<OptimizeResponse | null>(null);
  const optimizeError = ref<string>("");

  // 当前选中的 scene(用于左右栏联动 + 改编决策面板)
  const selectedSceneId = ref<string | null>(null);

  // 章节元数据(给左栏渲染原文用)
  const novelChapters = ref<
    Array<{
      id: string;
      number: number;
      title: string | null;
      paragraph_count: number;
      char_count: number;
    }>
  >([]);

  // 段落正文:chapter_number → 段落列表
  const paragraphsByChapter = ref<
    Map<number, Array<{ index_in_chapter: number; text: string }>>
  >(new Map());

  // ============================================================
  // Computed
  // ============================================================

  /** 当前选中的 scene 对象 */
  const selectedScene = computed<Scene | null>(() => {
    if (!screenplay.value || !selectedSceneId.value) return null;
    return (
      screenplay.value.scenes.find((s) => s.id === selectedSceneId.value) ??
      null
    );
  });

  /** 选中 scene 对应的 element_id → element 索引(给改编决策定位用) */
  const selectedSceneElements = computed<Map<string, ScreenplayElement>>(() => {
    const map = new Map<string, ScreenplayElement>();
    if (!selectedScene.value) return map;
    for (const el of selectedScene.value.elements) {
      map.set(el.id, el);
    }
    return map;
  });

  /** 选中 scene 的改编决策列表 */
  const selectedSceneDecisions = computed<AdaptationDecision[]>(() => {
    if (!screenplay.value || !selectedSceneId.value) return [];
    return (screenplay.value.adaptation_decisions ?? []).filter(
      (d) => d.scene_id === selectedSceneId.value,
    );
  });

  /** character_id → name 映射 */
  const characterNameById = computed<Map<string, string>>(() => {
    const map = new Map<string, string>();
    if (!screenplay.value) return map;
    for (const c of screenplay.value.characters) {
      map.set(c.id, c.name);
    }
    return map;
  });

  /** location_id → name 映射 */
  const locationNameById = computed<Map<string, string>>(() => {
    const map = new Map<string, string>();
    if (!screenplay.value) return map;
    for (const l of screenplay.value.locations) {
      map.set(l.id, l.name);
    }
    return map;
  });

  /** 总 scene 数 */
  const totalScenes = computed<number>(
    () => screenplay.value?.scenes.length ?? 0,
  );

  /** 是否已有剧本 */
  const hasScreenplay = computed<boolean>(() => screenplay.value !== null);

  // ============================================================
  // Actions
  // ============================================================

  function reset() {
    novelId.value = null;
    novelTitle.value = "";
    screenplayId.value = null;
    screenplay.value = null;
    rawYaml.value = "";
    warnings.value = [];
    failedChapters.value = [];
    stats.value = {};
    loadingState.value = "idle";
    lastError.value = "";
    selectedSceneId.value = null;
    novelChapters.value = [];
    paragraphsByChapter.value = new Map();
  }

  function selectScene(sceneId: string | null) {
    selectedSceneId.value = sceneId;
  }

  /** 当前作者对每条决策的选择(本 PR 仅本地状态,不写后端)*/
  const userDecisionChoices = ref<Map<string, AdaptationOptionType>>(
    new Map(),
  );

  function chooseAdaptationOption(
    decisionId: string,
    type: AdaptationOptionType,
  ) {
    userDecisionChoices.value.set(decisionId, type);
    // 触发 reactivity
    userDecisionChoices.value = new Map(userDecisionChoices.value);
  }

  function getDecisionChoice(
    decisionId: string,
  ): AdaptationOptionType | null {
    return userDecisionChoices.value.get(decisionId) ?? null;
  }

  /** 加载指定 novel 的最新剧本(若有)*/
  async function loadLatestForNovel(targetNovelId: string) {
    loadingState.value = "loading";
    lastError.value = "";
    novelId.value = targetNovelId;
    selectedSceneId.value = null;

    // 拿 novel 元数据(标题 + 章节列表)+ 并行抓所有段落
    try {
      const n = await getNovel(targetNovelId);
      novelTitle.value = n.title;
      novelChapters.value = n.chapters;

      // 并行抓每章的段落正文(供左栏渲染)
      const pairs = await Promise.all(
        n.chapters.map(async (ch) => {
          const paragraphs = await getChapterParagraphs(ch.id);
          return [ch.number, paragraphs] as const;
        }),
      );
      const newMap = new Map<
        number,
        Array<{ index_in_chapter: number; text: string }>
      >();
      for (const [num, ps] of pairs) {
        newMap.set(num, ps);
      }
      paragraphsByChapter.value = newMap;
    } catch (e) {
      lastError.value = e instanceof Error ? e.message : String(e);
      loadingState.value = "error";
      return;
    }

    // 拿最新剧本(若不存在 404 是正常情况,显示"待生成")
    try {
      const r = await getLatestScreenplay(targetNovelId);
      screenplayId.value = r.screenplay_id;
      rawYaml.value = r.yaml;
      const parsed = yaml.load(r.yaml) as Screenplay;
      screenplay.value = parsed;
      warnings.value = r.warnings;
      failedChapters.value = r.failed_chapters;
      stats.value = r.stats;
      loadingState.value = "ready";
      // 顺便拉结构报告 + 版本列表(不阻塞主加载)
      loadStructureReport();
      // 拉完版本列表后,挂上"当前版本派生过的优化记录"
      loadVersions().then(() => {
        if (screenplayId.value) {
          _attachChildOptimizationIfAny(screenplayId.value);
        }
      });
    } catch (e) {
      // 404 = 还没生成 → idle 不是 error
      if (e instanceof Error && e.message.includes("404")) {
        screenplay.value = null;
        loadingState.value = "idle";
      } else {
        lastError.value = e instanceof Error ? e.message : String(e);
        loadingState.value = "error";
      }
    }
  }

  /** 拉结构报告(秒响应,无 LLM)*/
  async function loadStructureReport(): Promise<void> {
    if (!screenplayId.value) return;
    structureLoading.value = true;
    try {
      structureReport.value = await getStructureReport(screenplayId.value);
    } catch {
      structureReport.value = null;
    } finally {
      structureLoading.value = false;
    }
  }

  /** 拉版本列表(无 LLM,快) */
  async function loadVersions(): Promise<void> {
    if (!novelId.value) return;
    try {
      versions.value = await listScreenplayVersions(novelId.value);
    } catch {
      versions.value = [];
    }
  }

  /** 按 id 加载指定版本(切版本时用) */
  async function switchToVersion(targetScreenplayId: string): Promise<void> {
    loadingState.value = "loading";
    try {
      const r = await getScreenplayById(targetScreenplayId);
      screenplayId.value = r.screenplay_id;
      rawYaml.value = r.yaml;
      const parsed = yaml.load(r.yaml) as Screenplay;
      screenplay.value = parsed;
      warnings.value = r.warnings;
      failedChapters.value = r.failed_chapters;
      stats.value = r.stats;
      if (parsed?.scenes?.[0]) {
        selectedSceneId.value = parsed.scenes[0].id;
      }
      loadingState.value = "ready";
      // 切完版本立刻重拉结构报告(新版结构可能完全不同)
      structureReport.value = null;
      loadStructureReport();
      // PR#16 Hot1:切版本后,把"该版本派生过的子版本优化记录"挂回 lastOptimizeResult
      // — 让用户点 AI 优化时直接看到上次结果,而不是回到空白配置
      _attachChildOptimizationIfAny(targetScreenplayId);
    } catch (e) {
      lastError.value = e instanceof Error ? e.message : String(e);
      loadingState.value = "error";
    }
  }

  /**
   * 跑 AI 优化(A 单场 / B 整本共用)。
   * 成功后:① loadVersions 更新版本树 ② 自动切到新版本 ③ 把 result 留给 modal 展示 change_log
   */
  async function runOptimize(req: OptimizeRequest): Promise<void> {
    if (!screenplayId.value) return;
    optimizingState.value = "running";
    optimizeError.value = "";
    lastOptimizeResult.value = null;
    // C 修复:把作者已做的决策塞进 request 给 LLM 当输入参考
    const userDecisionsObj: Record<string, AdaptationOptionType> = {};
    userDecisionChoices.value.forEach((v, k) => {
      userDecisionsObj[k] = v;
    });
    const enrichedReq: OptimizeRequest = {
      ...req,
      user_decisions: Object.keys(userDecisionsObj).length > 0 ? userDecisionsObj : undefined,
    };
    try {
      const result = await optimizeScreenplay(screenplayId.value, enrichedReq);
      // 拉新版本列表
      await loadVersions();
      // 自动切到新生成的版本(switchToVersion 内部可能调 _attachChildOptimizationIfAny 清掉 lastOptimizeResult)
      await switchToVersion(result.new_screenplay_id);
      // 必须放在 switchToVersion 之后,避免被切版本逻辑覆盖
      lastOptimizeResult.value = result;
      optimizingState.value = "done";
    } catch (e) {
      optimizeError.value = e instanceof Error ? e.message : String(e);
      optimizingState.value = "error";
    }
  }

  function clearOptimizeResult() {
    lastOptimizeResult.value = null;
    optimizingState.value = "idle";
    optimizeError.value = "";
  }

  /** 切版本后,扫 versions 找当前版本派生的子版本,把它的 optimization_log 包装为 OptimizeResponse 挂回。
   *  这样用户切回原版后再打开 modal,能继续看到上次的 change_log + reasoning。 */
  function _attachChildOptimizationIfAny(currentVersionId: string) {
    // 找直接子版本(parent === currentVersionId);如果有多个,取最新的
    const children = versions.value
      .filter((v) => v.parent_screenplay_id === currentVersionId && v.optimization_log)
      .sort((a, b) => b.created_at.localeCompare(a.created_at));
    if (children.length === 0) {
      lastOptimizeResult.value = null;
      optimizingState.value = "idle";
      return;
    }
    const child = children[0];
    const log = child.optimization_log!;
    // 包装为 OptimizeResponse 结构(供 OptimizationModal 复用)
    lastOptimizeResult.value = {
      new_screenplay_id: child.id,
      parent_screenplay_id: currentVersionId,
      origin: child.origin,
      change_log: log.change_log || [],
      reasoning: log.reasoning || "",
      fallback_reason: log.fallback_reason ?? null,
      llm_usage: {},
    };
    // 显式 done 态,这样 modal 一打开就是结果视图
    optimizingState.value = "done";
  }

  /** 触发编排(贵,30-60s)*/
  async function triggerCompose(
    targetNovelId: string,
    options: ComposeRequest = {},
  ) {
    loadingState.value = "composing";
    lastError.value = "";
    try {
      const r = await composeScreenplay(targetNovelId, options);
      screenplayId.value = r.screenplay_id;
      rawYaml.value = r.yaml;
      const parsed = yaml.load(r.yaml) as Screenplay;
      screenplay.value = parsed;
      warnings.value = r.warnings;
      failedChapters.value = r.failed_chapters;
      stats.value = r.stats;
      // 默认选中第一场,demo 立刻有东西可看
      if (parsed?.scenes?.[0]) {
        selectedSceneId.value = parsed.scenes[0].id;
      }
      loadingState.value = "ready";
      // 顺便拉结构报告 + 版本列表
      loadStructureReport();
      loadVersions();
    } catch (e) {
      lastError.value = e instanceof Error ? e.message : String(e);
      loadingState.value = "error";
    }
  }

  return {
    // state
    novelId,
    novelTitle,
    novelChapters,
    paragraphsByChapter,
    screenplayId,
    screenplay,
    rawYaml,
    warnings,
    failedChapters,
    stats,
    loadingState,
    lastError,
    selectedSceneId,
    userDecisionChoices,
    structureReport,
    structureLoading,
    // 优化 + 版本(PR#16)
    versions,
    optimizingState,
    lastOptimizeResult,
    optimizeError,
    // computed
    selectedScene,
    selectedSceneElements,
    selectedSceneDecisions,
    characterNameById,
    locationNameById,
    totalScenes,
    hasScreenplay,
    // actions
    reset,
    selectScene,
    chooseAdaptationOption,
    getDecisionChoice,
    loadLatestForNovel,
    triggerCompose,
    loadStructureReport,
    // PR#16
    loadVersions,
    switchToVersion,
    runOptimize,
    clearOptimizeResult,
  };
});
