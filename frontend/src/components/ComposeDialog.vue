<script setup lang="ts">
/**
 * 编排对话框 — PR#11 commit 4。
 *
 * 用户点击"生成剧本"前确认选项 + 显示进度。POST /compose-screenplay
 * 是同步的,跑 30-60s,所以只能 spinner + 阶段提示,无法实时 chapter 进度。
 *
 * 状态:
 *   - 用户配置阶段:显示 3 个 toggle + "开始生成" / "取消"
 *   - composing 阶段:spinner + 估时 + 进度文案
 *   - error:错误信息 + "重试"
 */
import { computed, ref, watch } from "vue";

import { useScreenplayStore } from "../stores/screenplay";

const props = defineProps<{ visible: boolean }>();
const emit = defineEmits<{
  (e: "close"): void;
}>();

const store = useScreenplayStore();

const refineDialogue = ref<boolean>(true);
const proposeDecisions = ref<boolean>(true);
const maxChapters = ref<number | null>(null);

// 动态估时 — 基于实际 LLM 调用次数 + 经验性的单次耗时
// 经验数据(deepseek-chat / 中文长 prompt):
//   scene_splitter: ~25 秒/章
//   element_extractor: ~30 秒/章(假定每章约 1.5 场景)
//   dialogue_attributor(PR#8 可选): ~25 秒/章
//   adaptation_decision(PR#9 可选): ~35 秒/章
//   故事圣经抽取: ~30 秒 一次性
const totalChapters = computed(() => store.novelChapters?.length ?? 0);
const effectiveChapters = computed(() => {
  if (maxChapters.value && maxChapters.value > 0) {
    return Math.min(maxChapters.value, totalChapters.value);
  }
  return totalChapters.value;
});

// 精确估时 — 返秒数
const estimateSeconds = computed(() => {
  const chs = effectiveChapters.value;
  if (chs === 0) return 0;
  // 一次性开销:故事圣经抽取 + 最终组装
  let baseline = 30;
  // 每章必跑:scene_splitter + element_extractor
  let perCh = 25 + 30;
  if (refineDialogue.value) perCh += 25;    // PR#8
  if (proposeDecisions.value) perCh += 35;   // PR#9
  return baseline + chs * perCh;
});

// 文案版估时
const estimateMinutes = computed(() => {
  const total = estimateSeconds.value;
  if (total === 0) return "—";
  if (total < 90) return `约 ${total} 秒`;
  const mins = Math.round(total / 60);
  return `约 ${mins} 分钟`;
});

const isLargeNovel = computed(() => totalChapters.value > 5);

// banner 用 — 跑完整本要多久
const fullNovelEstimateLabel = computed(() => {
  const chs = totalChapters.value;
  if (chs === 0) return "—";
  let baseline = 30;
  let perCh = 25 + 30;
  if (refineDialogue.value) perCh += 25;
  if (proposeDecisions.value) perCh += 35;
  const total = baseline + chs * perCh;
  if (total < 90) return `约 ${total} 秒`;
  const mins = Math.round(total / 60);
  return `约 ${mins} 分钟`;
});

// 大小说自动建议 max_chapters
watch(
  totalChapters,
  (n) => {
    if (n > 5 && maxChapters.value === null) {
      maxChapters.value = 3;
    }
  },
  { immediate: true },
);

const stage = computed(() => {
  if (store.loadingState === "composing") return "composing";
  if (store.loadingState === "error" && store.lastError) return "error";
  return "config";
});

const elapsed = ref<number>(0);
let timer: number | null = null;

