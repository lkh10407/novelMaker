/**
 * NovelMaker API client for Obsidian.
 *
 * REST calls use Obsidian's requestUrl() to bypass CORS.
 * SSE streaming uses native fetch() + ReadableStream manual parsing.
 */

import { requestUrl, RequestUrlParam } from "obsidian";
import type {
  Character,
  WorldSetting,
  ChapterOutline,
  Foreshadowing,
  ChapterResult,
  Project,
  GenerationStatus,
  TokenUsage,
  MediaGenerateRequest,
  MediaStatus,
  MediaVoice,
  SSEPhaseEvent,
  SSEChapterCompleteEvent,
  SSEAwaitingApprovalEvent,
  SSEDoneEvent,
  SSEErrorEvent,
  SSEMediaPhaseEvent,
  SSEMediaChapterCompleteEvent,
  SSEMediaDoneEvent,
  SSEMediaErrorEvent,
} from "./types";

export class NovelMakerAPI {
  constructor(private serverUrl: string) {}

  setServerUrl(url: string) {
    this.serverUrl = url.replace(/\/+$/, "");
  }

  private get base(): string {
    return `${this.serverUrl}/api/projects`;
  }

  private async request<T>(path: string, options: Partial<RequestUrlParam> = {}): Promise<T> {
    const url = path.startsWith("http") ? path : `${this.serverUrl}${path}`;
    const resp = await requestUrl({
      url,
      method: options.method || "GET",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      body: options.body,
    });
    if (resp.status >= 400) {
      throw new Error(`${resp.status}: ${resp.text}`);
    }
    return resp.json as T;
  }

  // ---- Health ----
  async healthCheck(): Promise<{ status: string; version: string }> {
    return this.request("/api/health");
  }

  // ---- Projects ----
  async listProjects(): Promise<Project[]> {
    return this.request("/api/projects");
  }

