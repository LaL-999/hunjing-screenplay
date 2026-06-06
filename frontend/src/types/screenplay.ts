/**
 * 剧本相关 TypeScript 类型 — 对齐后端 schemas/screenplay.json
 *
 * 来源:
 *   - PR#10 ComposeResponse / ScreenplayResponse(routers/compose.py)
 *   - schemas/screenplay.json(YAML 内部结构)
 */

// ============================================================
// 后端 API 响应
// ============================================================

export interface NovelInfo {
  id: string;
  title: string;
  source_format: string;
  source_filename: string;
  total_chars: number;
  total_chapters: number;
  uploaded_at: string;
}

export interface ScreenplayResponse {
  screenplay_id: string;
  novel_id: string;
  yaml: string; // 完整 YAML 文本
  stats: Record<string, unknown>;
  warnings: ComposeWarning[];
  failed_chapters: number[];
  schema_version: string;
  model_name: string | null;
  created_at: string;
}

export interface ComposeResponse {
  screenplay_id: string;
  novel_id: string;
  yaml: string;
  stats: Record<string, unknown>;
  warnings: ComposeWarning[];
  failed_chapters: number[];
  validation_errors: Array<{ layer: string; path: string; message: string }>;
}

export interface ComposeWarning {
  layer: string; // location | character | element | scene | decision | chapter
  path: string;
  message: string;
}

// ============================================================
// YAML 解析后的剧本结构(与 schemas/screenplay.json 对齐)
// ============================================================

export interface Screenplay {
  meta: ScreenplayMeta;
  characters: Character[];
  locations: Location[];
  scenes: Scene[];
  adaptation_decisions?: AdaptationDecision[];
}

export interface ScreenplayMeta {
  schema_version: string;
  title: string;
  source?: {
    novel_title?: string;
    adapted_from_chapters?: number[];
  };
  logline?: string;
  generated_by: {
    platform: string;
    schema_version?: string;
    model?: string;
    generated_at?: string;
  };
  stats?: {
    total_scenes?: number;
    total_pages_estimate?: number;
    high_fidelity_scenes?: number;
    medium_fidelity_scenes?: number;
    low_fidelity_scenes?: number;
  };
}

export interface Character {
  id: string; // char_NNN
  name: string;
  aka?: string[];
  description?: string;
  first_appearance?: string; // scene_NNN
  arc_summary?: string;
}

export interface Location {
  id: string; // loc_NNN
  name: string;
  int_ext: "INT" | "EXT" | "INT/EXT";
  description?: string;
  first_appearance?: string;
}

export interface Scene {
  id: string; // scene_NNN
  number: number;
  heading: {
    int_ext: "INT" | "EXT" | "INT/EXT";
    location_id: string;
    time_of_day: string;
  };
  summary?: string;
  characters_present?: string[]; // char_NNN[]
  source?: {
    chapter?: number;
    paragraph_range?: [number, number];
  };
  fidelity?: {
    level: "high" | "medium" | "low";
    reason?: string;
    issues?: string[];
  };
  transition_to_next?: string;
  elements: ScreenplayElement[];
}

export type ScreenplayElement =
  | ActionElement
  | DialogueElement
  | ParentheticalElement
  | VoiceoverElement
  | TransitionElement
  | FlashbackElement;

export interface ActionElement {
  type: "action";
  id: string; // el_NNN_MMM
  text: string;
}

export interface DialogueElement {
  type: "dialogue";
  id: string;
  character_id: string;
  parenthetical?: string;
  text: string;
}

export interface ParentheticalElement {
  type: "parenthetical";
  id: string;
  text: string;
}

export interface VoiceoverElement {
  type: "voiceover";
  id: string;
  character_id: string;
  text: string;
  adaptation_note?: string;
}

export interface TransitionElement {
  type: "transition";
  id: string;
  text: string;
}

export interface FlashbackElement {
  type: "flashback_start" | "flashback_end";
  id: string;
  marker: string;
}

// ============================================================
// 改编决策(差异化创新核心)
// ============================================================

export interface AdaptationDecision {
  id: string; // dec_NNN
  scene_id: string;
  element_id: string;
  original_text: string;
  options: AdaptationOption[];
  chosen?: "voiceover" | "action_externalize" | "delete";
  chosen_at?: string;
}

export interface AdaptationOption {
  type: "voiceover" | "action_externalize" | "delete";
  text?: string;
  pros?: string;
  cons?: string;
  rationale?: string;
}

// ============================================================
// 原文段落(从后端 chapter / paragraph 拼出的渲染数据)
// ============================================================

export interface NovelParagraph {
  chapter_number: number;
  chapter_title: string | null;
  index_in_chapter: number;
  text: string;
}