watch(
  () => store.loadingState,
  (s) => {
    if (s === "composing") {
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

// 进度文案 — 按实际进度比例划分阶段(不是写死秒数)
const progressLabel = computed(() => {
  const ratio = estimateSeconds.value > 0 ? elapsed.value / estimateSeconds.value : 0;
  if (ratio < 0.05) return "正在准备 LLM 流水线…";
  if (ratio < 0.15) return "提取故事圣经…";
  if (ratio < 0.45) return "切分场景 + 抽取元素…";
  if (ratio < 0.75) {
    if (refineDialogue.value) return "对白归属精修中…";
    return "组装中…";
  }
  if (ratio < 0.95) {
    if (proposeDecisions.value) return "生成改编决策建议…";
    return "组装中…";
  }
  if (ratio < 1.1) return "组装 YAML + Schema 校验…";
  return "LLM 比预估慢,请耐心等待…";
});

// 进度百分比 — 真实参照预估总时间
const progressPercent = computed(() => {
  if (estimateSeconds.value === 0) return 0;
  const ratio = elapsed.value / estimateSeconds.value;
  if (ratio < 1) {
    // 正常进度区间:0-90% 跟随实际时间
    return Math.round(ratio * 90);
  }
  // 已超时:慢慢爬向 95%(每超 10 秒涨 1%)
  const overflowSec = elapsed.value - estimateSeconds.value;
  return Math.min(95, 90 + Math.floor(overflowSec / 10));
});

// 超时态判定
const isOvertime = computed(
  () => estimateSeconds.value > 0 && elapsed.value > estimateSeconds.value,
);
const overtimeRatio = computed(() => {
  if (estimateSeconds.value === 0) return 1;
  return elapsed.value / estimateSeconds.value;
});

// 顶部副标题 — 真实秒数 + 预估
const composingSubtitle = computed(() => {
  const sec = elapsed.value;
  const est = estimateSeconds.value;
  if (est === 0) return `${sec} 秒`;
  if (sec <= est) {
    return `${sec} 秒 · 预估总耗时 ${estimateMinutes.value}`;
  }
  // 超时态
  const over = sec - est;
  const pct = Math.round(overtimeRatio.value * 100);
  return `${sec} 秒 · 已超预估 ${over} 秒 (${pct}%)`;
});

async function handleStart() {
  if (!store.novelId) return;
  await store.triggerCompose(store.novelId, {
    refine_dialogue: refineDialogue.value,
    propose_decisions: proposeDecisions.value,
    max_chapters: maxChapters.value,
  });
  // 成功 / 失败后让 watcher 处理后续 UI
  if (store.loadingState === "ready") {
    emit("close");
  }
}

function handleCancel() {
  if (store.loadingState !== "composing") emit("close");
}

function handleRetry() {
  store.lastError = "";
  handleStart();
}
</script>

<template>
  <transition name="fade">
    <div v-if="props.visible" class="overlay" @click.self="handleCancel">
      <div class="dialog">
        <!-- 头部 -->
        <header class="d-head">
          <div class="d-head-icon">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="M12 2l2.4 7.4H22l-6 4.6 2.3 7.4-6.3-4.6-6.3 4.6L8 14l-6-4.6h7.6z" />
            </svg>
          </div>
          <div class="d-head-text">
            <h3>{{ stage === "config" ? "生成剧本" : stage === "composing" ? "AI 编排中" : "生成失败" }}</h3>
            <p v-if="stage === 'config'">配置流水线选项,确认后开始</p>
            <p
              v-else-if="stage === 'composing'"
              :class="{ 'd-warn': isOvertime }"
            >
              {{ composingSubtitle }}
            </p>
            <p v-else class="d-err">无法完成编排</p>
          </div>
          <button
            v-if="stage !== 'composing'"
            class="d-close"
            @click="emit('close')"
            title="关闭"
          >
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
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </header>

        <!-- 内容 -->
        <main class="d-body">
          <!-- 配置阶段 -->
          <div v-if="stage === 'config'" class="config-stage">
            <!-- 大小说警告 banner -->
            <div v-if="isLargeNovel" class="large-novel-banner">
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
              <div class="lnb-text">
                <strong>你的小说共 {{ totalChapters }} 章 · 完整跑预估 {{ fullNovelEstimateLabel }}</strong>
                <div class="lnb-hint">
                  已为你预设 <strong>仅跑前 3 章</strong> — 想全跑请把下方"章节数上限"清空。
                </div>
              </div>
            </div>

            <label class="toggle-row">
              <div class="toggle-text">
                <div class="t-title">对白归属精修</div>
                <div class="t-hint">PR#8 二段式 AI — 代词消解 + 上下文推断</div>
              </div>
              <input v-model="refineDialogue" type="checkbox" class="toggle" />
            </label>

            <label class="toggle-row">
              <div class="toggle-text">
                <div class="t-title">
                  改编决策建议
                  <span class="differentiation-pill">差异化</span>
                </div>
                <div class="t-hint">
                  内心独白 → V.O. / 动作外化 / 潜台词 / 意象化 / 删除 5 备选
                </div>
              </div>
              <input v-model="proposeDecisions" type="checkbox" class="toggle" />
            </label>

            <label class="number-row">
              <div class="toggle-text">
                <div class="t-title">章节数上限</div>
                <div class="t-hint">仅跑前 N 章(留空则全跑)</div>
              </div>
              <input
                v-model.number="maxChapters"
                type="number"
                min="1"
                max="100"
                placeholder="全部"
                class="number-input"
              />
            </label>

            <div class="estimate">
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
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
              预估耗时:<strong>{{ estimateMinutes }}</strong>
              <span class="est-detail">· 跑 {{ effectiveChapters }}/{{ totalChapters }} 章</span>
            </div>
          </div>

          <!-- 进度阶段 -->
          <div v-else-if="stage === 'composing'" class="composing-stage">
            <div class="spinner">
              <svg width="40" height="40" viewBox="0 0 24 24">
                <circle
                  cx="12"
                  cy="12"
                  r="10"
                  fill="none"
                  stroke="rgba(139, 92, 246, 0.15)"
                  stroke-width="2"
                />
                <circle
                  cx="12"
                  cy="12"
                  r="10"
                  fill="none"
                  stroke="var(--accent)"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-dasharray="62"
                  stroke-dashoffset="48"
                  transform="rotate(-90 12 12)"
                >
                  <animateTransform
                    attributeName="transform"
                    type="rotate"
                    from="0 12 12"
                    to="360 12 12"
                    dur="1.5s"
                    repeatCount="indefinite"
                  />
                </circle>
              </svg>
            </div>
            <div class="progress-bar">
              <div
                class="progress-fill"
                :style="{ width: progressPercent + '%' }"
              ></div>
            </div>
            <p class="progress-label">{{ progressLabel }}</p>
            <p class="progress-stages">
              ① 故事圣经 → ② 场景切分 → ③ 元素抽取 → ④ 对白精修 → ⑤ 决策建议
              → ⑥ YAML 组装
            </p>
          </div>

          <!-- 错误阶段 -->
          <div v-else class="error-stage">
            <div class="error-icon">
              <svg
                width="32"
                height="32"
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
            </div>
            <p class="error-msg">{{ store.lastError }}</p>
            <p class="error-hint">
              常见原因:LLM API key 未配置 / 网络问题 / 章节内容过短
            </p>
          </div>
        </main>

        <!-- 底栏 -->
        <footer class="d-foot">
          <template v-if="stage === 'config'">
            <button class="btn-secondary" @click="emit('close')">取消</button>
            <button class="btn-primary" @click="handleStart">
              <svg
                width="13"
                height="13"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.4"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <polygon points="5 3 19 12 5 21 5 3" />
              </svg>
              开始生成
            </button>
          </template>
          <template v-else-if="stage === 'composing'">
            <p class="composing-foot-hint">
              此操作贵且不可中止 · 请等待 LLM 流水线完成
            </p>
          </template>
          <template v-else>
            <button class="btn-secondary" @click="emit('close')">关闭</button>
            <button class="btn-primary" @click="handleRetry">重试</button>
          </template>
        </footer>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(20, 18, 14, 0.36);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 200ms;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
.fade-enter-active .dialog,
.fade-leave-active .dialog {
  transition: transform 220ms cubic-bezier(0.25, 0.46, 0.45, 0.94);
}
.fade-enter-from .dialog,
.fade-leave-to .dialog {
  transform: translateY(10px) scale(0.98);
}

.dialog {
  width: 460px;
  max-width: 90vw;
  background: var(--card-bg);
  border-radius: 14px;
  box-shadow: var(--shadow-lg);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.d-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 18px 20px;
  border-bottom: 1px solid var(--border);
}
.d-head-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: rgba(139, 92, 246, 0.1);
  color: var(--accent);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.d-head-text {
  flex: 1;
}
.d-head-text h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}
.d-head-text p {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}
.d-head-text .d-err {
  color: var(--danger);
}
.d-head-text .d-warn {
  color: var(--warning);
  font-variant-numeric: tabular-nums;
}
.d-close {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-muted);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 120ms;
  flex-shrink: 0;
}
.d-close:hover {
  background: var(--hover-bg);
  color: var(--text);
}

.d-body {
  padding: 18px 20px;
}

/* === 配置阶段 === */
.toggle-row,
.number-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 0;
  border-bottom: 1px dashed var(--border);
}
.number-row:last-of-type,
.toggle-row:last-of-type {
  border-bottom: none;
}
.toggle-text {
  flex: 1;
}
.t-title {
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
}
.differentiation-pill {
  font-size: 9.5px;
  padding: 1px 7px;
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.16), rgba(14, 165, 233, 0.16));
  color: var(--accent);
  border-radius: 8px;
  letter-spacing: 0.04em;
}
.t-hint {
  font-size: 11.5px;
  color: var(--text-muted);
  margin-top: 2px;
}

