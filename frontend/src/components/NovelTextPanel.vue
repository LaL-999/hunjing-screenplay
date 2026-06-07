<script setup lang="ts">
/**
 * 左栏:原文 — PR#11 commit 2。
 *
 * 按 chapter 顺序渲染段落,根据选中 scene 高亮 paragraph_range 区间,
 * 并自动滚动到首条高亮段落。
 */
import { computed, nextTick, ref, watch } from "vue";

import { useScreenplayStore } from "../stores/screenplay";

const store = useScreenplayStore();
const scrollRoot = ref<HTMLElement | null>(null);

interface ParagraphView {
  chapterNumber: number;
  chapterTitle: string | null;
  index: number;
  text: string;
  highlighted: boolean;
  isFirstHighlighted: boolean;
}

interface ChapterGroup {
  number: number;
  title: string | null;
  paragraphs: ParagraphView[];
}

const groups = computed<ChapterGroup[]>(() => {
  const out: ChapterGroup[] = [];
  const scene = store.selectedScene;
  const highlightChapter = scene?.source?.chapter ?? null;
  const highlightRange = scene?.source?.paragraph_range ?? null;

  for (const ch of store.novelChapters) {
    const paragraphs = store.paragraphsByChapter.get(ch.number) ?? [];
    let firstHighlightedSeen = false;
    const views: ParagraphView[] = paragraphs.map((p) => {
      const isInRange =
        highlightChapter === ch.number &&
        highlightRange !== null &&
        p.index_in_chapter >= highlightRange[0] &&
        p.index_in_chapter <= highlightRange[1];
      const isFirst = isInRange && !firstHighlightedSeen;
      if (isFirst) firstHighlightedSeen = true;
      return {
        chapterNumber: ch.number,
        chapterTitle: ch.title,
        index: p.index_in_chapter,
        text: p.text,
        highlighted: isInRange,
        isFirstHighlighted: isFirst,
      };
    });
    out.push({ number: ch.number, title: ch.title, paragraphs: views });
  }
  return out;
});

// 选中 scene 变化 → 滚到首条高亮段落
watch(
  () => store.selectedSceneId,
  async () => {
    await nextTick();
    if (!scrollRoot.value) return;
    const target = scrollRoot.value.querySelector(
      ".paragraph.first-highlight",
    ) as HTMLElement | null;
    if (target) {
      target.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }
  },
);
</script>

<template>
  <div ref="scrollRoot" class="novel-text">
    <div v-if="groups.length === 0" class="empty">
      <div class="empty-text">
        作品尚未摄入段落数据<br />
        <span class="empty-hint">请检查后端 /chapters 接口</span>
      </div>
    </div>
    <template v-else>
      <div v-for="ch in groups" :key="ch.number" class="chapter-block">
        <h4 class="chapter-heading">
          <span class="ch-no">第 {{ ch.number }} 章</span>
          <span v-if="ch.title" class="ch-title">· {{ ch.title }}</span>
          <span class="ch-meta">{{ ch.paragraphs.length }} 段</span>
        </h4>
        <ol class="paragraphs">
          <li
            v-for="p in ch.paragraphs"
            :key="`${p.chapterNumber}-${p.index}`"
            :class="[
              'paragraph',
              { highlighted: p.highlighted, 'first-highlight': p.isFirstHighlighted },
            ]"
          >
            <span class="p-index">{{ p.index }}</span>
            <span class="p-text">{{ p.text }}</span>
          </li>
        </ol>
      </div>
    </template>
  </div>
</template>

<style scoped>
.novel-text {
  font-family: var(--font-serif);
  font-size: 16px;
  line-height: 1.9;
  color: var(--text);
  letter-spacing: 0.01em;
}

.chapter-block + .chapter-block {
  margin-top: var(--space-7);
}

.chapter-heading {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  font-family: var(--font-serif);
  font-size: 15px;
  font-weight: 500;
  color: var(--text-strong);
  margin: 0 0 var(--space-4);
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--border-soft);
  letter-spacing: 0.02em;
}
.ch-no {
  color: var(--text-muted);
  font-size: 12.5px;
  font-family: var(--font-mono);
  letter-spacing: 0.12em;
}
.ch-title {
  color: var(--text-strong);
  font-weight: 500;
}
.ch-meta {
  margin-left: auto;
  font-size: 10.5px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  letter-spacing: 0.04em;
}

.paragraphs {
  list-style: none;
  margin: 0;
  padding: 0;
}

.paragraph {
  display: flex;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-3);
  border-radius: var(--radius-md);
  margin: var(--space-2) 0;
  transition: all var(--transition-base);
}
.paragraph.highlighted {
  background: var(--accent-soft);
  border-left: 2px solid var(--accent);
  padding-left: calc(var(--space-3) + 2px);
  margin-left: -2px;
}
.p-index {
  flex-shrink: 0;
  width: 24px;
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  text-align: right;
  padding-top: 8px;
  user-select: none;
  opacity: 0.6;
}
.paragraph.highlighted .p-index {
  color: var(--accent);
  opacity: 1;
}
.p-text {
  flex: 1;
  word-break: break-word;
  text-indent: 2em;        /* 文学排版:首行缩进 */
}

.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  text-align: center;
  color: var(--text-muted);
}
.empty-text {
  font-size: 13px;
  line-height: 1.6;
}
.empty-hint {
  font-size: 11.5px;
  opacity: 0.7;
}
</style>
