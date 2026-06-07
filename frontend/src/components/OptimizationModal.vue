<script setup lang="ts">
/**
 * AI 优化弹窗 — PR#16 核心 UI。
 *
 * 3 个阶段:
 *   1. 配置:用户选 focus(fidelity / structure / both)
 *   2. 运行中:spinner + 进度文案
 *   3. 完成:展示 change_log + reasoning + 接受 / 继续在新版上精修
 *
 * scope 由父组件传入(A=single_scene / B=full_screenplay)。
 */
import { computed, ref, watch } from "vue";

import { useScreenplayStore } from "../stores/screenplay";
import type { OptimizeFocus, OptimizeScope } from "../types/screenplay";

const props = defineProps<{
  visible: boolean;
  scope: OptimizeScope;
  targetSceneId?: string;
}>();

const emit = defineEmits<{
  (e: "close"): void;
}>();

const store = useScreenplayStore();

// ============================================================
// 阶段判定
// ============================================================

const stage = computed<"config" | "running" | "done" | "error">(() => {
  if (store.optimizingState === "running") return "running";
  if (store.optimizingState === "done" && store.lastOptimizeResult)
    return "done";
  if (store.optimizingState === "error") return "error";
  return "config";
});

// ============================================================
// 配置阶段 state
// ============================================================

const selectedFocus = ref<OptimizeFocus>("both");

// 找到 target scene 的诊断(预填给 LLM 看)
const targetSceneDiagnostic = computed(() => {
  if (props.scope !== "single_scene" || !props.targetSceneId) return null;
  const scene = store.screenplay?.scenes?.find(
    (s) => s.id === props.targetSceneId,
  );
  return scene?.fidelity ?? null;
});

const structureNotes = computed(() => {
  if (props.scope !== "full_screenplay") return [];
  return store.structureReport?.notes ?? [];
});

// 前置质量预检 — 让用户决定是否还要花时间优化
const qualityPreCheck = computed<{
  level: "high" | "ok" | "needs-fix";
  reason: string;
} | null>(() => {
  if (props.scope === "single_scene") {
    const fid = targetSceneDiagnostic.value;
    if (!fid) return null;
    const score = typeof fid.score === "number" ? fid.score : 0;
    const issues = Array.isArray(fid.issues) ? fid.issues : [];
    if (fid.level === "high" && score >= 0.8 && issues.length === 0) {
      return {
        level: "high",
        reason: "本场保真度高 (≥80) 且无诊断 issues — 可能改动很小。",
      };
    }
    if (issues.length > 0) {
      return {
        level: "needs-fix",
        reason: `检出 ${issues.length} 条诊断 issues,优化预计能改善`,
      };
    }
    return { level: "ok", reason: "本场质量一般,优化可能带来改善。" };
  }
  // full_screenplay
  const struct = store.structureReport;
  if (!struct) return null;
  const score = typeof struct.overall_score === "number" ? struct.overall_score : 0;
  const notes = struct.notes ?? [];
  if (struct.overall_health === "excellent" && score >= 75 && notes.length === 0) {
    return {
      level: "high",
      reason: "整本结构优秀 (≥75) 且无 notes — 可能改动很小。",
    };
  }
  if (notes.length > 0) {
    return {
      level: "needs-fix",
      reason: `结构报告检出 ${notes.length} 条改进建议,优化预计能改善`,
    };
  }
  return { level: "ok", reason: "整体结构尚可,优化可能带来改善。" };
});

// ============================================================
// 运行中 state
// ============================================================

const elapsed = ref<number>(0);
let timer: number | null = null;

watch(
  () => store.optimizingState,
  (s) => {
    if (s === "running") {
      elapsed.value = 0;
      timer = window.setInterval(() => {
        elapsed.value += 1;
      }, 1000);
    } else if (timer) {
      window.clearInterval(timer);
      timer = null;
    }
  },
);

const progressLabel = computed(() => {
  const t = elapsed.value;
  if (props.scope === "single_scene") {
    if (t < 5) return "正在通读场景";
    if (t < 15) return "对照诊断,寻找改写方向";
    if (t < 30) return "重写元素,推敲措辞";
    return "校验输出,即将就绪";
  } else {
    if (t < 5) return "正在通读全本";
    if (t < 15) return "依诊断,决定动哪些场";
    if (t < 40) return "改写 · 新增 · 拆合并";
    if (t < 70) return "重新组装编号";
    return "最后润色,即将就绪";
  }
});

