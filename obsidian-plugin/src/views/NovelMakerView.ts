import { ItemView, WorkspaceLeaf, Notice, setIcon } from "obsidian";
import type NovelMakerPlugin from "../main";
import type { Project } from "../types";

export const VIEW_TYPE_NOVEL_MAKER = "novel-maker-view";

const PHASE_LABELS: Record<string, string> = {
  planning: "기획 중...",
  writing: "집필 중...",
  checking: "검수 중...",
  refining: "교정 중...",
  updating_state: "상태 업데이트 중...",
  replanning: "줄거리 재조정 중...",
  resumed: "이어서 진행 중...",
  awaiting_approval: "승인 대기 중...",
  done: "완료!",
};

export class NovelMakerView extends ItemView {
  plugin: NovelMakerPlugin;
  private status: "idle" | "running" | "completed" | "interrupted" = "idle";
  private interruptedInfo: { chapter?: number; total?: number } = {};
  private sseController: AbortController | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  // DOM refs
  private projectDropdown!: HTMLSelectElement;
  private logContainer!: HTMLDivElement;
  private controlsContainer!: HTMLDivElement;
  private approvalContainer!: HTMLDivElement;
  private tokenContainer!: HTMLDivElement;

  // Media state
  private mediaContainer!: HTMLDivElement;
  private mediaStatus: "idle" | "running" | "ready" = "idle";
  private mediaSseController: AbortController | null = null;
  private selectedVoice = "ko-KR-SunHiNeural";

  // HITL state
  private awaitingApproval = false;
  private approvalChapter = 0;
  private editedContent = "";
  private guidance = "";