.toggle {
  width: 36px;
  height: 20px;
  appearance: none;
  background: var(--border);
  border-radius: 12px;
  position: relative;
  cursor: pointer;
  transition: background 200ms;
}
.toggle::before {
  content: "";
  position: absolute;
  width: 16px;
  height: 16px;
  background: white;
  border-radius: 50%;
  top: 2px;
  left: 2px;
  transition: transform 200ms;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.15);
}
.toggle:checked {
  background: var(--accent);
}
.toggle:checked::before {
  transform: translateX(16px);
}

.number-input {
  width: 80px;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 5px;
  font-family: inherit;
  font-size: 13px;
  text-align: right;
  background: var(--card-bg);
}
.number-input:focus {
  outline: none;
  border-color: var(--accent);
}

.estimate {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: var(--space-4);
  padding: var(--space-3) var(--space-3);
  background: var(--bg);
  border-radius: var(--radius-md);
  font-size: 12px;
  color: var(--text-secondary);
  letter-spacing: 0.02em;
}
.estimate strong {
  color: var(--accent-text);
  font-family: var(--font-mono);
  font-weight: 500;
  font-size: 12.5px;
}
.est-detail {
  color: var(--text-muted);
  font-size: 11px;
  margin-left: 4px;
  font-family: var(--font-mono);
}