// ============================================================
// 完成阶段
// ============================================================

const result = computed(() => store.lastOptimizeResult);

const actionLabel: Record<string, string> = {
  modified: "修改",
  added: "新增",
  removed: "删除",
  split: "拆分",
  merged: "合并",
};

const actionColor: Record<string, string> = {
  modified: "var(--accent)",
  added: "var(--success)",
  removed: "var(--danger)",
  split: "var(--warning)",
  merged: "var(--warning)",
};

// ============================================================
// 操作
// ============================================================

async function handleStart() {
  await store.runOptimize({
    scope: props.scope,
    target_scene_id: props.targetSceneId,
    focus: selectedFocus.value,
  });
  // 状态变化 → stage computed 自动切到 'done' 或 'error'
}

function handleAccept() {
  // 用户接受新版 — store 已经自动切到新版本,直接关闭
  store.clearOptimizeResult();
  emit("close");
}

function handleRetry() {
  store.clearOptimizeResult();
}

function handleClose() {
  store.clearOptimizeResult();
  emit("close");
}

// 弹窗关闭时若不接受,要切回 parent
async function handleReject() {
  if (result.value?.parent_screenplay_id) {
    await store.switchToVersion(result.value.parent_screenplay_id);
  }
  store.clearOptimizeResult();
  emit("close");
}
</script>

