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
        width="32"
        height="32"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
      >
        <path d="M21 12a9 9 0 11-6.219-8.56" />
      </svg>
      <div class="upload-text">解析中...</div>
      <div class="upload-hint">服务器正在分章节、抽段落</div>
    </div>

    <div v-else class="upload-state">
      <svg
        width="36"
        height="36"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="17 8 12 3 7 8" />
        <line x1="12" y1="3" x2="12" y2="15" />
      </svg>
      <div class="upload-text">
        <strong>点击选择</strong>或拖拽小说文件
      </div>
      <div class="upload-hint">支持 .txt / .epub / .docx,最大 {{ MAX_MB }}MB</div>
    </div>

    <div v-if="errorMsg" class="upload-error">{{ errorMsg }}</div>
  </section>
</template>

<style scoped>
.upload-card {
  border: 2px dashed var(--border);
  border-radius: 10px;
  padding: 28px 18px;
  text-align: center;
  cursor: pointer;
  background: var(--card-bg);
  transition: border-color 150ms, background 150ms, transform 150ms;
  margin-bottom: 16px;
}

.upload-card:hover {
  border-color: var(--accent);
  background: var(--hover-bg);
}

.upload-card.dragging {
  border-color: var(--accent);
  background: rgba(139, 92, 246, 0.08);
  transform: scale(1.01);
}

.upload-card.uploading {
  pointer-events: none;
  opacity: 0.85;
}

.upload-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: var(--text-muted);
}
.upload-state svg {
  color: var(--accent);
}

.upload-text {
  font-size: 13px;
  color: var(--text);
}
.upload-text strong {
  color: var(--accent);
  font-weight: 600;
}

.upload-hint {
  font-size: 11px;
  color: var(--text-muted);
}

.upload-error {
  margin-top: 10px;
  padding: 6px 10px;
  background: rgba(239, 68, 68, 0.08);
  border-radius: 6px;
  color: var(--danger);
  font-size: 11.5px;
}

.spinner {
  animation: spin 1s linear infinite;
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