  constructor(leaf: WorkspaceLeaf, plugin: NovelMakerPlugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType(): string {
    return VIEW_TYPE_NOVEL_MAKER;
  }

  getDisplayText(): string {
    return "NovelMaker";
  }

  getIcon(): string {
    return "book-open";
  }

  async onOpen(): Promise<void> {
    const container = this.containerEl.children[1] as HTMLElement;
    container.empty();
    container.addClass("novel-maker-view");

    // Header
    const header = container.createDiv("novel-maker-header");
    header.createEl("h3", { text: "NovelMaker" });

    // Project selector
    const projectSection = container.createDiv("novel-maker-section");
    this.projectDropdown = projectSection.createEl("select", {
      cls: "novel-maker-dropdown",
    });
    this.projectDropdown.addEventListener("change", () => {
      this.plugin.settings.projectId = this.projectDropdown.value;
      this.plugin.saveSettings();
    });
    await this.loadProjects();

    // Controls
    this.controlsContainer = container.createDiv("novel-maker-controls");
    this.renderControls();

    // Approval panel (hidden by default)
    this.approvalContainer = container.createDiv("novel-maker-approval");
    this.approvalContainer.style.display = "none";

    // Event log
    const logSection = container.createDiv("novel-maker-section");
    logSection.createEl("h4", { text: "로그" });
    this.logContainer = logSection.createDiv("novel-maker-log");

    // Media (YouTube video) section
    this.mediaContainer = container.createDiv("novel-maker-section");
    this.renderMediaSection();

    // Token usage
    this.tokenContainer = container.createDiv("novel-maker-section");
    this.tokenContainer.style.display = "none";

    // Load initial status
    await this.refreshStatus();
    await this.refreshMediaStatus();
  }

  async onClose(): Promise<void> {
    this.sseController?.abort();
    this.mediaSseController?.abort();
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
  }

  // ---- Project loading ----

  private async loadProjects(): Promise<void> {
    this.projectDropdown.empty();
    const defaultOpt = this.projectDropdown.createEl("option", {
      text: "-- 프로젝트 선택 --",
      value: "",
    });
    defaultOpt.value = "";

    try {
      const projects: Project[] = await this.plugin.api.listProjects();
      for (const p of projects) {
        const opt = this.projectDropdown.createEl("option", {
          text: p.title,
          value: p.project_id,
        });
        opt.value = p.project_id;
      }
      this.projectDropdown.value = this.plugin.settings.projectId;
    } catch {
      this.addLog("error", "프로젝트 목록을 불러올 수 없습니다");
    }
  }

  // ---- Controls rendering ----

  private renderControls(): void {
    this.controlsContainer.empty();

    if (this.status === "interrupted") {
      const info = this.interruptedInfo;
      const resumeBtn = this.controlsContainer.createEl("button", {
        text: `이어서 생성 (${info.chapter ?? "?"}장부터)`,
        cls: "novel-maker-btn novel-maker-btn-yellow",
      });
      resumeBtn.addEventListener("click", () => this.handleResume(true));

      const resumeAutoBtn = this.controlsContainer.createEl("button", {
        text: "이어서 자동 생성",
        cls: "novel-maker-btn novel-maker-btn-blue",
      });
      resumeAutoBtn.addEventListener("click", () => this.handleResume(false));

      const restartBtn = this.controlsContainer.createEl("button", {
        text: "처음부터 생성",
        cls: "novel-maker-btn novel-maker-btn-gray",
      });
      restartBtn.addEventListener("click", () => this.handleStart(true));
    } else if (this.status !== "running") {
      const interactiveBtn = this.controlsContainer.createEl("button", {
        text: "인터랙티브 생성",
        cls: "novel-maker-btn novel-maker-btn-green",
      });
      interactiveBtn.addEventListener("click", () => this.handleStart(true));

      const autoBtn = this.controlsContainer.createEl("button", {
        text: "자동 생성",
        cls: "novel-maker-btn novel-maker-btn-blue",
      });
      autoBtn.addEventListener("click", () => this.handleStart(false));

      // Sync button
      const syncBtn = this.controlsContainer.createEl("button", {
        text: "동기화",
        cls: "novel-maker-btn novel-maker-btn-gray",
      });
      syncBtn.addEventListener("click", () => this.handleSync());
    } else {
      const stopBtn = this.controlsContainer.createEl("button", {
        text: "중단",
        cls: "novel-maker-btn novel-maker-btn-red",
      });
      stopBtn.addEventListener("click", () => this.handleStop());
    }

    // Export buttons
    const exportRow = this.controlsContainer.createDiv("novel-maker-export-row");
    for (const [label, urlFn] of [
      ["MD", (pid: string) => this.plugin.api.getExportMarkdownUrl(pid)],
      ["EPUB", (pid: string) => this.plugin.api.getExportEpubUrl(pid)],
      ["PDF", (pid: string) => this.plugin.api.getExportPdfUrl(pid)],
    ] as [string, (pid: string) => string][]) {
      const btn = exportRow.createEl("button", {
        text: label,
        cls: "novel-maker-btn novel-maker-btn-sm",
      });
      btn.addEventListener("click", () => {
        const pid = this.getProjectId();
        if (!pid) return;
        window.open(urlFn(pid));
      });
    }
  }

  // ---- Generation ----

  private async handleStart(interactive: boolean): Promise<void> {
    const pid = this.getProjectId();
    if (!pid) return;

    this.logContainer.empty();
    this.awaitingApproval = false;
    this.approvalContainer.style.display = "none";

    try {
      await this.plugin.api.startGeneration(pid, {
        language: this.plugin.settings.language,
        interactive,
      });
      this.status = "running";
      this.renderControls();
      this.listenSSE();
    } catch (e) {
      this.addLog("error", `시작 오류: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  private async handleResume(interactive: boolean): Promise<void> {
    const pid = this.getProjectId();
    if (!pid) return;

    this.logContainer.empty();
    try {
      await this.plugin.api.resumeGeneration(pid, {
        language: this.plugin.settings.language,
        interactive,
      });
      this.status = "running";
      this.renderControls();
      this.listenSSE();
      this.addLog("phase", "중단된 생성을 이어서 진행합니다");
    } catch (e) {
      this.addLog("error", `재개 오류: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  private async handleStop(): Promise<void> {
    const pid = this.getProjectId();
    if (!pid) return;

    try {
      await this.plugin.api.stopGeneration(pid);
      this.sseController?.abort();
      this.status = "idle";
      this.renderControls();
      this.addLog("error", "생성이 중단되었습니다.");
    } catch (e) {
      console.error(e);
    }
  }

  private async handleSync(): Promise<void> {
    const pid = this.getProjectId();
    if (!pid) return;

    if (this.plugin.sync) {
      try {
        await this.plugin.sync.pullAll(pid);
        new Notice("동기화 완료!");
        this.addLog("phase", "Vault 동기화 완료");
      } catch (e) {
        new Notice(`동기화 실패: ${e instanceof Error ? e.message : String(e)}`);
      }
    } else {
      new Notice("동기화 모듈이 아직 로드되지 않았습니다");
    }
  }

  // ---- SSE ----

  private listenSSE(): void {
    const pid = this.getProjectId();
    if (!pid) return;

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    this.sseController = this.plugin.api.streamGeneration(pid, {
      onPhase: (data) => {
        const label = PHASE_LABELS[data.phase] || data.phase;
        const prefix = data.chapter ? `${data.chapter}장 ` : "";
        this.addLog("phase", `${prefix}${label}`);
      },
      onChapterComplete: (data) => {
        this.addLog("chapter", `${data.chapter}장 완료 (${data.char_count}자) — ${data.summary}`);
      },
      onAwaitingApproval: (data) => {
        this.approvalChapter = data.chapter;
        this.editedContent = data.content || "";
        this.guidance = "";
        this.awaitingApproval = true;
        this.renderApprovalPanel();
        this.addLog("approval", `${data.chapter}장 승인 대기 — 검토 후 승인해주세요`);
      },
      onDone: (data) => {
        this.addLog("done", `생성 완료! 총 토큰: ${data.total_tokens?.toLocaleString()} (≈$${data.cost_usd})`);
        this.status = "completed";
        this.renderControls();
        this.loadTokenUsage();
        // Auto-sync after generation
        if (this.plugin.sync) {
          this.plugin.sync.pullAll(pid).catch(() => {});
        }
      },
      onError: (data) => {
        if (data.message) {
          this.addLog("error", `오류: ${data.message}`);
          this.status = "idle";
          this.renderControls();
        }
      },
      onDisconnect: () => {
        // Auto-reconnect
        this.reconnectTimer = setTimeout(async () => {
          try {
            const s = await this.plugin.api.getGenerationStatus(pid);
            if (s.status === "running") {
              this.addLog("phase", "연결 재시도 중...");
              this.listenSSE();
            } else if (s.status === "completed") {
              this.status = "completed";
              this.renderControls();
              this.addLog("done", "생성 완료! (연결 복구 후 확인)");
            } else {
              this.status = "idle";
              this.renderControls();
            }
          } catch {
            this.status = "idle";
            this.renderControls();
            this.addLog("error", "서버 연결 실패");
          }
        }, 3000);
      },
    });
  }

  // ---- HITL Approval ----

  private renderApprovalPanel(): void {
    this.approvalContainer.empty();
    this.approvalContainer.style.display = this.awaitingApproval ? "" : "none";

    if (!this.awaitingApproval) return;

    this.approvalContainer.createEl("h4", { text: `${this.approvalChapter}장 검토` });

    // Content textarea
    this.approvalContainer.createEl("label", {
      text: "챕터 내용",
      cls: "novel-maker-label",
    });
    const contentArea = this.approvalContainer.createEl("textarea", {
      cls: "novel-maker-textarea novel-maker-textarea-lg",
    });
    contentArea.value = this.editedContent;
    contentArea.addEventListener("input", () => {
      this.editedContent = contentArea.value;
    });

    // Guidance textarea
    this.approvalContainer.createEl("label", {
      text: "다음 챕터 지시사항 (선택)",
      cls: "novel-maker-label",
    });
    const guidanceArea = this.approvalContainer.createEl("textarea", {
      cls: "novel-maker-textarea",
      attr: { placeholder: "예: 다음 장에서 주인공이 비밀을 밝히게 해주세요..." },
    });
    guidanceArea.value = this.guidance;
    guidanceArea.addEventListener("input", () => {
      this.guidance = guidanceArea.value;
    });

    // Buttons
    const btnRow = this.approvalContainer.createDiv("novel-maker-btn-row");

    const approveBtn = btnRow.createEl("button", {
      text: "승인",
      cls: "novel-maker-btn novel-maker-btn-green",
    });
    approveBtn.addEventListener("click", () => this.handleApprove(false));

    const editApproveBtn = btnRow.createEl("button", {
      text: "편집 후 승인",
      cls: "novel-maker-btn novel-maker-btn-yellow",
    });
    editApproveBtn.addEventListener("click", () => this.handleApprove(true));
  }

  private async handleApprove(withEdit: boolean): Promise<void> {
    const pid = this.getProjectId();
    if (!pid) return;

    try {
      await this.plugin.api.approveChapter(pid, this.approvalChapter, {
        approved: true,
        edited_content: withEdit ? this.editedContent : null,
        guidance: this.guidance,
      });
      this.awaitingApproval = false;
      this.approvalContainer.style.display = "none";
      this.addLog(
        "phase",
        `${this.approvalChapter}장 승인됨${this.guidance ? " (지시사항 포함)" : ""}`,
      );
    } catch (e) {
      this.addLog("error", `승인 오류: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  // ---- Token usage ----

  private async loadTokenUsage(): Promise<void> {
    const pid = this.getProjectId();
    if (!pid) return;

    try {
      const data = await this.plugin.api.getTokenUsage(pid);
      if (!data || data.total_input_tokens === 0) {
        this.tokenContainer.style.display = "none";
        return;
      }

      this.tokenContainer.empty();
      this.tokenContainer.style.display = "";
      this.tokenContainer.createEl("h4", { text: "토큰 사용량" });

      const grid = this.tokenContainer.createDiv("novel-maker-token-grid");

      const inputBox = grid.createDiv("novel-maker-token-box");
      inputBox.createEl("div", {
        text: data.total_input_tokens.toLocaleString(),
        cls: "novel-maker-token-value",
      });
      inputBox.createEl("div", { text: "입력 토큰", cls: "novel-maker-token-label" });

      const outputBox = grid.createDiv("novel-maker-token-box");
      outputBox.createEl("div", {
        text: data.total_output_tokens.toLocaleString(),
        cls: "novel-maker-token-value",
      });
      outputBox.createEl("div", { text: "출력 토큰", cls: "novel-maker-token-label" });

      const costBox = grid.createDiv("novel-maker-token-box");
      costBox.createEl("div", {
        text: `$${data.estimated_cost_usd ?? "—"}`,
        cls: "novel-maker-token-value",
      });
      costBox.createEl("div", { text: "예상 비용", cls: "novel-maker-token-label" });
    } catch {
      // ignore
    }
  }

  // ---- Status ----

  private async refreshStatus(): Promise<void> {
    const pid = this.getProjectId();
    if (!pid) return;

    try {
      const s = await this.plugin.api.getGenerationStatus(pid) as {
        status: string;
        current_chapter?: number;
        total_chapters?: number;
      };
      if (s.status === "running") {
        this.status = "running";
        this.listenSSE();
      } else if (s.status === "completed") {
        this.status = "completed";
        this.loadTokenUsage();
      } else if (s.status === "interrupted") {
        this.status = "interrupted";
        this.interruptedInfo = {
          chapter: s.current_chapter,
          total: s.total_chapters,
        };
        this.addLog("phase", `중단된 생성이 감지됨 (${s.current_chapter}장/${s.total_chapters}장)`);
      } else {
        this.status = "idle";
      }
      this.renderControls();
    } catch {
      // Server not reachable
    }
  }

  // ---- Helpers ----

  private getProjectId(): string {
    const pid = this.projectDropdown?.value || this.plugin.settings.projectId;
    if (!pid) {
      new Notice("프로젝트를 먼저 선택해주세요");
    }
    return pid;
  }

  private addLog(type: string, text: string): void {
    const entry = this.logContainer.createDiv(`novel-maker-log-entry novel-maker-log-${type}`);
    entry.setText(text);
    this.logContainer.scrollTop = this.logContainer.scrollHeight;
  }

  // ---- Media (YouTube Video) ----

  private renderMediaSection(): void {
    this.mediaContainer.empty();
    this.mediaContainer.createEl("h4", { text: "YouTube 영상 생성" });

    if (this.mediaStatus === "running") {
      const stopBtn = this.mediaContainer.createEl("button", {
        text: "영상 생성 중단",
        cls: "novel-maker-btn novel-maker-btn-red",
      });
      stopBtn.addEventListener("click", () => this.handleMediaStop());
      return;
    }

    // Voice selector
    const voiceRow = this.mediaContainer.createDiv("novel-maker-media-row");
    voiceRow.createEl("label", { text: "음성: ", cls: "novel-maker-label" });
    const voiceSelect = voiceRow.createEl("select", { cls: "novel-maker-dropdown" });
    for (const [id, name] of [
      ["ko-KR-SunHiNeural", "선희 (여성)"],
      ["ko-KR-InJoonNeural", "인준 (남성)"],
      ["ko-KR-HyunsuMultilingualNeural", "현수 (남성, 다국어)"],
    ]) {
      const opt = voiceSelect.createEl("option", { text: name, value: id });
      opt.value = id;
    }
    voiceSelect.value = this.selectedVoice;
    voiceSelect.addEventListener("change", () => {
      this.selectedVoice = voiceSelect.value;
    });

    // Generate button
    const genBtn = this.mediaContainer.createEl("button", {
      text: "영상 생성",
      cls: "novel-maker-btn novel-maker-btn-blue",
    });
    genBtn.addEventListener("click", () => this.handleMediaStart());

    // Download buttons (if ready)
    if (this.mediaStatus === "ready") {
      const dlRow = this.mediaContainer.createDiv("novel-maker-export-row");
      const dlBtn = dlRow.createEl("button", {
        text: "영상 다운로드",
        cls: "novel-maker-btn novel-maker-btn-green",
      });
      dlBtn.addEventListener("click", () => {
        const pid = this.getProjectId();
        if (pid) window.open(this.plugin.api.getMediaDownloadUrl(pid));
      });
    }
  }

  private async handleMediaStart(): Promise<void> {
    const pid = this.getProjectId();
    if (!pid) return;

    try {
      await this.plugin.api.startMediaGeneration(pid, {
        voice: this.selectedVoice,
      });
      this.mediaStatus = "running";
      this.renderMediaSection();
      this.listenMediaSSE();
      this.addLog("phase", "YouTube 영상 생성을 시작합니다");
    } catch (e) {
      this.addLog("error", `영상 생성 오류: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  private async handleMediaStop(): Promise<void> {
    const pid = this.getProjectId();
    if (!pid) return;

    try {
      await this.plugin.api.stopMediaGeneration(pid);
      this.mediaSseController?.abort();
      this.mediaStatus = "idle";
      this.renderMediaSection();
      this.addLog("error", "영상 생성이 중단되었습니다");
    } catch (e) {
      console.error(e);
    }
  }

  private listenMediaSSE(): void {
    const pid = this.getProjectId();
    if (!pid) return;

    this.mediaSseController = this.plugin.api.streamMediaGeneration(pid, {
      onPhase: (data) => {
        this.addLog("phase", data.message || `${data.phase} ${data.chapter ? data.chapter + "장" : ""}`);
      },
      onChapterComplete: (data) => {
        this.addLog("chapter", `${data.chapter}장 영상 완료 (${data.duration}초)`);
      },
      onDone: (data) => {
        this.addLog("done", `영상 생성 완료! ${data.duration}초, ${data.file_size_mb}MB, ${data.chapters_processed}챕터`);
        this.mediaStatus = "ready";
        this.renderMediaSection();
      },
      onError: (data) => {
        this.addLog("error", `영상 오류: ${data.message}`);
        this.mediaStatus = "idle";
        this.renderMediaSection();
      },
      onDisconnect: () => {
        if (this.mediaStatus === "running") {
          this.mediaStatus = "idle";
          this.renderMediaSection();
        }
      },
    });
  }

  private async refreshMediaStatus(): Promise<void> {
    const pid = this.getProjectId();
    if (!pid) return;

    try {
      const s = await this.plugin.api.getMediaStatus(pid);
      if (s.status === "running") {
        this.mediaStatus = "running";
        this.listenMediaSSE();
      } else if (s.status === "ready" || s.status === "completed") {
        this.mediaStatus = "ready";
      } else {
        this.mediaStatus = "idle";
      }
      this.renderMediaSection();
    } catch {
      // Server not reachable
    }
  }
}