<template>
  <transition name="modal-fade">
    <div v-if="visible" class="modal-mask" @click.self="handleClose">
      <div class="modal-box">
        <!-- ========== 配置阶段 ========== -->
        <template v-if="stage === 'config'">
          <header class="hdr">
            <div class="hdr-icon">
              <svg
                width="28"
                height="28"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
              </svg>
            </div>
            <div>
              <h2 class="literary-heading">{{ scope === "single_scene" ? "单场精修" : "整本重排" }}</h2>
              <p class="hdr-sub">
                {{
                  scope === "single_scene"
                    ? "针对此场诊断,委托 AI 重写"
                    : "通读全本 · 可加场 / 拆合并 / 调整节奏"
                }}
              </p>
            </div>
          </header>

          <section class="cfg-body">
            <!-- 前置质量预检 — 让用户在花时间前看一眼 -->
            <div
              v-if="qualityPreCheck"
              class="precheck"
              :class="`precheck-${qualityPreCheck.level}`"
            >
              <div class="pc-icon">
                <svg
                  v-if="qualityPreCheck.level === 'high'"
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.5"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                >
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                <svg
                  v-else
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.5"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                >
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
              </div>
              <div class="pc-text">
                <div class="pc-title">
                  {{
                    qualityPreCheck.level === "high"
                      ? "质量已优 · 优化或许多此一举"
                      : qualityPreCheck.level === "needs-fix"
                      ? "有改进空间 · 推荐优化"
                      : "可优化"
                  }}
                </div>
                <div class="pc-reason">{{ qualityPreCheck.reason }}</div>
              </div>
            </div>

            <!-- 诊断预览 -->
            <div class="diag-preview">
              <div class="diag-label">输入给 AI 的诊断</div>
              <template v-if="scope === 'single_scene' && targetSceneDiagnostic">
                <div class="diag-row">
                  <span class="diag-key">保真度</span>
                  <span class="diag-value">
                    {{ targetSceneDiagnostic.level }} ·
                    {{
                      Math.round(
                        (targetSceneDiagnostic.score ?? 0) > 1
                          ? (targetSceneDiagnostic.score ?? 0)
                          : (targetSceneDiagnostic.score ?? 0) * 100,
                      )
                    }}/100
                  </span>
                </div>
                <ul v-if="targetSceneDiagnostic.issues?.length" class="diag-issues">
                  <li v-for="(iss, i) in targetSceneDiagnostic.issues" :key="i">
                    {{ iss }}
                  </li>
                </ul>
              </template>
              <template v-else-if="scope === 'full_screenplay'">
                <div class="diag-row">
                  <span class="diag-key">结构健康度</span>
                  <span class="diag-value">
                    {{ store.structureReport?.overall_health }} ·
                    {{ store.structureReport?.overall_score }}/100
                  </span>
                </div>
                <ul v-if="structureNotes.length" class="diag-issues">
                  <li v-for="(note, i) in structureNotes" :key="i">{{ note }}</li>
                </ul>
              </template>
              <div v-else class="diag-empty">无诊断,AI 将做温和优化</div>
            </div>

            <!-- focus 选择 -->
            <div class="focus-group">
              <div class="focus-label">优化重点</div>
              <div class="focus-options">
                <label
                  v-for="opt in [
                    { v: 'both', l: '全面优化', d: '保真度 + 结构' },
                    { v: 'fidelity', l: '只修保真度', d: '动作密度 / 角色 / 对白' },
                    { v: 'structure', l: '只调结构', d: '张力 / 三幕节奏' },
                  ]"
                  :key="opt.v"
                  class="focus-pill"
                  :class="{ active: selectedFocus === opt.v }"
                >
                  <input
                    type="radio"
                    :value="opt.v"
                    v-model="selectedFocus"
                    hidden
                  />
                  <div class="fp-title">{{ opt.l }}</div>
                  <div class="fp-desc">{{ opt.d }}</div>
                </label>
              </div>
            </div>

            <p class="cost-hint">
              将调用 LLM 一次 · 20–90 秒 · 失败自动回退,不影响原稿
            </p>
          </section>

          <footer class="ftr">
            <button class="btn btn-secondary" @click="handleClose">取消</button>
            <button class="btn btn-primary" @click="handleStart">
              开始重写
            </button>
          </footer>
        </template>

        <!-- ========== 运行中阶段 ========== -->
        <template v-else-if="stage === 'running'">
          <div class="running-state">
            <svg
              class="spinner-lg"
              width="48"
              height="48"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
            >
              <path d="M21 12a9 9 0 11-6.219-8.56" />
            </svg>
            <div class="running-title literary-heading">正在重写</div>
            <div class="running-label">{{ progressLabel }}</div>
            <div class="running-meta">
              已用时 {{ elapsed }}s · 不要关闭此窗口
            </div>
          </div>
        </template>

        <!-- ========== 完成阶段 ========== -->
        <template v-else-if="stage === 'done' && result">
          <header class="hdr hdr-done">
            <div class="hdr-icon hdr-icon-done">
              <svg
                width="28"
                height="28"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </div>
            <div>
              <h2>优化完成</h2>
              <p class="hdr-sub">
                {{ result.change_log.length }} 处改动 · 新版本已生成
                <span v-if="result.fallback_reason" class="hdr-warn">
                  ⚠ {{ result.fallback_reason }}
                </span>
              </p>
            </div>
          </header>

          <section class="done-body">
            <!-- AI 总体思路 -->
            <div class="reasoning-block">
              <div class="rb-label">AI 总体思路</div>
              <p class="rb-text">{{ result.reasoning }}</p>
            </div>

            <!-- change_log 列表 -->
            <div class="changelog-block">
              <div class="cb-label">改动详情</div>
              <div
                v-if="result.change_log.length === 0 && result.fallback_reason"
                class="cb-empty cb-empty-fail"
              >
                ⚠ LLM 调用失败,本次未产生改动。请点击「重新优化」再试一次。
              </div>
              <div
                v-else-if="result.change_log.length === 0"
                class="cb-empty"
              >
                AI 经过分析后认为无需改动 — 这版剧本质量足够
              </div>
              <ul v-else class="cb-list">
                <li
                  v-for="(c, i) in result.change_log"
                  :key="i"
                  class="cb-item"
                  :style="{ borderLeftColor: actionColor[c.action] }"
                >
                  <div class="cb-head">
                    <span
                      class="cb-action-pill"
                      :style="{ color: actionColor[c.action], borderColor: actionColor[c.action] }"
                    >
                      {{ actionLabel[c.action] || c.action }}
                    </span>
                    <span class="cb-scene-id">{{ c.scene_id }}</span>
                    <span
                      v-if="c.original_scene_id && c.original_scene_id !== c.scene_id"
                      class="cb-original"
                    >
                      ← 原 {{ c.original_scene_id }}
                    </span>
                  </div>
                  <div class="cb-summary">{{ c.summary }}</div>
                  <div v-if="c.addresses_diagnostic" class="cb-diag">
                    呼应诊断 — {{ c.addresses_diagnostic }}
                  </div>
                  <details v-if="c.details" class="cb-details">
                    <summary>展开技术细节</summary>
                    <p>{{ c.details }}</p>
                  </details>
                </li>
              </ul>
            </div>
          </section>

          <footer class="ftr">
            <button class="btn btn-tertiary" @click="handleReject">
              拒绝 · 回到原稿
            </button>
            <button class="btn btn-secondary" @click="handleRetry">
              重新优化
            </button>
            <button class="btn btn-primary" @click="handleAccept">
              接受此版
            </button>
          </footer>
        </template>

        <!-- ========== 错误阶段 ========== -->
        <template v-else-if="stage === 'error'">
          <div class="error-state">
            <svg
              width="40"
              height="40"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <div class="err-title">优化失败</div>
            <div class="err-msg">{{ store.optimizeError }}</div>
            <div class="err-actions">
              <button class="btn btn-secondary" @click="handleClose">关闭</button>
              <button class="btn btn-primary" @click="handleRetry">重试</button>
            </div>
          </div>
        </template>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(30, 25, 18, 0.45);
  backdrop-filter: blur(3px);
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-5);
}
.modal-box {
  background: var(--card-bg-strong);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  width: 100%;
  max-width: 600px;
  max-height: calc(100vh - 48px);
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

/* === header === */
.hdr {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-5) var(--space-6);
  background: var(--card-bg);
  border-bottom: 1px solid var(--border-soft);
}
.hdr-done {
  background: var(--success-soft);
}
.hdr-icon {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--accent-soft);
  color: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.hdr-icon-done {
  background: rgba(95, 143, 106, 0.15);
  color: var(--success);
}
.hdr h2 {
  font-size: 19px;
  margin: 0 0 4px;
  color: var(--text-strong);
  font-weight: 500;
  letter-spacing: 0.02em;
}
.hdr-sub {
  font-family: var(--font-serif);
  font-size: 12.5px;
  color: var(--text-secondary);
  margin: 0;
  letter-spacing: 0.02em;
}
.hdr-warn {
  color: var(--warning);
  margin-left: 6px;
}

