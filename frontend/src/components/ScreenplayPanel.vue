<script setup lang="ts">
/**
 * 右栏:剧本 — PR#11 commit 2。
 *
 * Scene 卡片列表。点击 scene 标题切换 selectedSceneId,
 * element 按剧本格式渲染:
 *   - action      : 灰色行动文
 *   - dialogue    : 角色名居中 + 对白居中
 *   - parenthetical: 小括号灰字
 *   - voiceover   : 角色名 + (V.O.) + 内容
 */
import { computed, inject, nextTick, ref, watch } from "vue";

import FidelityBadge from "./FidelityBadge.vue";
import StructureReportPanel from "./StructureReportPanel.vue";
import { useScreenplayStore } from "../stores/screenplay";
import type {
  AdaptationDecision,
  OptimizeScope,
  Scene,
  ScreenplayElement,
} from "../types/screenplay";

// 从父组件注入"打开优化弹窗"方法(A 入口)
const openOptimization = inject<
  (scope: OptimizeScope, sceneId?: string) => void
>("openOptimizationModal", () => {});

const store = useScreenplayStore();
const scrollRoot = ref<HTMLElement | null>(null);

const scenes = computed<Scene[]>(() => store.screenplay?.scenes ?? []);

function locationName(id: string): string {
  return store.locationNameById.get(id) ?? id;
}

function characterName(id: string): string {
  return store.characterNameById.get(id) ?? id;
}

function isSelected(sceneId: string): boolean {
  return store.selectedSceneId === sceneId;
}

function handleSelect(sceneId: string) {
  store.selectScene(sceneId);
}

function decisionsForElement(
  sceneId: string,
  elementId: string,
): AdaptationDecision[] {
  if (!store.screenplay?.adaptation_decisions) return [];
  return store.screenplay.adaptation_decisions.filter(
    (d) => d.scene_id === sceneId && d.element_id === elementId,
  );
}

function elementHasDecision(sceneId: string, el: ScreenplayElement): boolean {
  return decisionsForElement(sceneId, el.id).length > 0;
}

// 选中变化 → 滚动到位
watch(
  () => store.selectedSceneId,
  async (id) => {
    if (!id) return;
    await nextTick();
    if (!scrollRoot.value) return;
    const target = scrollRoot.value.querySelector(
      `[data-scene-id="${id}"]`,
    ) as HTMLElement | null;
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  },
);
</script>

<template>
  <div ref="scrollRoot" class="screenplay-panel">
    <div v-if="scenes.length === 0" class="empty">
      <div class="empty-text">剧本待生成</div>
    </div>
    <template v-else>
      <StructureReportPanel />
      <article
        v-for="scene in scenes"
        :key="scene.id"
        :data-scene-id="scene.id"
        :class="['scene-card', { selected: isSelected(scene.id) }]"
        @click="handleSelect(scene.id)"
      >
        <header class="scene-header">
          <span class="scene-no">SCENE {{ String(scene.number).padStart(3, "0") }}</span>
          <span class="scene-heading-text">
            {{ scene.heading.int_ext }}. {{ locationName(scene.heading.location_id) }} —
            {{ scene.heading.time_of_day }}
          </span>
          <!-- A 入口:AI 优化此场(PR#16) -->
          <button
            class="optimize-a-btn"
            :disabled="store.optimizingState === 'running'"
            title="让 AI 重写此场,针对保真度诊断"
            @click.stop="openOptimization('single_scene', scene.id)"
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4" />
            </svg>
            AI 优化
          </button>
          <FidelityBadge
            v-if="scene.fidelity"
            :fidelity="scene.fidelity"
            class="scene-fidelity"
            @click.stop
          />
        </header>

        <p v-if="scene.summary" class="scene-summary">{{ scene.summary }}</p>

        <div class="scene-body">
          <template v-for="el in scene.elements" :key="el.id">
            <!-- action -->
            <p v-if="el.type === 'action'" class="el el-action">
              {{ el.text }}
            </p>
            <!-- dialogue -->
            <div v-else-if="el.type === 'dialogue'" class="el el-dialogue">
              <div class="d-character">{{ characterName(el.character_id) }}</div>
              <div v-if="el.parenthetical" class="d-paren">({{ el.parenthetical }})</div>
              <div class="d-text">{{ el.text }}</div>
            </div>
            <!-- parenthetical -->
            <p v-else-if="el.type === 'parenthetical'" class="el el-paren">
              ({{ el.text }})
            </p>
            <!-- voiceover — 区分 V.O. / O.S. (PR#16 升级 3) -->
            <div v-else-if="el.type === 'voiceover'" class="el el-vo">
              <div class="d-character">
                {{ characterName(el.character_id) }}
                <span
                  class="vo-tag"
                  :class="el.voice_source === 'OS' ? 'vo-tag-os' : 'vo-tag-vo'"
                >({{ el.voice_source === 'OS' ? 'O.S.' : 'V.O.' }})</span>
                <span
                  v-if="elementHasDecision(scene.id, el)"
                  class="decision-badge"
                  title="有改编决策待选"
                >改编</span>
              </div>
              <div class="d-text">{{ el.text }}</div>
            </div>
            <!-- transition -->
            <p v-else-if="el.type === 'transition'" class="el el-transition">
              {{ el.text }}
            </p>
          </template>
        </div>

        <footer v-if="scene.transition_to_next" class="scene-transition">
          {{ scene.transition_to_next }}
        </footer>
      </article>
    </template>
  </div>
</template>

<style scoped>
.screenplay-panel {
  font-family: var(--font-sans);
  font-size: 14px;
  color: var(--text);
}

/* === SCENE 卡 — 剧本印刷气质 === */
.scene-card {
  background: var(--card-bg);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-lg);
  padding: var(--space-5) var(--space-6);
  margin-bottom: var(--space-5);
  transition: all var(--transition-base);
  cursor: pointer;
}
.scene-card:hover {
  border-color: var(--border);
}
.scene-card:hover .optimize-a-btn {
  opacity: 1;
}
.scene-card.selected {
  border-color: var(--accent);
  background: var(--card-bg-strong);
}

/* SCENE 头 — 剧本印刷格式 */
.scene-header {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--border-soft);
}

