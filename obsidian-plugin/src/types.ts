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
  id: string;
  name: string;
  logline: string;
  total_chapters: number;
  created_at: string;
  updated_at: string;
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
