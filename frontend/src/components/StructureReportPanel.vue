<script setup lang="ts">
/**
 * 剧本结构报告 — PR#13。
 *
 * SVG 张力曲线 + 三幕分区背景 + 关键节点标记。
 * 顶部入口可折叠。
 */
import { computed, inject, onMounted, ref } from "vue";

import { useScreenplayStore } from "../stores/screenplay";
import type { OptimizeScope, TensionPoint } from "../types/screenplay";

// 从父组件 ScreenplayEditorView 注入"打开优化弹窗"方法
const openOptimization = inject<
  (scope: OptimizeScope, sceneId?: string) => void
>("openOptimizationModal", () => {});

const store = useScreenplayStore();
const collapsed = ref<boolean>(false);

// 视口尺寸
const SVG_WIDTH = 720;
const SVG_HEIGHT = 160;
const PADDING_TOP = 18;
const PADDING_BOTTOM = 26;
const PADDING_LEFT = 36;
const PADDING_RIGHT = 12;

const CHART_W = SVG_WIDTH - PADDING_LEFT - PADDING_RIGHT;
const CHART_H = SVG_HEIGHT - PADDING_TOP - PADDING_BOTTOM;

const points = computed<TensionPoint[]>(
  () => store.structureReport?.points ?? [],
);
const acts = computed(() => store.structureReport?.acts ?? []);
const notes = computed(() => store.structureReport?.notes ?? []);
const overallHealth = computed(
  () => store.structureReport?.overall_health ?? "good",
);
const overallScore = computed(() => {
  const s = store.structureReport?.overall_score;
  return typeof s === "number" ? Math.round(s * 100) : null;
});

const healthLabel: Record<string, string> = {
  excellent: "结构优秀",
  good: "结构良好",
  uneven: "节奏不均",
  flat: "曲线偏平",
};

const healthColor: Record<string, string> = {
  excellent: "var(--success)",
  good: "var(--success)",
  uneven: "var(--warning)",
  flat: "var(--danger)",
};

function xForIndex(i: number, total: number): number {
  if (total <= 1) return PADDING_LEFT + CHART_W / 2;
  return PADDING_LEFT + (i / (total - 1)) * CHART_W;
}

function yForTension(t: number): number {
  return PADDING_TOP + (1 - t) * CHART_H;
}

const linePath = computed(() => {
  const pts = points.value;
  if (pts.length === 0) return "";
  const total = pts.length;
  return pts
    .map(
      (p, i) =>
        `${i === 0 ? "M" : "L"}${xForIndex(i, total).toFixed(1)},${yForTension(p.tension).toFixed(1)}`,
    )
    .join(" ");
});

const areaPath = computed(() => {
  const pts = points.value;
  if (pts.length === 0) return "";
  const total = pts.length;
  const top = pts
    .map(
      (p, i) =>
        `${i === 0 ? "M" : "L"}${xForIndex(i, total).toFixed(1)},${yForTension(p.tension).toFixed(1)}`,
    )
    .join(" ");
  const lastX = xForIndex(total - 1, total).toFixed(1);
  const firstX = xForIndex(0, total).toFixed(1);
  const baseY = (PADDING_TOP + CHART_H).toFixed(1);
  return `${top} L${lastX},${baseY} L${firstX},${baseY} Z`;
});

// 三幕区段(背景颜色块)
interface ActBand {
  act: number;
  x: number;
  width: number;
  color: string;
  label: string;
  scene_count: number;
  avg_tension: number;
}

