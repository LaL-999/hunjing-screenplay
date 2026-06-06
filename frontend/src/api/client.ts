/**
 * 后端 API client — 极简 fetch 封装。
 *
 * 约定:vite.config.ts 已配 /api → http://localhost:8003 代理。
 */

import type {
  ComposeResponse,
  NovelInfo,
  ScreenplayResponse,
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