/* 大小说警告 banner */
.large-novel-banner {
  display: flex;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--warning-soft);
  border: 1px solid var(--warning);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-4);
  color: var(--warning);
}
.large-novel-banner svg {
  flex-shrink: 0;
  margin-top: 2px;
}
.lnb-text {
  flex: 1;
  font-family: var(--font-serif);
  font-size: 13px;
  color: var(--text);
  letter-spacing: 0.02em;
}
.lnb-text strong {
  color: var(--text-strong);
  font-weight: 500;
}
.lnb-hint {
  margin-top: var(--space-1);
  font-family: var(--font-sans);
  font-size: 11.5px;
  color: var(--text-secondary);
  letter-spacing: 0.02em;
}
.lnb-hint strong {
  color: var(--accent-text);
}

/* === 进度阶段 === */
.composing-stage {
  text-align: center;
  padding: 8px 0 4px;
}
.spinner {
  display: inline-flex;
  margin-bottom: 16px;
}
.progress-bar {
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
  margin: 12px 0;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent), #a78bfa);
  border-radius: 2px;
  transition: width 800ms ease-out;
}
.progress-label {
  font-size: 13px;
  color: var(--text);
  margin: 12px 0 4px;
  font-weight: 500;
}
.progress-stages {
  font-size: 11px;
  color: var(--text-muted);
  margin: 0;
  line-height: 1.8;
}

/* === 错误阶段 === */
.error-stage {
  text-align: center;
  padding: 12px 0;
}
.error-icon {
  color: var(--danger);
  margin-bottom: 8px;
}
.error-msg {
  font-size: 13px;
  color: var(--danger);
  margin: 8px 0 4px;
  word-break: break-word;
}
.error-hint {
  font-size: 11.5px;
  color: var(--text-muted);
  margin: 0;
}

/* === 底栏 === */
.d-foot {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 20px;
  border-top: 1px solid var(--border);
  background: var(--bg);
}
.btn-secondary,
.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  border: 1px solid var(--border);
  background: var(--card-bg);
  color: var(--text);
  transition: all 120ms;
}
.btn-secondary:hover {
  background: var(--hover-bg);
}
.btn-primary {
  background: var(--accent);
  color: white;
  border-color: var(--accent);
}
.btn-primary:hover {
  background: var(--accent-hover);
  border-color: var(--accent-hover);
}
.composing-foot-hint {
  margin: 0;
  font-size: 11.5px;
  color: var(--text-muted);
  flex: 1;
  text-align: center;
}
</style>
