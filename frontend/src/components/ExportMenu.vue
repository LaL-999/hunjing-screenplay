<script setup lang="ts">
/**
 * 导出菜单 — PR#17。
 *
 * 顶栏"导出"按钮 + 下拉,3 种行业格式:
 *   - Fountain (.fountain) — 行业标准,Final Draft 可导入
 *   - TXT (.txt)         — 中文友好纯文本
 *   - YAML (.yaml)       — 原始结构化数据
 */
import { onBeforeUnmount, onMounted, ref } from "vue";

import { downloadScreenplay, type ExportFormat } from "../api/client";
import { useScreenplayStore } from "../stores/screenplay";

const store = useScreenplayStore();

const isOpen = ref<boolean>(false);
const isDownloading = ref<ExportFormat | null>(null);
const errorMsg = ref<string>("");

const formats: Array<{
  key: ExportFormat;
  label: string;
  tagline: string;
  hint: string;
}> = [
  {
    key: "fountain",
    label: ".fountain",
    tagline: "行业标准",
    hint: "Final Draft / WriterDuet 等专业软件直接打开",
  },
  {
    key: "txt",
    label: ".txt",
    tagline: "纯文本",
    hint: "中文友好排版,发微信 / 打印 / 对稿",
  },
  {
    key: "yaml",
    label: ".yaml",
    tagline: "结构化数据",
    hint: "原始 YAML,给工具链 / 二次开发",
  },
];

function toggle() {
  if (!store.screenplayId) return;
  isOpen.value = !isOpen.value;
  errorMsg.value = "";
}

async function handleDownload(format: ExportFormat) {
  if (!store.screenplayId || isDownloading.value) return;
  errorMsg.value = "";
  isDownloading.value = format;
  try {
    await downloadScreenplay(store.screenplayId, format);
    // 成功后短暂保留状态再关菜单
    setTimeout(() => {
      isOpen.value = false;
    }, 300);
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e);
  } finally {
    isDownloading.value = null;
  }
}

// 点外面关菜单
function onClickOutside(e: MouseEvent) {
  const target = e.target as HTMLElement;
  if (!target.closest(".export-root")) {
    isOpen.value = false;
  }
}

onMounted(() => {
  document.addEventListener("click", onClickOutside);
});
onBeforeUnmount(() => {
  document.removeEventListener("click", onClickOutside);
});
</script>

<template>
  <div class="export-root">
    <button
      class="export-trigger"
      :disabled="!store.screenplayId"
      :title="store.screenplayId ? '导出剧本' : '需要先生成剧本'"
      @click="toggle"
    >
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
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="7 10 12 15 17 10" />
        <line x1="12" y1="15" x2="12" y2="3" />
      </svg>
      <span>导出</span>
    </button>

    <transition name="export-fade">
      <div v-if="isOpen" class="export-menu">
        <div class="menu-label">选择格式</div>
        <button
          v-for="f in formats"
          :key="f.key"
          class="format-item"
          :class="{ downloading: isDownloading === f.key }"
          :disabled="isDownloading !== null"
          @click="handleDownload(f.key)"
        >
          <div class="fi-left">
            <span class="fi-ext literary">{{ f.label }}</span>
            <span class="fi-tagline">{{ f.tagline }}</span>
          </div>
          <div class="fi-hint">{{ f.hint }}</div>
          <div v-if="isDownloading === f.key" class="fi-spinner">
            <svg
              class="spinner"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
            >
              <path d="M21 12a9 9 0 11-6.219-8.56" />
            </svg>
          </div>
        </button>

        <div v-if="errorMsg" class="export-error">⚠ {{ errorMsg }}</div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.export-root {
  position: relative;
  display: inline-block;
}

.export-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text);
  font-family: var(--font-sans);
  font-size: 12px;
  cursor: pointer;
  transition: all var(--transition-fast);
  letter-spacing: 0.02em;
}
.export-trigger:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent-text);
  background: var(--accent-soft);
}
.export-trigger:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.export-menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  min-width: 320px;
  background: var(--card-bg-strong);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  z-index: 50;
  padding: var(--space-3);
}

.menu-label {
  font-size: 10.5px;
  color: var(--text-muted);
  letter-spacing: 0.24em;
  padding: var(--space-2) var(--space-3) var(--space-3);
  text-transform: uppercase;
  border-bottom: 1px solid var(--border-soft);
  margin-bottom: var(--space-2);
}

.format-item {
  display: block;
  width: 100%;
  text-align: left;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  padding: var(--space-3);
  cursor: pointer;
  transition: all var(--transition-fast);
  position: relative;
  margin-bottom: var(--space-1);
}
.format-item:hover:not(:disabled) {
  background: var(--hover-bg);
  border-color: var(--border);
}
.format-item:disabled {
  opacity: 0.5;
  cursor: wait;
}
.format-item.downloading {
  background: var(--accent-soft);
}

.fi-left {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  margin-bottom: 2px;
}
.fi-ext {
  font-family: var(--font-mono);
  font-size: 14px;
  font-weight: 500;
  color: var(--accent-text);
  letter-spacing: 0.02em;
}
.fi-tagline {
  font-family: var(--font-serif);
  font-size: 12px;
  color: var(--text-strong);
  letter-spacing: 0.02em;
}
.fi-hint {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.5;
  letter-spacing: 0.02em;
}

.fi-spinner {
  position: absolute;
  right: var(--space-3);
  top: 50%;
  transform: translateY(-50%);
  color: var(--accent);
}
.spinner {
  animation: spin 1.2s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.export-error {
  margin-top: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--danger-soft);
  color: var(--danger);
  border-radius: var(--radius-sm);
  font-size: 11px;
  border: 1px solid var(--danger);
}

/* transition */
.export-fade-enter-active,
.export-fade-leave-active {
  transition: opacity 150ms, transform 150ms;
}
.export-fade-enter-from,
.export-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