.scene-no {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 0.18em;
  font-weight: 500;
}
.scene-heading-text {
  font-family: var(--font-mono);
  font-size: 12.5px;
  color: var(--text-strong);
  letter-spacing: 0.06em;
  font-weight: 500;
  text-transform: uppercase;
  flex: 1;
}

/* A 入口 — AI 优化此场按钮(hover 时显现) */
.optimize-a-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  background: transparent;
  color: var(--text-muted);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  font-size: 10.5px;
  font-family: var(--font-sans);
  text-transform: none;
  letter-spacing: 0.04em;
  cursor: pointer;
  transition: all var(--transition-fast);
  opacity: 0;     /* hover scene 时 才显现 */
}
.optimize-a-btn:hover:not(:disabled) {
  background: var(--accent-soft);
  color: var(--accent-text);
  border-color: var(--accent);
}
.optimize-a-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.scene-summary {
  font-family: var(--font-serif);
  font-size: 14px;
  font-style: italic;
  color: var(--text-secondary);
  margin: var(--space-3) 0 var(--space-4);
  line-height: 1.8;
  letter-spacing: 0.01em;
}

.scene-body {
  /* 剧本元素之间统一间距 */
}

.el {
  margin: var(--space-3) 0;
}

/* ACTION — 段落式,衬线字体最易读 */
.el-action {
  font-family: var(--font-serif);
  font-size: 15px;
  line-height: 1.85;
  color: var(--text);
  letter-spacing: 0.01em;
}

/* DIALOGUE / VOICEOVER — 行业标准居中缩进 */
.el-dialogue,
.el-vo {
  margin: var(--space-5) auto;
  text-align: center;
  max-width: 70%;
}
.d-character {
  font-family: var(--font-mono);
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.18em;
  color: var(--text-strong);
  text-transform: uppercase;
  margin-bottom: var(--space-1);
}
.vo-tag {
  font-size: 10px;
  font-weight: 400;
  margin-left: 4px;
  letter-spacing: 0.12em;
}
.vo-tag-vo {
  color: var(--decision-voiceover);  /* 烟紫 — V.O. */
}
.vo-tag-os {
  color: var(--decision-action);     /* 钢蓝 — O.S. */
}
.d-paren {
  font-family: var(--font-serif);
  font-size: 12.5px;
  color: var(--text-muted);
  font-style: italic;
  margin-bottom: var(--space-1);
}
.d-text {
  font-family: var(--font-serif);
  font-size: 15px;
  line-height: 1.8;
  color: var(--text);
  letter-spacing: 0.01em;
}

.el-paren {
  text-align: center;
  font-family: var(--font-serif);
  font-size: 13px;
  color: var(--text-muted);
  font-style: italic;
}

.el-transition {
  text-align: right;
  font-family: var(--font-mono);
  font-weight: 500;
  font-size: 10.5px;
  letter-spacing: 0.18em;
  color: var(--text-muted);
  margin: var(--space-4) 0;
}

/* 决策标识 — 改用细线下划替代闪烁星 */
.decision-badge {
  display: inline-block;
  margin-left: 6px;
  color: var(--decision-voiceover);
  font-size: 9px;
  letter-spacing: 0.1em;
  border-bottom: 1px solid currentColor;
  padding-bottom: 1px;
  opacity: 0.7;
}

.scene-transition {
  margin-top: var(--space-4);
  padding-top: var(--space-3);
  border-top: 1px solid var(--border-soft);
  text-align: right;
  font-family: var(--font-mono);
  font-size: 10.5px;
  font-weight: 500;
  letter-spacing: 0.2em;
  color: var(--text-muted);
}

.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--text-muted);
}
.empty-text {
  font-family: var(--font-serif);
  font-size: 15px;
  font-style: italic;
}
</style>
