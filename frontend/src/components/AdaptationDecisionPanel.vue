<script setup lang="ts">
/**
 * 改编决策 3 选项面板 — PR#11 commit 3,差异化创新核心。
 *
 * 当用户选中包含 voiceover 内心独白的 scene,本面板从右下浮起,
 * 展示该 scene 所有 decision,每条 decision 给 3 备选(V.O./动作/删除)
 * + 利弊 + AI 推荐,作者点选哪个就高亮哪个(本地 state,不写后端)。
 *
 * "别的 AI 工具偷偷选 1 个,我们摊三选项给作者拍板。"
 */
import { computed, ref } from "vue";

import { useScreenplayStore } from "../stores/screenplay";
import type { AdaptationDecision, AdaptationOption } from "../types/screenplay";

const store = useScreenplayStore();
const collapsed = ref<boolean>(false);

const decisions = computed<AdaptationDecision[]>(
  () => store.selectedSceneDecisions,
);
const hasDecisions = computed<boolean>(() => decisions.value.length > 0);

const optionTypeLabel: Record<string, string> = {
  voiceover: "V.O. 画外音",
  action_externalize: "动作外化",
  delete: "删除",
};

const optionTypeMicro: Record<string, string> = {
  voiceover: "保留主观叙述",
  action_externalize: "转为可见动作",
  delete: "假后续场景能体现",
};

function sortedOptions(d: AdaptationDecision): AdaptationOption[] {
  // 推荐项排第一,其他按 V.O. / 动作 / 删除 顺序
  const order = ["voiceover", "action_externalize", "delete"];
  const rec = d.options.find((o) => o.type === d.chosen);
  const sorted = [...d.options].sort(
    (a, b) => order.indexOf(a.type) - order.indexOf(b.type),
  );
  // chosen 字段在 schema 里其实是"作者选择",但我们用 store.userDecisionChoices 兜底
  return sorted;
}

function recommendedType(d: AdaptationDecision): string {
  // PR#9 后端把推荐 LLM 推荐放在了哪里?当前 schema 里 decision 没有 recommended
  // 字段(adaptation_decision 只有 chosen 是作者选的)。
  // V.O. 是默认推荐 — 与 PR#9 prompt 一致(adaptation_decision.md)
  return "voiceover";
}

function isChosen(decisionId: string, type: string): boolean {
  return store.getDecisionChoice(decisionId) === type;
}

function choose(
  decisionId: string,
  type: "voiceover" | "action_externalize" | "delete",
) {
  store.chooseAdaptationOption(decisionId, type);
}

function toggle() {
  collapsed.value = !collapsed.value;
}
</script>

<template>
  <transition name="slide">
    <aside
      v-if="hasDecisions"
      :class="['decision-panel', { collapsed }]"
    >
      <!-- 标题栏 -->
      <header class="dp-head">
        <div class="dp-head-left">
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            class="dp-icon"
          >
            <circle cx="12" cy="12" r="10" />
            <path d="M12 8v4M12 16h.01" />
          </svg>
          <h3 class="dp-title">改编决策</h3>
          <span class="dp-count">{{ decisions.length }} 条 · 作者拍板</span>
        </div>
        <button class="dp-toggle" @click="toggle" :title="collapsed ? '展开' : '收起'">
          <svg
            v-if="collapsed"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <polyline points="18 15 12 9 6 15" />
          </svg>
          <svg
            v-else
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>
      </header>

      <!-- 决策列表(收起时只显示标题) -->
      <div v-if="!collapsed" class="dp-body">
        <article
          v-for="(d, dIdx) in decisions"
          :key="d.id"
          class="decision-card"
        >
          <!-- 原文 -->
          <div class="dc-header">
            <span class="dc-no">{{ dIdx + 1 }} / {{ decisions.length }}</span>
            <span class="dc-element-id">{{ d.element_id }}</span>
          </div>
          <blockquote class="dc-original">
            <span class="dc-quote">"</span>{{ d.original_text }}<span class="dc-quote">"</span>
          </blockquote>

          <!-- 3 选项 -->
          <div class="dc-options">
            <button
              v-for="opt in sortedOptions(d)"
              :key="opt.type"
              :class="[
                'option',
                `option--${opt.type}`,
                {
                  recommended: recommendedType(d) === opt.type,
                  chosen: isChosen(d.id, opt.type),
                },
              ]"
              @click="choose(d.id, opt.type)"
            >
              <div class="option-head">
                <span class="option-label">{{ optionTypeLabel[opt.type] }}</span>
                <span
                  v-if="recommendedType(d) === opt.type"
                  class="option-rec-badge"
                >
                  AI 推荐
                </span>
                <span v-if="isChosen(d.id, opt.type)" class="option-chosen-badge">
                  <svg
                    width="11"
                    height="11"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="3"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  >
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  已选
                </span>
              </div>
              <p class="option-micro">{{ optionTypeMicro[opt.type] }}</p>
              <!-- V.O. / 动作:展示改写文本 -->
              <p
                v-if="opt.text && (opt.type === 'voiceover' || opt.type === 'action_externalize')"
                class="option-text"
              >
                {{ opt.text }}
              </p>
              <!-- 删除:展示 rationale -->
              <p v-if="opt.rationale" class="option-rationale">
                <em>{{ opt.rationale }}</em>
              </p>
              <!-- pros / cons -->
              <div v-if="opt.pros || opt.cons" class="option-proscons">
                <div v-if="opt.pros" class="pros">
                  <span class="pc-mark pc-mark--ok">+</span>
                  {{ opt.pros }}
                </div>
                <div v-if="opt.cons" class="cons">
                  <span class="pc-mark pc-mark--no">−</span>
                  {{ opt.cons }}
                </div>
              </div>
            </button>
          </div>
        </article>
      </div>
    </aside>
  </transition>
