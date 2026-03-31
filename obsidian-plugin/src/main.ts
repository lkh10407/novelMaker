import { Plugin, TFile, WorkspaceLeaf, Notice } from "obsidian";
import { NovelMakerAPI } from "./api";
import { NovelMakerSettingTab } from "./settings";
import { NovelMakerView, VIEW_TYPE_NOVEL_MAKER } from "./views/NovelMakerView";
import { VaultSync } from "./sync";
import type { NovelMakerSettings } from "./types";
import { DEFAULT_SETTINGS } from "./types";

export default class NovelMakerPlugin extends Plugin {
  settings!: NovelMakerSettings;
  api!: NovelMakerAPI;
  sync: VaultSync | null = null;
  collabWs: WebSocket | null = null;
  collabUsers: string[] = [];
  collabLocks: Map<number, string> = new Map(); // chapter -> user_id

  private debounceTimers = new Map<string, ReturnType<typeof setTimeout>>();

  async onload() {
    await this.loadSettings();
    this.api = new NovelMakerAPI(this.settings.serverUrl);
    this.sync = new VaultSync(this.app, this.api);

    // Register sidebar view
    this.registerView(VIEW_TYPE_NOVEL_MAKER, (leaf) => new NovelMakerView(leaf, this));

    // Ribbon icon
    this.addRibbonIcon("book-open", "NovelMaker", () => {
      this.activateView();
    });

    // Settings tab
    this.addSettingTab(new NovelMakerSettingTab(this.app, this));

    // Commands
    this.addCommand({
      id: "open-novel-maker",
      name: "패널 열기",
      callback: () => this.activateView(),
    });

    this.addCommand({
      id: "sync-project",
      name: "프로젝트 동기화",
      callback: async () => {
        if (this.sync && this.settings.projectId) {
          await this.sync.pullAll(this.settings.projectId);
          new Notice("동기화 완료!");
        }
      },
    });

    this.addCommand({
      id: "export-markdown",
      name: "내보내기 (Markdown)",
      callback: () => {
        if (this.settings.projectId) {
          window.open(this.api.getExportMarkdownUrl(this.settings.projectId));
        }
      },
    });

    this.addCommand({
      id: "export-epub",
      name: "내보내기 (EPUB)",
      callback: () => {
        if (this.settings.projectId) {
          window.open(this.api.getExportEpubUrl(this.settings.projectId));
        }
      },
    });

    this.addCommand({
      id: "export-pdf",
      name: "내보내기 (PDF)",
      callback: () => {
        if (this.settings.projectId) {
          window.open(this.api.getExportPdfUrl(this.settings.projectId));
        }
      },
    });

    this.addCommand({
      id: "connect-collab",
      name: "실시간 협업 연결",
      callback: () => this.connectCollab(),
    });

    this.addCommand({
      id: "disconnect-collab",
      name: "실시간 협업 해제",
      callback: () => this.disconnectCollab(),
    });

    // File watcher for auto-sync (Vault → Server)
    this.registerEvent(
      this.app.vault.on("modify", (file) => {
        if (!(file instanceof TFile)) return;
        if (!this.settings.autoSync) return;
        if (!this.settings.projectId) return;
        if (!this.sync) return;

        // Only watch NovelMaker files
        if (!this.sync.isNovelMakerFile(file.path)) return;

        // Skip files recently written by pullAll() (loop prevention)
        if (this.sync.isRecentlySynced(file.path)) return;

        // Debounce: 3 seconds
        const existing = this.debounceTimers.get(file.path);
        if (existing) clearTimeout(existing);

        this.debounceTimers.set(
          file.path,
          setTimeout(() => {
            this.debounceTimers.delete(file.path);
            this.pushFileChanges(file);
          }, 3000),
        );
      }),
    );
  }

  onunload() {
    this.disconnectCollab();
    for (const timer of this.debounceTimers.values()) {
      clearTimeout(timer);
    }
    this.debounceTimers.clear();
  }

  connectCollab(): void {
    const pid = this.settings.projectId;
    if (!pid) {
      new Notice("프로젝트를 먼저 선택해주세요");
      return;
    }
    if (this.collabWs && this.collabWs.readyState === WebSocket.OPEN) {
      new Notice("이미 협업에 연결되어 있습니다");
      return;
    }

    this.collabWs = this.api.connectCollab(pid, {
      onInit: (data) => {
        this.collabUsers = data.users;
        this.collabLocks.clear();
        for (const [ch, lock] of Object.entries(data.locks)) {
          this.collabLocks.set(Number(ch), lock.user_id);
        }
        new Notice(`협업 연결됨 (${data.users.length}명 접속 중)`);
      },
      onUserJoined: (data) => {
        this.collabUsers = data.users;
        new Notice(`사용자 접속: ${data.user_id}`);
      },
      onUserLeft: (data) => {
        this.collabUsers = data.users;
      },
      onChapterLocked: (data) => {
        this.collabLocks.set(data.chapter, data.user_id);
      },
      onChapterUnlocked: (data) => {
        this.collabLocks.delete(data.chapter);
      },
      onChapterUpdated: (data) => {
        new Notice(`${data.chapter}장이 다른 사용자에 의해 수정됨`);
        // Auto-sync the updated chapter
        if (this.sync) {
          this.sync.pullAll(pid).catch(() => {});
        }
      },
      onLockAcquired: (data) => {
        new Notice(`${data.chapter}장 편집 잠금 획득`);
      },
      onLockDenied: (data) => {
        new Notice(`${data.chapter}장은 다른 사용자(${data.locked_by})가 편집 중입니다`);
      },
      onDisconnect: () => {
        this.collabWs = null;
        this.collabUsers = [];
        this.collabLocks.clear();
      },
    });
  }

  disconnectCollab(): void {
    if (this.collabWs) {
      this.collabWs.close();
      this.collabWs = null;
      this.collabUsers = [];
      this.collabLocks.clear();
    }
  }

  private async pushFileChanges(file: TFile): Promise<void> {
    if (!this.sync || !this.settings.projectId) return;

    const category = this.sync.getFileCategory(file.path);
    try {
      switch (category) {
        case "chapter":
          await this.sync.pushChapterChanges(this.settings.projectId, file);
          break;
        case "character":
          await this.sync.pushCharacterChanges(this.settings.projectId, file);
          break;
        // outline, foreshadowing, world — read-only for now
      }
    } catch (e) {
      console.error(`NovelMaker sync push failed for ${file.path}:`, e);
    }
  }

  async activateView(): Promise<void> {
    const { workspace } = this.app;
    let leaf = workspace.getLeavesOfType(VIEW_TYPE_NOVEL_MAKER)[0];

    if (!leaf) {
      const rightLeaf = workspace.getRightLeaf(false);
      if (rightLeaf) {
        leaf = rightLeaf;
        await leaf.setViewState({ type: VIEW_TYPE_NOVEL_MAKER, active: true });
      }
    }

    if (leaf) {
      workspace.revealLeaf(leaf);
    }
  }

  async loadSettings() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings() {
    await this.saveData(this.settings);
    this.api.setServerUrl(this.settings.serverUrl);
  }
}
