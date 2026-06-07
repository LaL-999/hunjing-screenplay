<script setup lang="ts">
/**
 * 版本切换 — v2 重设计:dropdown 形式,不再横排 chip 挤顶栏。
 *
 * 视觉:
 *   - 默认显示当前版本简短名(e.g. "稿 5 · 整本重排")
 *   - 点击展开下拉时间线,按时间倒序列出全部
 *   - 选择切换 → 自动收起
 */
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { useScreenplayStore } from "../stores/screenplay";
import type { ScreenplayVersion } from "../types/screenplay";

const store = useScreenplayStore();

const versions = computed<ScreenplayVersion[]>(() => store.versions);
const currentId = computed(() => store.screenplayId);

const isOpen = ref<boolean>(false);

const orderedVersions = computed(() => {
  // ASC → DESC(最新在前)
  return [...versions.value].reverse();
});

const currentVersion = computed(() =>
  versions.value.find((v) => v.id === currentId.value),
);

const currentIndex = computed(() => {
  if (!currentVersion.value) return -1;
  return versions.value.findIndex((v) => v.id === currentId.value);
});

function shortOriginLabel(origin: string): string {
  if (origin === "initial") return "初稿";
  if (origin === "full_screenplay") return "整本重排";
  if (origin.startsWith("single_scene_")) {
    const sceneId = origin.replace("single_scene_", "");
    const num = sceneId.match(/scene_(\d+)/)?.[1];
    return num ? `单场精修 · 第 ${parseInt(num)} 场` : "单场精修";
  }
  return origin;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

function getCardinal(idx: number): string {
  return `稿 ${idx + 1}`;
}

async function handleSwitch(v: ScreenplayVersion) {
  isOpen.value = false;
  if (v.id === currentId.value) return;
  await store.switchToVersion(v.id);
}

function toggle() {
  isOpen.value = !isOpen.value;
}

// 点击外部关闭
function onClickOutside(e: MouseEvent) {
  const target = e.target as HTMLElement;
  if (!target.closest(".vs-root")) {
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
  <div v-if="versions.length > 1" class="vs-root">
    <button class="vs-trigger" @click="toggle">
      <span class="vs-label">本稿</span>
      <span class="vs-current">
        <span class="vs-cardinal">{{ getCardinal(currentIndex) }}</span>
        <span class="vs-divider">/</span>
        <span class="vs-origin">
          {{ currentVersion ? shortOriginLabel(currentVersion.origin) : "—" }}
        </span>
        <span
          v-if="currentVersion && currentVersion.change_count > 0"
          class="vs-changes"
        >
          {{ currentVersion.change_count }} 处改动
        </span>
      </span>
      <svg
        class="vs-chevron"
        :class="{ open: isOpen }"
        width="12"
        height="12"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </button>

    <transition name="vs-fade">
      <div v-if="isOpen" class="vs-menu">
        <div class="vs-menu-label">版本时间线</div>
        <ul class="vs-list">
          <li
            v-for="(v, idx) in orderedVersions"
            :key="v.id"
            class="vs-item"
            :class="{ active: v.id === currentId }"
            @click="handleSwitch(v)"
          >
            <div class="vs-item-num">
              <span class="vs-item-cardinal">
                {{ getCardinal(versions.length - 1 - idx) }}
              </span>
              <span class="vs-item-time">{{ formatTime(v.created_at) }}</span>
            </div>
            <div class="vs-item-main">
              <div class="vs-item-origin">{{ shortOriginLabel(v.origin) }}</div>
              <div
                v-if="v.change_count > 0"
                class="vs-item-meta"
              >
                {{ v.change_count }} 处改动 · {{ v.scene_count }} 场
              </div>
              <div v-else class="vs-item-meta">{{ v.scene_count }} 场</div>
              <!-- 当前选中版本展开 reasoning,其余折叠节省空间 -->
              <div
                v-if="v.reasoning_snippet && v.id === currentId"
                class="vs-item-snippet literary"
              >
                {{ v.reasoning_snippet }}…
              </div>
            </div>
          </li>
        </ul>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.vs-root {
  position: relative;
  display: inline-block;
}

/* === Trigger 按钮 === */
.vs-trigger {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
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
.vs-trigger:hover {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.vs-label {
  font-size: 10.5px;
  color: var(--text-muted);
  letter-spacing: 0.2em;
}
.vs-current {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.vs-cardinal {
  font-family: var(--font-serif);
  font-weight: 500;
  color: var(--text-strong);
  font-size: 13px;
}
.vs-divider {
  color: var(--border);
}
.vs-origin {
  color: var(--text-secondary);
  font-size: 11.5px;
}
.vs-changes {
  font-size: 10.5px;
  color: var(--accent);
  padding: 1px 6px;
  background: var(--accent-soft);
  border-radius: 8px;
  font-family: var(--font-mono);
}
.vs-chevron {
  color: var(--text-muted);
  transition: transform var(--transition-fast);
}
.vs-chevron.open {
  transform: rotate(180deg);
}

/* === Dropdown 菜单 === */
.vs-menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  min-width: 320px;
  max-width: 420px;
  max-height: 480px;
  overflow-y: auto;
  background: var(--card-bg-strong);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  z-index: 50;
  padding: var(--space-3);
}

.vs-menu-label {
  font-size: 10.5px;
  color: var(--text-muted);
  letter-spacing: 0.24em;
  padding: var(--space-2) var(--space-3) var(--space-3);
  text-transform: uppercase;
  border-bottom: 1px solid var(--border-soft);
  margin-bottom: var(--space-2);
}

.vs-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.vs-item {
  display: flex;
  gap: var(--space-3);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.vs-item:hover {
  background: var(--hover-bg);
}
.vs-item.active {
  background: var(--accent-soft);
}

.vs-item-num {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  min-width: 60px;
  flex-shrink: 0;
  padding-top: 2px;
}
.vs-item-cardinal {
  font-family: var(--font-serif);
  font-size: 14px;
  font-weight: 500;
  color: var(--text-strong);
  letter-spacing: 0.02em;
}
.vs-item-time {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
  margin-top: 2px;
  letter-spacing: 0.04em;
}

.vs-item-main {
  flex: 1;
  min-width: 0;
}
.vs-item-origin {
  font-size: 12.5px;
  color: var(--text);
  margin-bottom: 2px;
}
.vs-item.active .vs-item-origin {
  color: var(--accent-text);
  font-weight: 500;
}
.vs-item-meta {
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 0.02em;
}
.vs-item-snippet {
  font-size: 11.5px;
  color: var(--text-secondary);
  margin-top: var(--space-2);
  line-height: 1.6;
  font-style: italic;
  border-left: 2px solid var(--border);
  padding-left: var(--space-3);
}

/* === transition === */
.vs-fade-enter-active,
.vs-fade-leave-active {
  transition: opacity 150ms, transform 150ms;
}
.vs-fade-enter-from,
.vs-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