const actBands = computed<ActBand[]>(() => {
  const pts = points.value;
  if (pts.length === 0 || acts.value.length === 0) return [];
  const total = pts.length;
  const colors = [
    "rgba(16, 185, 129, 0.07)", // act 1 — 绿(立)
    "rgba(245, 158, 11, 0.07)", // act 2 — 黄(冲)
    "rgba(239, 68, 68, 0.07)", // act 3 — 红(收)
  ];
  const labels = ["第一幕 · 立", "第二幕 · 冲", "第三幕 · 收"];

  return acts.value.map((a) => {
    const startIdx = pts.findIndex((p) => p.number === a.start_scene_number);
    const endIdx = pts.findIndex((p) => p.number === a.end_scene_number);
    if (startIdx < 0 || endIdx < 0) {
      return {
        act: a.act,
        x: PADDING_LEFT,
        width: 0,
        color: colors[a.act - 1] ?? "transparent",
        label: labels[a.act - 1] ?? `第${a.act}幕`,
        scene_count: a.scene_count,
        avg_tension: a.avg_tension,
      };
    }
    // 区段从左起点到下一幕起点
    const xStart = xForIndex(startIdx, total);
    let xEnd: number;
    if (endIdx === total - 1) {
      xEnd = PADDING_LEFT + CHART_W;
    } else {
      xEnd = xForIndex(endIdx + 1, total);
    }
    if (startIdx === 0) {
      // 第一段贴左边
      // 不改 xStart
    }
    return {
      act: a.act,
      x: xStart,
      width: Math.max(0, xEnd - xStart),
      color: colors[a.act - 1] ?? "transparent",
      label: labels[a.act - 1] ?? `第${a.act}幕`,
      scene_count: a.scene_count,
      avg_tension: a.avg_tension,
    };
  });
});

// 关键节点标记
interface BeatMarker {
  point: TensionPoint;
  cx: number;
  cy: number;
  label: string;
  color: string;
}

const beatMarkers = computed<BeatMarker[]>(() => {
  const pts = points.value;
  const total = pts.length;
  const out: BeatMarker[] = [];
  pts.forEach((p, i) => {
    if (p.is_inciting_incident) {
      out.push({
        point: p,
        cx: xForIndex(i, total),
        cy: yForTension(p.tension),
        label: "触发事件",
        color: "var(--success)",
      });
    }
    if (p.is_midpoint) {
      out.push({
        point: p,
        cx: xForIndex(i, total),
        cy: yForTension(p.tension),
        label: "中点反转",
        color: "var(--warning)",
      });
    }
    if (p.is_climax) {
      out.push({
        point: p,
        cx: xForIndex(i, total),
        cy: yForTension(p.tension),
        label: "高潮",
        color: "var(--danger)",
      });
    }
  });
  return out;
});

// 鼠标悬停 — 只显示 tooltip 数据,不跳转 scene(用户反馈)
const hoverIndex = ref<number | null>(null);

function handleHover(i: number) {
  hoverIndex.value = i;
  // 注:hover 仅展示 tooltip,不自动 selectScene
  // 跳转需要用户主动点击数据点(handleClick)
}

function handleLeave() {
  hoverIndex.value = null;
}

function handleClick(i: number) {
  // 点击才同步选中右栏 scene(明确的用户意图)
  const p = points.value[i];
  if (p) {
    store.selectScene(p.scene_id);
  }
}

const hoverPoint = computed(() =>
  hoverIndex.value !== null ? points.value[hoverIndex.value] : null,
);

// 当 screenplay 加载完即拉结构(由父组件 mount 时触发,这里只在缺数据时拉)
onMounted(() => {
  if (store.screenplayId && !store.structureReport) {
    store.loadStructureReport();
  }
});

function toggle() {
  collapsed.value = !collapsed.value;
}
</script>