</template>

<style scoped>
.decision-panel {
  position: fixed;
  right: 20px;
  bottom: 20px;
  width: 420px;
  max-height: calc(100vh - 100px);
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: var(--shadow-lg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  z-index: 100;
  backdrop-filter: blur(8px);
}
.decision-panel.collapsed {
  width: 260px;
}

/* 滑入动画 */
.slide-enter-active,
.slide-leave-active {
  transition: all 320ms cubic-bezier(0.25, 0.46, 0.45, 0.94);
}
.slide-enter-from,
.slide-leave-to {
  transform: translateY(20px);
  opacity: 0;
}

/* 标题栏 */
.dp-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: linear-gradient(135deg,
    rgba(139, 92, 246, 0.08),
    rgba(139, 92, 246, 0.02));
  flex-shrink: 0;
}
.dp-head-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dp-icon {
  color: var(--accent);
}
.dp-title {
  font-size: 13px;
  font-weight: 600;
  margin: 0;
  color: var(--text);
}
.dp-count {
  font-size: 10.5px;
  color: var(--text-muted);
  padding-left: 4px;
}
.dp-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 4px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-muted);
  transition: all 120ms;
}
.dp-toggle:hover {
  background: var(--hover-bg);
  color: var(--text);
}

/* 决策列表 */
.dp-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px 16px;
}

.decision-card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
  margin-bottom: 14px;
}
.decision-card:last-child {
  margin-bottom: 0;
}

.dc-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 10.5px;
  color: var(--text-muted);
  margin-bottom: 6px;
}
.dc-no {
  font-weight: 600;
  color: var(--accent);
  letter-spacing: 0.05em;
}
.dc-element-id {
  font-family: ui-monospace, monospace;
}

.dc-original {
  font-size: 12.5px;
  font-style: italic;
  color: var(--text);
  margin: 4px 0 12px;
  padding-left: 10px;
  border-left: 2px solid var(--decision-voiceover);
  line-height: 1.6;
}
.dc-quote {
  color: var(--accent);
  font-weight: 700;
  font-style: normal;
}

/* 选项卡片 */
.dc-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.option {
  display: block;
  text-align: left;
  background: var(--card-bg);
  border: 1.5px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  transition: all 180ms;
  cursor: pointer;
  width: 100%;
  font-family: inherit;
}
.option:hover {
  border-color: var(--accent);
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}
.option.chosen {
  border-color: var(--accent);
  background: rgba(139, 92, 246, 0.05);
  box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.1);
}

/* 类型左色条(细) */
.option--voiceover {
  border-left: 4px solid var(--decision-voiceover);
}
.option--action_externalize {
  border-left: 4px solid var(--decision-action);
}
.option--delete {
  border-left: 4px solid var(--decision-delete);
}

.option-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 2px;
}
.option-label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text);
}
.option-rec-badge {
  display: inline-block;
  font-size: 9.5px;
  padding: 1px 6px;
  background: rgba(245, 158, 11, 0.12);
  color: var(--warning);
  border-radius: 8px;
  letter-spacing: 0.04em;
  margin-left: 4px;
}
.option-chosen-badge {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  padding: 2px 6px;
  background: var(--accent);
  color: white;
  border-radius: 8px;
}

.option-micro {
  font-size: 11px;
  color: var(--text-muted);
  margin: 0 0 6px;
}

.option-text {
  font-size: 12.5px;
  color: var(--text);
  margin: 6px 0;
  line-height: 1.55;
  padding: 6px 10px;
  background: rgba(0, 0, 0, 0.02);
  border-radius: 5px;
}

.option-rationale {
  font-size: 12px;
  color: var(--text-muted);
  margin: 6px 0;
  line-height: 1.55;
}

.option-proscons {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--border);
  font-size: 11.5px;
}
.pros,
.cons {
  display: flex;
  gap: 6px;
  align-items: flex-start;
  line-height: 1.55;
}
.pros { color: var(--success); }
.cons { color: var(--text-muted); }
.pc-mark {
  flex-shrink: 0;
  width: 14px;
  font-weight: 700;
  text-align: center;
}
.pc-mark--ok { color: var(--success); }
.pc-mark--no { color: var(--text-muted); }
</style>
