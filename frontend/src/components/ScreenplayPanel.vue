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
import { computed, nextTick, ref, watch } from "vue";

import FidelityBadge from "./FidelityBadge.vue";
import StructureReportPanel from "./StructureReportPanel.vue";
import { useScreenplayStore } from "../stores/screenplay";
import type {
  AdaptationDecision,
  Scene,
  ScreenplayElement,
} from "../types/screenplay";

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
            <!-- voiceover -->
            <div v-else-if="el.type === 'voiceover'" class="el el-vo">
              <div class="d-character">
                {{ characterName(el.character_id) }} <span class="vo-tag">(V.O.)</span>
                <span
                  v-if="elementHasDecision(scene.id, el)"
                  class="decision-badge"
                  title="该元素有改编决策待选"
                >★</span>
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
  font-family: "Courier Prime", ui-monospace, "Courier New", monospace;
  font-size: 13px;
  color: var(--text);
}

.scene-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px 18px;
  margin-bottom: 14px;
  transition: all 180ms;
}
.scene-card:hover {
  border-color: rgba(139, 92, 246, 0.25);
  box-shadow: var(--shadow-sm);
}
.scene-card.selected {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.12);
}

.scene-header {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 700;
  text-transform: uppercase;
  margin-bottom: 6px;
}
.scene-fidelity {
  margin-left: auto;
}
.scene-no {
  font-size: 10.5px;
  color: var(--accent);
  letter-spacing: 0.1em;
  font-family: ui-monospace, monospace;
  padding: 2px 8px;
  background: rgba(139, 92, 246, 0.1);
  border-radius: 10px;
}
.scene-heading-text {
  font-size: 12px;
  color: var(--text);
  letter-spacing: 0.05em;
}

.scene-summary {
  font-family:
    -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 12px;
  font-style: italic;
  color: var(--text-muted);
  margin: 4px 0 12px;
  line-height: 1.6;
  padding-left: 8px;
  border-left: 2px solid var(--border);
}

.scene-body {
  /* 剧本元素之间统一间距 */
}

.el {
  margin: 8px 0;
}

.el-action {
  font-family:
    -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text);
}

.el-dialogue,
.el-vo {
  margin: 14px auto;
  text-align: center;
  max-width: 78%;
}
.d-character {
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: var(--text);
  margin-bottom: 2px;
}
.vo-tag {
  font-size: 10.5px;
  color: var(--decision-voiceover);
  font-weight: 500;
}
.d-paren {
  font-size: 11px;
  color: var(--text-muted);
  font-style: italic;
  margin-bottom: 2px;
}
.d-text {
  font-family:
    -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text);
}

.el-paren {
  text-align: center;
  font-size: 11.5px;
  color: var(--text-muted);
  font-style: italic;
}

.el-transition {
  text-align: right;
  font-weight: 700;
  font-size: 10.5px;
  letter-spacing: 0.12em;
  color: var(--text-muted);
  margin: 12px 0;
}

.decision-badge {
  display: inline-block;
  margin-left: 6px;
  color: var(--accent);
  font-size: 12px;
  animation: starpulse 2.4s ease-in-out infinite;
}
@keyframes starpulse {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 1; }
}

.scene-transition {
  margin-top: 14px;
  text-align: right;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.12em;
  color: var(--text-muted);
  font-family: ui-monospace, monospace;
}

.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--text-muted);
}
.empty-text {
  font-size: 13px;
}
</style>