<template>
  <section v-if="points.length > 0" class="structure-panel" :class="{ collapsed }">
    <header class="panel-header">
      <div class="header-left">
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M3 3v18h18" />
          <path d="M7 14l4-4 4 6 5-9" />
        </svg>
        <h3>结构报告</h3>
        <span
          class="health-pill"
          :style="{ color: healthColor[overallHealth], borderColor: healthColor[overallHealth] }"
        >
          {{ healthLabel[overallHealth] }}
          <span v-if="overallScore !== null" class="health-score">
            {{ overallScore }}
          </span>
        </span>
      </div>
      <button class="toggle-btn" @click="toggle" :title="collapsed ? '展开' : '收起'">
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
          <polyline points="6 9 12 15 18 9" />
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
          <polyline points="18 15 12 9 6 15" />
        </svg>
      </button>
    </header>

    <div v-if="!collapsed" class="panel-body">
      <!-- SVG 曲线 -->
      <div class="chart-wrap">
        <svg
          :viewBox="`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`"
          preserveAspectRatio="xMidYMid meet"
          class="chart-svg"
          @mouseleave="handleLeave"
        >
          <!-- 三幕背景 -->
          <g class="act-bands">
            <rect
              v-for="band in actBands"
              :key="band.act"
              :x="band.x"
              :y="PADDING_TOP"
              :width="band.width"
              :height="CHART_H"
              :fill="band.color"
            />
          </g>

          <!-- Y 轴网格(0.25 / 0.5 / 0.75 / 1.0) -->
          <g class="y-grid">
            <line
              v-for="t in [0.25, 0.5, 0.75, 1.0]"
              :key="t"
              :x1="PADDING_LEFT"
              :x2="PADDING_LEFT + CHART_W"
              :y1="yForTension(t)"
              :y2="yForTension(t)"
              stroke="var(--border)"
              stroke-dasharray="3 3"
              stroke-width="0.8"
            />
            <text
              v-for="t in [0, 0.5, 1.0]"
              :key="`l${t}`"
              :x="PADDING_LEFT - 6"
              :y="yForTension(t) + 3"
              text-anchor="end"
              class="y-label"
            >
              {{ t.toFixed(1) }}
            </text>
          </g>

          <!-- 填充区域 -->
          <path :d="areaPath" fill="rgba(139, 92, 246, 0.12)" />

          <!-- 张力曲线 -->
          <path
            :d="linePath"
            fill="none"
            stroke="var(--accent)"
            stroke-width="2.2"
            stroke-linejoin="round"
            stroke-linecap="round"
          />

          <!-- 数据点(hover 看数据 / 点击跳转 scene)-->
          <g class="data-points">
            <g
              v-for="(p, i) in points"
              :key="p.scene_id"
              @mouseenter="handleHover(i)"
              @click="handleClick(i)"
            >
              <!-- 透明 hit area -->
              <circle
                :cx="xForIndex(i, points.length)"
                :cy="yForTension(p.tension)"
                r="14"
                fill="transparent"
              />
              <!-- 可见点 -->
              <circle
                :cx="xForIndex(i, points.length)"
                :cy="yForTension(p.tension)"
                :r="hoverIndex === i ? 5 : 3"
                :fill="hoverIndex === i ? 'var(--accent)' : 'white'"
                :stroke="hoverIndex === i ? 'white' : 'var(--accent)'"
                stroke-width="2"
              />
            </g>
          </g>

          <!-- 关键节点 -->
          <g class="beat-markers">
            <g v-for="(b, idx) in beatMarkers" :key="`beat-${idx}`">
              <circle
                :cx="b.cx"
                :cy="b.cy"
                r="6"
                fill="transparent"
                :stroke="b.color"
                stroke-width="1.5"
                stroke-dasharray="2 2"
              />
              <line
                :x1="b.cx"
                :x2="b.cx"
                :y1="b.cy + 8"
                :y2="PADDING_TOP + CHART_H + 4"
                :stroke="b.color"
                stroke-width="1"
                stroke-dasharray="2 2"
              />
              <text
                :x="b.cx"
                :y="PADDING_TOP + CHART_H + 17"
                text-anchor="middle"
                :fill="b.color"
                class="beat-label"
              >
                {{ b.label }}
              </text>
            </g>
          </g>

          <!-- 三幕标签 -->
          <g class="act-labels">
            <text
              v-for="band in actBands"
              :key="`acttxt-${band.act}`"
              :x="band.x + band.width / 2"
              :y="PADDING_TOP - 5"
              text-anchor="middle"
              class="act-label"
            >
              {{ band.label }}
            </text>
          </g>
        </svg>

        <!-- Hover tooltip -->
        <div
          v-if="hoverPoint"
          class="hover-info"
        >
          <strong>SCENE {{ String(hoverPoint.number).padStart(3, "0") }}</strong>
          · 张力 {{ Math.round(hoverPoint.tension * 100) }}
          · 第 {{ hoverPoint.act }} 幕
        </div>
      </div>

      <!-- 三幕统计 -->
      <div class="acts-strip">
        <div
          v-for="band in actBands"
          :key="`stat-${band.act}`"
          class="act-stat"
        >
          <span class="act-name">{{ band.label }}</span>
          <span class="act-meta">
            {{ band.scene_count }} 场 · 平均张力 {{ Math.round(band.avg_tension * 100) }}
          </span>
        </div>
      </div>

      <!-- Notes -->
      <ul v-if="notes.length > 0" class="notes-list">
        <li v-for="(n, i) in notes" :key="i">
          <span class="bullet">·</span>
          {{ n }}
        </li>
      </ul>

      <!-- B 入口:整本重排 (PR#16) -->
      <div class="optimize-cta">
        <button
          class="optimize-b-btn"
          @click="openOptimization('full_screenplay')"
          :disabled="store.optimizingState === 'running'"
          title="委托 AI 通读全本,按诊断重排"
        >
          <span class="b-btn-main">整本重排</span>
          <span class="b-btn-hint">委托 AI 按诊断重写</span>
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.structure-panel {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--card-bg);
  margin-bottom: 14px;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-3) var(--space-4);
  background: var(--card-bg);
  border-bottom: 1px solid var(--border-soft);
}
.structure-panel.collapsed .panel-header {
  border-bottom: none;
}
.header-left {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  color: var(--accent);
}
.header-left h3 {
  font-family: var(--font-serif);
  font-size: 14px;
  margin: 0;
  color: var(--text-strong);
  font-weight: 500;
  letter-spacing: 0.04em;
}

