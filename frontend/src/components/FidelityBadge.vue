<script setup lang="ts">
/**
 * Fidelity 评分徽章 — PR#12。
 *
 * scene 卡片右上角的小徽章,显示 high / medium / low 三色之一。
 * 鼠标悬停时上方弹出 popover,展示 4 个维度 + 进度条 + 人话原因。
 */
import { computed, ref } from "vue";

import type { Fidelity } from "../types/screenplay";

const props = defineProps<{ fidelity: Fidelity }>();

const hover = ref<boolean>(false);

const levelLabel = computed(() => {
  return { high: "高", medium: "中", low: "低" }[props.fidelity.level] ?? "—";
});

const levelFull = computed(() => {
  return {
    high: "高保真",
    medium: "中保真",
    low: "低保真",
  }[props.fidelity.level] ?? "—";
});

const scorePercent = computed(() => {
  if (typeof props.fidelity.score !== "number") return null;
  return Math.round(props.fidelity.score * 100);
});

// 维度中文标签
const dimLabel: Record<string, string> = {
  dialogue_coverage: "对白覆盖度",
  character_alignment: "角色一致性",
  element_density: "元素密度",
  decision_completeness: "决策完整度",
};

function dimDisplay(name: string): string {
  return dimLabel[name] ?? name;
}

function dimColor(score: number): string {
  if (score >= 0.8) return "var(--success)";
  if (score >= 0.55) return "var(--warning)";
  return "var(--danger)";
}

function open() { hover.value = true; }
function close() { hover.value = false; }
</script>

<template>
  <div
    class="fidelity-badge-wrap"
    @mouseenter="open"
    @mouseleave="close"
    @focusin="open"
    @focusout="close"
  >
    <button
      :class="['badge', `badge--${fidelity.level}`]"
      tabindex="0"
      :title="levelFull"
    >
      <span class="badge-dot"></span>
      <span class="badge-label">{{ levelLabel }}</span>
      <span v-if="scorePercent !== null" class="badge-score">
        {{ scorePercent }}
      </span>
    </button>

    <transition name="popfade">
      <div v-if="hover" class="popover" @click.stop>
        <header class="pop-head">
          <span :class="['pop-dot', `pop-dot--${fidelity.level}`]"></span>
          <span class="pop-title">{{ levelFull }}</span>
          <span v-if="scorePercent !== null" class="pop-score">
            综合 {{ scorePercent }} / 100
          </span>
        </header>

        <p v-if="fidelity.reason" class="pop-reason">{{ fidelity.reason }}</p>

        <ul v-if="fidelity.dimensions" class="dim-list">
          <li
            v-for="dim in fidelity.dimensions"
            :key="dim.name"
            class="dim-row"
          >
            <div class="dim-label">{{ dimDisplay(dim.name) }}</div>
            <div class="dim-bar">
              <div
                class="dim-fill"
                :style="{
                  width: Math.round(dim.score * 100) + '%',
                  background: dimColor(dim.score),
                }"
              ></div>
            </div>
            <div class="dim-score">{{ Math.round(dim.score * 100) }}</div>
            <div v-if="dim.reason" class="dim-reason">{{ dim.reason }}</div>
          </li>
        </ul>

        <div
          v-if="fidelity.issues && fidelity.issues.length > 0"
          class="issues"
        >
          <h4 class="issues-title">
            <svg
              width="11"
              height="11"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            建议复核
          </h4>
          <ul class="issues-list">
            <li v-for="(issue, idx) in fidelity.issues" :key="idx">
              {{ issue }}
            </li>
          </ul>
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.fidelity-badge-wrap {
  position: relative;
  display: inline-block;
}

/* === 徽章 === */
.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px 3px 6px;
  border-radius: 10px;
  border: 1px solid;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.04em;
  background: transparent;
  transition: all 120ms;
  cursor: help;
  font-family: inherit;
}
.badge:hover {
  transform: translateY(-1px);
}

.badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.badge-label {
  font-weight: 700;
}
.badge-score {
  font-variant-numeric: tabular-nums;
  font-size: 10px;
  opacity: 0.7;
  padding-left: 2px;
}

.badge--high {
  color: var(--success);
  border-color: rgba(16, 185, 129, 0.4);
  background: rgba(16, 185, 129, 0.08);
}
.badge--high .badge-dot { background: var(--success); }

.badge--medium {
  color: var(--warning);
  border-color: rgba(245, 158, 11, 0.4);
  background: rgba(245, 158, 11, 0.1);
}
.badge--medium .badge-dot { background: var(--warning); }

.badge--low {
  color: var(--danger);
  border-color: rgba(239, 68, 68, 0.4);
  background: rgba(239, 68, 68, 0.1);
}
.badge--low .badge-dot { background: var(--danger); }

/* === Popover === */
.popover {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 280px;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow-lg);
  padding: 12px 14px;
  z-index: 50;
  font-family:
    -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
}

.popfade-enter-active,
.popfade-leave-active {
  transition: all 180ms cubic-bezier(0.25, 0.46, 0.45, 0.94);
}
.popfade-enter-from,
.popfade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.pop-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 10px;
}
.pop-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.pop-dot--high { background: var(--success); }
.pop-dot--medium { background: var(--warning); }
.pop-dot--low { background: var(--danger); }
.pop-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
}
.pop-score {
  margin-left: auto;
  font-size: 10.5px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.pop-reason {
  font-size: 11.5px;
  color: var(--text);
  line-height: 1.55;
  margin: 0 0 12px;
}

/* === 维度列表 === */
.dim-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.dim-row {
  display: grid;
  grid-template-columns: 70px 1fr 28px;
  align-items: center;
  gap: 6px;
  font-size: 10.5px;
}
.dim-label {
  color: var(--text);
  font-weight: 500;
}
.dim-bar {
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
}
.dim-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 240ms ease-out;
}
.dim-score {
  text-align: right;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}
.dim-reason {
  grid-column: 1 / -1;
  font-size: 10.5px;
  color: var(--text-muted);
  line-height: 1.5;
  padding: 2px 0 4px 4px;
  border-left: 2px solid var(--border);
  padding-left: 8px;
}

/* === Issues === */
.issues {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--border);
}
.issues-title {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--warning);
  margin: 0 0 4px;
}
.issues-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.issues-list li {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.5;
  padding-left: 14px;
  position: relative;
}
.issues-list li::before {
  content: "·";
  position: absolute;
  left: 6px;
  color: var(--warning);
  font-weight: 700;
}
</style>