  async createProject(data: { name: string; logline: string; total_chapters?: number }): Promise<Project> {
    return this.request("/api/projects", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async getProject(id: string): Promise<Project> {
    return this.request(`/api/projects/${id}`);
  }

  async updateProject(id: string, data: Partial<Project>): Promise<Project> {
    return this.request(`/api/projects/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  }

  async deleteProject(id: string): Promise<void> {
    await this.request(`/api/projects/${id}`, { method: "DELETE" });
  }

  // ---- Characters ----
  async listCharacters(pid: string): Promise<Character[]> {
    return this.request(`/api/projects/${pid}/characters`);
  }

  async addCharacter(pid: string, data: Partial<Character>): Promise<Character> {
    return this.request(`/api/projects/${pid}/characters`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async updateCharacter(pid: string, cid: number, data: Partial<Character>): Promise<Character> {
    return this.request(`/api/projects/${pid}/characters/${cid}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  }

  async deleteCharacter(pid: string, cid: number): Promise<void> {
    await this.request(`/api/projects/${pid}/characters/${cid}`, { method: "DELETE" });
  }

  // ---- Settings (WorldSetting) ----
  async getSettings(pid: string): Promise<WorldSetting> {
    return this.request(`/api/projects/${pid}/settings`);
  }

  async updateSettings(pid: string, data: Partial<WorldSetting>): Promise<WorldSetting> {
    return this.request(`/api/projects/${pid}/settings`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  }

  // ---- Outline ----
  async getOutline(pid: string): Promise<ChapterOutline[]> {
    const resp = await this.request<{ total_chapters: number; outline: ChapterOutline[] }>(`/api/projects/${pid}/outline`);
    return resp.outline;
  }

  async updateOutline(pid: string, data: ChapterOutline[]): Promise<ChapterOutline[]> {
    return this.request(`/api/projects/${pid}/outline`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  }

  // ---- Foreshadowing ----
  async listForeshadowing(pid: string): Promise<Foreshadowing[]> {
    return this.request(`/api/projects/${pid}/foreshadowing`);
  }

  async addForeshadowing(pid: string, data: Partial<Foreshadowing>): Promise<Foreshadowing> {
    return this.request(`/api/projects/${pid}/foreshadowing`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async updateForeshadowing(pid: string, fsId: number, data: Partial<Foreshadowing>): Promise<Foreshadowing> {
    return this.request(`/api/projects/${pid}/foreshadowing/${fsId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  }

  async deleteForeshadowing(pid: string, fsId: number): Promise<void> {
    await this.request(`/api/projects/${pid}/foreshadowing/${fsId}`, { method: "DELETE" });
  }

  // ---- Chapters ----
  async listChapters(pid: string): Promise<ChapterResult[]> {
    return this.request(`/api/projects/${pid}/chapters`);
  }

  async getChapter(pid: string, num: number): Promise<ChapterResult> {
    return this.request(`/api/projects/${pid}/chapters/${num}`);
  }

  async updateChapter(pid: string, num: number, data: { content: string }): Promise<ChapterResult> {
    return this.request(`/api/projects/${pid}/chapters/${num}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  }

  async regenerateChapter(pid: string, num: number, data: { guidance?: string }): Promise<void> {
    await this.request(`/api/projects/${pid}/chapters/${num}/regenerate`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  // ---- Branches ----
  async createBranch(pid: string, num: number, data: { guidance?: string }): Promise<ChapterResult> {
    return this.request(`/api/projects/${pid}/chapters/${num}/branch`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async listBranches(pid: string, num: number): Promise<ChapterResult[]> {
    return this.request(`/api/projects/${pid}/chapters/${num}/branches`);
  }

  async adoptBranch(pid: string, num: number, ver: number): Promise<void> {
    await this.request(`/api/projects/${pid}/chapters/${num}/branches/${ver}/adopt`, {
      method: "POST",
    });
  }

  // ---- Generation ----
  async startGeneration(pid: string, data: { language?: string; interactive?: boolean }): Promise<void> {
    await this.request(`/api/projects/${pid}/generate`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async resumeGeneration(pid: string, data: { language?: string; interactive?: boolean }): Promise<void> {
    await this.request(`/api/projects/${pid}/generate/resume`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async stopGeneration(pid: string): Promise<void> {
    await this.request(`/api/projects/${pid}/generate/stop`, { method: "POST" });
  }

  async getGenerationStatus(pid: string): Promise<GenerationStatus> {
    return this.request(`/api/projects/${pid}/generate/status`);
  }

  async approveChapter(
    pid: string,
    chapterNum: number,
    data: { approved: boolean; edited_content?: string | null; guidance?: string },
  ): Promise<void> {
    await this.request(`/api/projects/${pid}/generate/approve/${chapterNum}`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  // ---- Token usage ----
  async getTokenUsage(pid: string): Promise<TokenUsage> {
    return this.request(`/api/projects/${pid}/tokens`);
  }

  // ---- Export URLs ----
  getExportMarkdownUrl(pid: string): string {
    return `${this.serverUrl}/api/projects/${pid}/export/markdown`;
  }

  getExportEpubUrl(pid: string): string {
    return `${this.serverUrl}/api/projects/${pid}/export/epub`;
  }

  getExportPdfUrl(pid: string): string {
    return `${this.serverUrl}/api/projects/${pid}/export/pdf`;
  }

  // ---- Media (YouTube Video) ----

  async listVoices(pid: string): Promise<MediaVoice[]> {
    return this.request(`/api/projects/${pid}/media/voices`);
  }

  async startMediaGeneration(pid: string, data: MediaGenerateRequest): Promise<void> {
    await this.request(`/api/projects/${pid}/media/generate`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async stopMediaGeneration(pid: string): Promise<void> {
    await this.request(`/api/projects/${pid}/media/stop`, { method: "POST" });
  }

  async getMediaStatus(pid: string): Promise<MediaStatus> {
    return this.request(`/api/projects/${pid}/media/status`);
  }

  getMediaDownloadUrl(pid: string): string {
    return `${this.serverUrl}/api/projects/${pid}/media/download`;
  }

  getChapterVideoDownloadUrl(pid: string, chapter: number): string {
    return `${this.serverUrl}/api/projects/${pid}/media/download/${chapter}`;
  }

  getChapterAudioDownloadUrl(pid: string, chapter: number): string {
    return `${this.serverUrl}/api/projects/${pid}/media/download-audio/${chapter}`;
  }

  streamMediaGeneration(
    pid: string,
    callbacks: {
      onPhase?: (data: SSEMediaPhaseEvent) => void;
      onChapterComplete?: (data: SSEMediaChapterCompleteEvent) => void;
      onDone?: (data: SSEMediaDoneEvent) => void;
      onError?: (data: SSEMediaErrorEvent) => void;
      onDisconnect?: () => void;
    },
  ): AbortController {
    const controller = new AbortController();
    const url = `${this.serverUrl}/api/projects/${pid}/media/stream`;

    this._connectMediaSSE(url, controller, callbacks);
    return controller;
  }

  private async _connectMediaSSE(
    url: string,
    controller: AbortController,
    callbacks: Parameters<NovelMakerAPI["streamMediaGeneration"]>[1],
  ): Promise<void> {
    try {
      const response = await fetch(url, {
        signal: controller.signal,
        headers: { Accept: "text/event-stream" },
      });

      if (!response.ok || !response.body) {
        callbacks.onError?.({ message: `Media SSE failed: ${response.status}` });
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        let currentEvent = "";
        let currentData = "";

        for (const line of lines) {
          if (line.startsWith("event:")) {
            currentEvent = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            currentData = line.slice(5).trim();
          } else if (line === "" && currentEvent && currentData) {
            this._handleMediaSSEEvent(currentEvent, currentData, callbacks);
            currentEvent = "";
            currentData = "";
          }
        }
      }
    } catch (e: unknown) {
      if (e instanceof Error && e.name === "AbortError") return;
      callbacks.onDisconnect?.();
    }
  }

  private _handleMediaSSEEvent(
    event: string,
    data: string,
    callbacks: Parameters<NovelMakerAPI["streamMediaGeneration"]>[1],
  ): void {
    if (event === "ping") return;
    try {
      const parsed = JSON.parse(data);
      switch (event) {
        case "media_phase":
          callbacks.onPhase?.(parsed);
          break;
        case "media_chapter_complete":
          callbacks.onChapterComplete?.(parsed);
          break;
        case "media_done":
          callbacks.onDone?.(parsed);
          break;
        case "media_error":
          callbacks.onError?.(parsed);
          break;
        case "end":
          break;
      }
    } catch {
      // Ignore malformed JSON
    }
  }

  // ---- WebSocket Collaboration ----

  /**
   * Connect to the collaboration WebSocket for a project.
   * Returns the WebSocket instance for external management.
   */
  connectCollab(
    pid: string,
    callbacks: {
      onInit?: (data: { locks: Record<string, { user_id: string }>; users: string[] }) => void;
      onUserJoined?: (data: { user_id: string; users: string[] }) => void;
      onUserLeft?: (data: { user_id: string; users: string[] }) => void;
      onChapterLocked?: (data: { chapter: number; user_id: string }) => void;
      onChapterUnlocked?: (data: { chapter: number }) => void;
      onChapterUpdated?: (data: { chapter: number; user_id: string; char_count: number; summary: string }) => void;
      onLockAcquired?: (data: { chapter: number }) => void;
      onLockDenied?: (data: { chapter: number; locked_by: string }) => void;
      onDisconnect?: () => void;
    },
  ): WebSocket {
    const wsUrl = this.serverUrl.replace(/^http/, "ws") + `/ws/${pid}`;
    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        switch (data.type) {
          case "init":
            callbacks.onInit?.(data);
            break;
          case "user_joined":
            callbacks.onUserJoined?.(data);
            break;
          case "user_left":
            callbacks.onUserLeft?.(data);
            break;
          case "chapter_locked":
            callbacks.onChapterLocked?.(data);
            break;
          case "chapter_unlocked":
            callbacks.onChapterUnlocked?.(data);
            break;
          case "chapter_updated":
            callbacks.onChapterUpdated?.(data);
            break;
          case "lock_acquired":
            callbacks.onLockAcquired?.(data);
            break;
          case "lock_denied":
            callbacks.onLockDenied?.(data);
            break;
        }
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onclose = () => callbacks.onDisconnect?.();
    ws.onerror = () => callbacks.onDisconnect?.();

    return ws;
  }

  /** Send a lock request via WebSocket. */
  static sendLock(ws: WebSocket, chapter: number): void {
    ws.send(JSON.stringify({ action: "lock", chapter }));
  }

  /** Send an unlock request via WebSocket. */
  static sendUnlock(ws: WebSocket, chapter: number): void {
    ws.send(JSON.stringify({ action: "unlock", chapter }));
  }

  /** Send a save (with content) via WebSocket. */
  static sendSave(ws: WebSocket, chapter: number, content: string, summary: string = ""): void {
    ws.send(JSON.stringify({ action: "save", chapter, content, summary }));
  }

  // ---- SSE Streaming ----

  /**
   * Connect to SSE generation stream.
   * Uses native fetch + ReadableStream for manual SSE parsing
   * (Obsidian's requestUrl doesn't support streaming).
   */
  streamGeneration(
    pid: string,
    callbacks: {
      onPhase?: (data: SSEPhaseEvent) => void;
      onChapterComplete?: (data: SSEChapterCompleteEvent) => void;
      onAwaitingApproval?: (data: SSEAwaitingApprovalEvent) => void;
      onDone?: (data: SSEDoneEvent) => void;
      onError?: (data: SSEErrorEvent) => void;
      onDisconnect?: () => void;
    },
  ): AbortController {
    const controller = new AbortController();
    const url = `${this.serverUrl}/api/projects/${pid}/generate/stream`;

    this._connectSSE(url, controller, callbacks);
    return controller;
  }

  private async _connectSSE(
    url: string,
    controller: AbortController,
    callbacks: Parameters<NovelMakerAPI["streamGeneration"]>[1],
  ): Promise<void> {
    try {
      const response = await fetch(url, {
        signal: controller.signal,
        headers: { Accept: "text/event-stream" },
      });

      if (!response.ok || !response.body) {
        callbacks.onError?.({ message: `SSE connection failed: ${response.status}` });
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        let currentEvent = "";
        let currentData = "";

        for (const line of lines) {
          if (line.startsWith("event:")) {
            currentEvent = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            currentData = line.slice(5).trim();
          } else if (line === "" && currentEvent && currentData) {
            this._handleSSEEvent(currentEvent, currentData, callbacks);
            currentEvent = "";
            currentData = "";
          }
        }
      }
    } catch (e: unknown) {
      if (e instanceof Error && e.name === "AbortError") return;
      callbacks.onDisconnect?.();
    }
  }

  private _handleSSEEvent(
    event: string,
    data: string,
    callbacks: Parameters<NovelMakerAPI["streamGeneration"]>[1],
  ): void {
    if (event === "ping") return;

    try {
      const parsed = JSON.parse(data);

      switch (event) {
        case "phase":
          callbacks.onPhase?.(parsed);
          break;
        case "chapter_complete":
          callbacks.onChapterComplete?.(parsed);
          break;
        case "awaiting_approval":
          callbacks.onAwaitingApproval?.(parsed);
          break;
        case "done":
          callbacks.onDone?.(parsed);
          break;
        case "error":
          callbacks.onError?.(parsed);
          break;
        case "end":
          // Stream ended normally
          break;
      }
    } catch {
      // Ignore malformed JSON
    }
  }
}