.health-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 10px;
  border-radius: 12px;
  font-size: 10.5px;
  font-weight: 500;
  border: 1px solid;
  background: transparent;
  letter-spacing: 0.04em;
}
.health-score {
  font-variant-numeric: tabular-nums;
  opacity: 0.75;
}

.toggle-btn {
  width: 24px;
  height: 24px;
  border-radius: 4px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-muted);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.toggle-btn:hover {
  background: var(--hover-bg);
  color: var(--text);
}

.panel-body {
  padding: 14px;
}

/* === Chart === */
.chart-wrap {
  position: relative;
}
.chart-svg {
  width: 100%;
  height: auto;
  display: block;
}

.y-label {
  font-size: 9px;
  fill: var(--text-muted);
  font-family: ui-monospace, monospace;
}

.act-label {
  font-size: 9.5px;
  fill: var(--text-muted);
  font-weight: 600;
  letter-spacing: 0.04em;
}

.beat-label {
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.data-points g {
  cursor: pointer;
}

.hover-info {
  position: absolute;
  top: 6px;
  right: 12px;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 11px;
  color: var(--text);
  box-shadow: var(--shadow-sm);
  font-family: ui-monospace, monospace;
}
.hover-info strong {
  color: var(--accent);
}

/* === Acts strip === */
.acts-strip {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 6px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--border);
}
.act-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 10px;
  background: var(--bg);
  border-radius: 6px;
  font-size: 11px;
}
.act-name {
  font-weight: 600;
  color: var(--text);
}
.act-meta {
  font-size: 10.5px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

/* === Notes === */
/* B 入口 — 整本重排按钮 */
.optimize-cta {
  margin-top: var(--space-4);
  padding-top: var(--space-4);
  border-top: 1px solid var(--border-soft);
  display: flex;
  justify-content: center;
}
.optimize-b-btn {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: var(--space-3) var(--space-5);
  background: transparent;
  color: var(--accent-text);
  border: 1px solid var(--accent);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.optimize-b-btn:hover:not(:disabled) {
  background: var(--accent);
  color: white;
}
.optimize-b-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.b-btn-main {
  font-family: var(--font-serif);
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 0.08em;
}
.b-btn-hint {
  font-size: 10px;
  opacity: 0.7;
  letter-spacing: 0.06em;
  font-family: var(--font-sans);
}

.notes-list {
  list-style: none;
  margin: 12px 0 0;
  padding: 12px 0 0;
  border-top: 1px dashed var(--border);
}
.notes-list li {
  display: flex;
  gap: 6px;
  font-size: 11.5px;
  color: var(--text);
  line-height: 1.6;
  padding: 2px 0;
}
.bullet {
  color: var(--accent);
  font-weight: 700;
}
</style>
