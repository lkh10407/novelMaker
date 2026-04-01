/** TypeScript interfaces mirroring Python models.py */

export interface Character {
  id: number;
  name: string;
  traits: string;
  status: "alive" | "dead" | "missing";
  location: string;
  inventory: string[];
  relationships: Record<string, string>;
}

export interface WorldSetting {
  tone: string;
  rules: string[];
  locations: string[];
  time_period: string;
}

export interface ChapterOutline {
  chapter: number;
  goal: string;
  key_events: string[];
  pov_character: string;
  involved_characters: string[];
}

export interface Foreshadowing {
  id: number;
  planted_chapter: number;
  description: string;
  resolved: boolean;
  resolved_chapter: number | null;
}

export interface ChapterResult {
  chapter: number;
  content: string;
  summary: string;
  ending_hook: string;
  state_changes: string[];
  char_count: number;
  version: number;
}

export interface CheckerError {
  code: string;
  description: string;
  severity: "critical" | "warning";
}

export interface CheckResult {
  passed: boolean;
  errors: CheckerError[];
}

export interface Project {
  project_id: string;
  title: string;
  logline: string;
  total_chapters: number;
  created_at: number;
  updated_at: number;
}

export interface GenerationStatus {
  status: "idle" | "running" | "completed" | "error";
  current_chapter?: number;
  phase?: string;
}

export interface TokenUsage {
  total_input_tokens: number;
  total_output_tokens: number;
  estimated_cost_usd: number;
  records: TokenRecord[];
}

export interface TokenRecord {
  agent: string;
  chapter: number;
  input_tokens: number;
  output_tokens: number;
}

// SSE event types
export interface SSEPhaseEvent {
  phase: string;
  chapter?: number;
}

export interface SSEChapterCompleteEvent {
  chapter: number;
  char_count: number;
  summary: string;
}

export interface SSEAwaitingApprovalEvent {
  chapter: number;
  content: string;
}

export interface SSEDoneEvent {
  total_tokens: number;
  cost_usd: string;
}

export interface SSEErrorEvent {
  message: string;
}

// Animation storyboard & dialogue types
export interface StoryboardScene {
  chapter: number;
  scene_number: number;
  visual_description: string;
  image_prompt: string;
  camera_angle: string;
  characters_present: string[];
  key_actions: string[];
  mood: string;
  duration_seconds: number;
}

export interface DialogueLine {
  chapter: number;
  scene_number: number;
  speaker: string;
  text: string;
  emotion: string;
  direction: string;
}

export interface AnimationStatus {
  status: "idle" | "running" | "completed" | "ready";
  scene_count?: number;
  line_count?: number;
}

export interface SSEAnimPhaseEvent {
  phase: string;
  chapter?: number;
  progress?: number;
  message?: string;
}

export interface SSEAnimDoneEvent {
  total_scenes: number;
  total_lines: number;
  total_tokens: number;
  cost_usd: number;
}

// Media generation types
export interface MediaGenerateRequest {
  voice?: string;
  background_color?: string;
  background_image_url?: string | null;
  subtitle_font_size?: number;
  subtitle_color?: string;
  include_title_cards?: boolean;
  chapters?: number[] | null;
}

export interface MediaStatus {
  status: "idle" | "running" | "completed" | "ready";
  file_size_mb?: number;
}

export interface MediaVoice {
  id: string;
  name: string;
}

export interface SSEMediaPhaseEvent {
  phase: string;
  chapter?: number;
  progress?: number;
  message?: string;
}

export interface SSEMediaChapterCompleteEvent {
  chapter: number;
  duration: number;
  progress: number;
}

export interface SSEMediaDoneEvent {
  duration: number;
  file_size_mb: number;
  chapters_processed: number;
}

export interface SSEMediaErrorEvent {
  message: string;
}

export interface NovelMakerSettings {
  serverUrl: string;
  projectId: string;
  language: string;
  autoSync: boolean;
}

export const DEFAULT_SETTINGS: NovelMakerSettings = {
  serverUrl: "http://localhost:8080",
  projectId: "",
  language: "ko",
  autoSync: false,
};
