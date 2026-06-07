<script setup lang="ts">
/**
 * 小说上传卡片 — 支持点击选择 + 拖拽。
 *
 * 接 POST /novels(multipart/form-data),后端解析章节落库后,
 * 触发父组件 reload novels 列表。
 */
import { ref } from "vue";

import { uploadNovel } from "../api/client";

const emit = defineEmits<{
  (e: "uploaded", novelId: string): void;
}>();

const isDragging = ref<boolean>(false);
const isUploading = ref<boolean>(false);
const errorMsg = ref<string>("");
const fileInput = ref<HTMLInputElement | null>(null);

const ACCEPTED = [".txt", ".epub", ".docx"];
const MAX_MB = 20;

function pickFile() {
  fileInput.value?.click();
}

async function handleFile(file: File) {
  errorMsg.value = "";

  // 类型校验
  const lower = file.name.toLowerCase();
  if (!ACCEPTED.some((ext) => lower.endsWith(ext))) {
    errorMsg.value = `不支持的格式 — 仅支持 ${ACCEPTED.join(" / ")}`;
    return;
  }
  // 大小校验
  if (file.size > MAX_MB * 1024 * 1024) {
    errorMsg.value = `文件超过 ${MAX_MB}MB 限制`;
    return;
  }

  isUploading.value = true;
  try {
    const r = await uploadNovel(file);
    emit("uploaded", r.novel_id);
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e);
  } finally {
    isUploading.value = false;
    if (fileInput.value) fileInput.value.value = "";
  }
}

function onChange(e: Event) {
  const target = e.target as HTMLInputElement;
  const file = target.files?.[0];
  if (file) handleFile(file);
}

function onDrop(e: DragEvent) {
  e.preventDefault();
  isDragging.value = false;
  const file = e.dataTransfer?.files?.[0];
  if (file) handleFile(file);
}

function onDragOver(e: DragEvent) {
  e.preventDefault();
  isDragging.value = true;
}

function onDragLeave() {
  isDragging.value = false;
}
</script>

<template>
  <section
    class="upload-card"
    :class="{ dragging: isDragging, uploading: isUploading }"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
    @click="pickFile"
  >
    <input
      ref="fileInput"
      type="file"
      :accept="ACCEPTED.join(',')"
      hidden
      @change="onChange"
    />

    <div v-if="isUploading" class="upload-state">
      <svg
        class="spinner"
        width="28"
        height="28"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
      >
        <path d="M21 12a9 9 0 11-6.219-8.56" />
      </svg>
      <div class="upload-text literary">正在拆解章节…</div>
    </div>

    <div v-else class="upload-state">
      <svg
        width="32"
        height="32"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="17 8 12 3 7 8" />
        <line x1="12" y1="3" x2="12" y2="15" />
      </svg>
      <div class="upload-text literary">
        拖入小说,或<button class="text-btn">点此选择</button>
      </div>
      <div class="upload-hint">.txt · .epub · .docx · ≤ {{ MAX_MB }}MB</div>
    </div>

    <div v-if="errorMsg" class="upload-error">{{ errorMsg }}</div>
  </section>
</template>

<style scoped>
.upload-card {
  border: 1px dashed var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-7) var(--space-5);
  text-align: center;
  cursor: pointer;
  background: var(--card-bg);
  transition: all var(--transition-base);
}

.upload-card:hover {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.upload-card.dragging {
  border-color: var(--accent);
  border-style: solid;
  background: var(--accent-soft);
}

.upload-card.uploading {
  pointer-events: none;
  opacity: 0.7;
}

.upload-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  color: var(--text-muted);
}
.upload-state svg {
  color: var(--accent);
  opacity: 0.65;
}

.upload-text {
  font-size: 16px;
  color: var(--text);
  letter-spacing: 0.02em;
}
.text-btn {
  background: none;
  border: none;
  padding: 0;
  font: inherit;
  color: var(--accent);
  cursor: pointer;
  border-bottom: 1px solid currentColor;
  margin-left: 2px;
}

.upload-hint {
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 0.12em;
  font-family: var(--font-mono);
  text-transform: lowercase;
}

.upload-error {
  margin-top: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: var(--danger-soft);
  border-radius: var(--radius-md);
  color: var(--danger);
  font-size: 11.5px;
}

.spinner {
  animation: spin 1.2s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
