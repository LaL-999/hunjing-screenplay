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

const progressLabel = computed(() => {
  const t = elapsed.value;
  if (t < 5) return "正在准备 LLM 流水线...";
  if (t < 15) return "故事圣经 + 章节切分中...";
  if (t < 35) return "逐场抽元素 + 对白归属精修...";
  if (t < 60) return "改编决策建议生成中...";
  return "组装 YAML + 校验...";
});

const progressPercent = computed(() => {
  // 估算 — 90s 上限给视觉上"还在动"的感觉
  return Math.min(95, Math.round((elapsed.value / 90) * 100));
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
            <p v-else-if="stage === 'composing'">{{ elapsed }} 秒 · 总耗时约 1-2 分钟</p>
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
                  PR#9 内心独白 → V.O. / 动作外化 / 删除 3 备选
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
              预估耗时 30 - 90 秒(取决于章数 + LLM 响应延迟)
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
  margin-top: 14px;
  padding: 10px 12px;
  background: var(--bg);
  border-radius: 6px;
  font-size: 11.5px;
  color: var(--text-muted);
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
