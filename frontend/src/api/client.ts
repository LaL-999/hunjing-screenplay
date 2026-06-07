/**
 * 后端 API client — 极简 fetch 封装。
 *
 * 约定:vite.config.ts 已配 /api → http://localhost:8003 代理。
 */

import type {
  ComposeResponse,
  NovelInfo,
  OptimizeRequest,
  OptimizeResponse,
  ScreenplayResponse,
  ScreenplayVersion,
  StructureReport,
} from "../types/screenplay";

const API_BASE = "/api";

class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    public detail: string,
  ) {
    super(`[${status} ${code}] ${detail}`);
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, init);
  if (!r.ok) {
    let code = `HTTP_${r.status}`;
    let detail = r.statusText;
    try {
      const body = await r.json();
      if (body && typeof body === "object" && "detail" in body) {
        const d = body.detail as { code?: string; message?: string };
        code = d.code ?? code;
        detail = d.message ?? detail;
      }
    } catch {
      /* body 不是 JSON,沿用 statusText */
    }
    throw new ApiError(r.status, code, detail);
  }
  return r.json() as Promise<T>;
}

// ============================================================
// Novel
// ============================================================

export async function listNovels(): Promise<NovelInfo[]> {
  // 后端返 envelope {items: [...]}
  const r = await request<{ items: NovelInfo[] }>("/novels");
  return r.items ?? [];
}

/**
 * 上传小说文件(.txt / .epub / .docx)
 * 后端走 multipart/form-data,自动解析章节落库。
 */
export async function uploadNovel(file: File): Promise<{
  novel_id: string;
  title: string;
  source_format: string;
  total_chapters: number;
  total_chars: number;
  chapters: Array<{
    id: string;
    number: number;
    title: string | null;
    paragraph_count: number;
    char_count: number;
  }>;
}> {
  const form = new FormData();
  form.append("file", file);
  const r = await fetch(`${API_BASE}/novels`, {
    method: "POST",
    body: form,
  });
  if (!r.ok) {
    let code = `HTTP_${r.status}`;
    let detail = r.statusText;
    try {
      const body = await r.json();
      if (body && typeof body === "object" && "detail" in body) {
        const d = body.detail as { code?: string; message?: string };
        code = d.code ?? code;
        detail = d.message ?? detail;
      }
    } catch {
      /* ignore */
    }
    throw new ApiError(r.status, code, detail);
  }
  return r.json();
}

/**
 * 删除小说(级联清章节 / 段落 / 故事圣经 / screenplays)
 */
export async function deleteNovel(novelId: string): Promise<void> {
  const r = await fetch(`${API_BASE}/novels/${encodeURIComponent(novelId)}`, {
    method: "DELETE",
  });
  if (!r.ok && r.status !== 404) {
    throw new ApiError(r.status, `HTTP_${r.status}`, r.statusText);
  }
}

export async function getNovel(novelId: string): Promise<
  NovelInfo & {
    chapters: Array<{
      id: string;
      number: number;
      title: string | null;
      paragraph_count: number;
      char_count: number;
    }>;
  }
> {
  return request(`/novels/${encodeURIComponent(novelId)}`);
}

export async function getChapterParagraphs(
  chapterId: string,
): Promise<Array<{ index_in_chapter: number; text: string }>> {
  // 后端 GET /chapters/{id} 返 {chapter_id, paragraphs: [...]}
  const r = await request<{
    paragraphs: Array<{ index_in_chapter: number; text: string }>;
  }>(`/chapters/${encodeURIComponent(chapterId)}`);
  return r.paragraphs ?? [];
}

// ============================================================
// Screenplay (PR#10)
// ============================================================

export interface ComposeRequest {
  refine_dialogue?: boolean;
  propose_decisions?: boolean;
  max_chapters?: number | null;
  retry_per_call?: number;
}

export async function composeScreenplay(
  novelId: string,
  req: ComposeRequest = {},
): Promise<ComposeResponse> {
  return request(`/novels/${encodeURIComponent(novelId)}/compose-screenplay`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export async function getLatestScreenplay(
  novelId: string,
): Promise<ScreenplayResponse> {
  return request(`/novels/${encodeURIComponent(novelId)}/screenplay`);
}

export async function getScreenplayById(
  screenplayId: string,
): Promise<ScreenplayResponse> {
  return request(`/screenplays/${encodeURIComponent(screenplayId)}`);
}

export async function getStructureReport(
  screenplayId: string,
): Promise<StructureReport> {
  return request(`/screenplays/${encodeURIComponent(screenplayId)}/structure`);
}

// ============================================================
// Export (PR#17) — 触发文件下载
// ============================================================

export type ExportFormat = "fountain" | "txt" | "yaml";

/**
 * 下载剧本为指定格式。
 * 走原生浏览器下载流(走 a 标签触发,带 attachment header)。
 */
export async function downloadScreenplay(
  screenplayId: string,
  format: ExportFormat,
): Promise<void> {
  const url = `${API_BASE}/screenplays/${encodeURIComponent(screenplayId)}/export.${format}`;
  const r = await fetch(url);
  if (!r.ok) {
    let detail = `导出失败 (HTTP ${r.status})`;
    try {
      const body = await r.json();
      if (body?.detail?.message) detail = body.detail.message;
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  // 从 Content-Disposition 拿文件名(RFC 5987 编码,filename*=UTF-8''xxx)
  const disposition = r.headers.get("Content-Disposition") || "";
  let filename = `screenplay.${format}`;
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match) {
    try {
      filename = decodeURIComponent(utf8Match[1]);
    } catch { /* fallback */ }
  } else {
    const plainMatch = disposition.match(/filename="?([^";]+)"?/i);
    if (plainMatch) filename = plainMatch[1];
  }
  const blob = await r.blob();
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // 释放
  setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
}

// ============================================================
// 优化 + 版本(PR#16)
// ============================================================

/**
 * 调用人机协作优化引擎(A 单场 / B 整本共用)。
 * 后端会跑 LLM → 存为新版本(parent 指向当前)→ 返新 id + change_log。
 */
export async function optimizeScreenplay(
  screenplayId: string,
  req: OptimizeRequest,
): Promise<OptimizeResponse> {
  return request(`/screenplays/${encodeURIComponent(screenplayId)}/optimize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

/**
 * 列出该 novel 的所有剧本版本(初始版 + 所有优化分支)。
 */
export async function listScreenplayVersions(
  novelId: string,
): Promise<ScreenplayVersion[]> {
  const r = await request<{ items: ScreenplayVersion[] }>(
    `/novels/${encodeURIComponent(novelId)}/versions`,
  );
  return r.items ?? [];
}

// ============================================================
// 健康检查
// ============================================================

export async function getHealth(): Promise<{
  status: string;
  service: string;
  version: string;
  llm_model: string;
  llm_configured: boolean;
}> {
  return request("/health");
}

export { ApiError };