/* === config body === */
/* 前置质量预检 banner */
.precheck {
  display: flex;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-4);
  border: 1px solid;
}
.pc-icon {
  flex-shrink: 0;
  display: flex;
  align-items: flex-start;
  padding-top: 2px;
}
.pc-text {
  flex: 1;
}
.pc-title {
  font-family: var(--font-serif);
  font-size: 13.5px;
  font-weight: 500;
  letter-spacing: 0.02em;
}
.pc-reason {
  margin-top: 2px;
  font-size: 11.5px;
  color: var(--text-secondary);
  letter-spacing: 0.02em;
}
.precheck-high {
  background: var(--success-soft);
  border-color: var(--success);
  color: var(--success);
}
.precheck-high .pc-title {
  color: var(--text-strong);
}
.precheck-needs-fix {
  background: var(--warning-soft);
  border-color: var(--warning);
  color: var(--warning);
}
.precheck-needs-fix .pc-title {
  color: var(--text-strong);
}
.precheck-ok {
  background: var(--bg);
  border-color: var(--border);
  color: var(--text-secondary);
}
.precheck-ok .pc-title {
  color: var(--text);
}

.cfg-body {
  padding: var(--space-5) var(--space-6);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.diag-preview {
  background: var(--bg);
  border-radius: 8px;
  padding: 12px 14px;
}
.diag-label {
  font-size: 10.5px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 6px;
}
.diag-row {
  display: flex;
  font-size: 12px;
  gap: 6px;
}
.diag-key {
  color: var(--text-muted);
}
.diag-value {
  color: var(--text);
  font-weight: 500;
}
.diag-issues {
  margin: 6px 0 0;
  padding-left: 16px;
  font-size: 11.5px;
  color: var(--text);
  line-height: 1.6;
}
.diag-empty {
  font-size: 12px;
  color: var(--text-muted);
  font-style: italic;
}

.focus-label {
  font-size: 10.5px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 8px;
}
.focus-options {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 8px;
}
.focus-pill {
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 150ms;
  background: var(--card-bg);
}
.focus-pill:hover {
  border-color: var(--accent);
  background: var(--hover-bg);
}
.focus-pill.active {
  border-color: var(--accent);
  background: rgba(139, 92, 246, 0.08);
}
.fp-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 2px;
}
.fp-desc {
  font-size: 10.5px;
  color: var(--text-muted);
}

.cost-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin: 0;
  padding-top: 6px;
  border-top: 1px dashed var(--border);
}

/* === footer === */
.ftr {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 12px 22px;
  border-top: 1px solid var(--border);
  background: var(--bg);
}
.btn {
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid transparent;
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  transition: all 150ms;
}
.btn-primary {
  background: var(--accent);
  color: white;
}
.btn-primary:hover {
  background: var(--accent-hover, #7c3aed);
}
.btn-secondary {
  background: var(--card-bg);
  color: var(--text);
  border-color: var(--border);
}
.btn-secondary:hover {
  background: var(--hover-bg);
}
.btn-tertiary {
  background: transparent;
  color: var(--text-muted);
}
.btn-tertiary:hover {
  color: var(--danger);
}

/* === running === */
.running-state {
  padding: 60px 22px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}
.spinner-lg {
  color: var(--accent);
  animation: spin 1.1s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.running-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
}
.running-label {
  font-size: 12.5px;
  color: var(--accent);
}
.running-meta {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
}

/* === done body === */
.done-body {
  padding: 18px 22px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.reasoning-block {
  background: linear-gradient(
    135deg,
    rgba(16, 185, 129, 0.06),
    rgba(16, 185, 129, 0.02)
  );
  border: 1px solid rgba(16, 185, 129, 0.15);
  border-radius: 8px;
  padding: 12px 14px;
}
.rb-label {
  font-size: 10.5px;
  color: var(--success);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 6px;
  font-weight: 600;
}
.rb-text {
  font-size: 12.5px;
  color: var(--text);
  line-height: 1.7;
  margin: 0;
}

.cb-label {
  font-size: 10.5px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 8px;
}
.cb-empty {
  text-align: center;
  padding: var(--space-5);
  background: var(--bg);
  border-radius: var(--radius-md);
  color: var(--text-muted);
  font-size: 13px;
  font-family: var(--font-serif);
  letter-spacing: 0.02em;
}
.cb-empty-fail {
  background: var(--warning-soft);
  color: var(--warning);
  border: 1px solid var(--warning);
  font-family: var(--font-sans);
  letter-spacing: 0;
}
.cb-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cb-item {
  background: var(--bg);
  border-radius: 8px;
  padding: 10px 14px;
  border-left: 3px solid var(--accent);
}
.cb-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.cb-action-pill {
  font-size: 10.5px;
  font-weight: 600;
  border: 1px solid;
  padding: 1px 6px;
  border-radius: 10px;
  letter-spacing: 0.04em;
}
.cb-scene-id {
  font-family: ui-monospace, monospace;
  font-size: 11px;
  color: var(--text);
  font-weight: 500;
}
.cb-original {
  font-family: ui-monospace, monospace;
  font-size: 10.5px;
  color: var(--text-muted);
}
.cb-summary {
  font-size: 12.5px;
  color: var(--text);
  line-height: 1.6;
}
.cb-diag {
  margin-top: 4px;
  font-size: 11px;
  color: var(--text-muted);
  font-style: italic;
}
.cb-details {
  margin-top: 6px;
  font-size: 11.5px;
}
.cb-details summary {
  cursor: pointer;
  color: var(--accent);
  font-size: 11px;
  font-weight: 500;
}
.cb-details p {
  margin: 6px 0 0;
  color: var(--text);
  line-height: 1.6;
  padding-left: 8px;
  border-left: 2px dashed var(--border);
}

/* === error === */
.error-state {
  padding: 50px 22px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: var(--danger);
}
.err-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}
.err-msg {
  font-size: 11.5px;
  color: var(--text-muted);
  text-align: center;
  max-width: 80%;
}
.err-actions {
  margin-top: 14px;
  display: flex;
  gap: 10px;
}

/* === transitions === */
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 200ms;
}
.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
</style>
