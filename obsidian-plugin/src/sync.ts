/**
 * VaultSync — synchronizes server data to/from Obsidian vault.
 * Phase 3 will implement the full pullAll() and Phase 5 adds push methods.
 */

import { App, TFile, normalizePath } from "obsidian";
import type { NovelMakerAPI } from "./api";

const VAULT_FOLDER = "NovelMaker";

export class VaultSync {
  /** Tracks file write timestamps to prevent sync loops */
  private lastSyncTimestamps = new Map<string, number>();

  constructor(
    private app: App,
    private api: NovelMakerAPI,
  ) {}

  async pullAll(projectId: string): Promise<void> {
    // Will be implemented in Phase 3
    const basePath = normalizePath(VAULT_FOLDER);
    await this.ensureFolder(basePath);
    await this.ensureFolder(`${basePath}/등장인물`);
    await this.ensureFolder(`${basePath}/줄거리`);
    await this.ensureFolder(`${basePath}/챕터`);
    await this.ensureFolder(`${basePath}/복선`);

    // Pull world setting
    const settings = await this.api.getSettings(projectId);
    await this.writeFile(
      `${basePath}/세계관.md`,
      this.worldSettingToMd(settings),
    );

    // Pull characters
    const characters = await this.api.listCharacters(projectId);
    for (const ch of characters) {
      const relationships = Object.entries(ch.relationships || {})
        .map(([name, rel]) => `- [[${name}]]: ${rel}`)
        .join("\n");

      const content = [
        "---",
        `id: ${ch.id}`,
        `name: "${ch.name}"`,
        `status: ${ch.status}`,
        `location: "${ch.location}"`,
        `traits: "${ch.traits}"`,
        "---",
        "",
        `# ${ch.name}`,
        "",
        `**성격**: ${ch.traits}`,
        `**상태**: ${ch.status}`,
        `**위치**: ${ch.location || "미정"}`,
        "",
        ch.inventory.length > 0
          ? `## 소지품\n${ch.inventory.map((i) => `- ${i}`).join("\n")}`
          : "",
        "",
        relationships ? `## 관계\n${relationships}` : "",
      ]
        .filter(Boolean)
        .join("\n");

      await this.writeFile(`${basePath}/등장인물/${ch.name}.md`, content);
    }

    // Pull outline
    const outline = await this.api.getOutline(projectId);
    for (const ol of outline) {
      const content = [
        "---",
        `chapter: ${ol.chapter}`,
        `pov_character: "${ol.pov_character}"`,
        "---",
        "",
        `# ${ol.chapter}장 개요`,
        "",
        `**목표**: ${ol.goal}`,
        `**시점**: [[${ol.pov_character}]]`,
        "",
        "## 주요 이벤트",
        ...ol.key_events.map((e) => `- ${e}`),
        "",
        "## 등장인물",
        ...ol.involved_characters.map((c) => `- [[${c}]]`),
      ].join("\n");

      await this.writeFile(`${basePath}/줄거리/${ol.chapter}장 개요.md`, content);
    }

    // Pull chapters
    const chapters = await this.api.listChapters(projectId);
    for (const ch of chapters) {
      let detail;
      try {
        detail = await this.api.getChapter(projectId, ch.chapter);
      } catch {
        continue;
      }
      const content = [
        "---",
        `chapter: ${detail.chapter}`,
        `char_count: ${detail.char_count}`,
        `version: ${detail.version}`,
        "---",
        "",
        `# ${detail.chapter}장`,
        "",
        detail.content,
      ].join("\n");

      await this.writeFile(`${basePath}/챕터/${detail.chapter}장.md`, content);
    }

    // Pull foreshadowing
    const foreshadowing = await this.api.listForeshadowing(projectId);
    for (const fs of foreshadowing) {
      const content = [
        "---",
        `id: ${fs.id}`,
        `planted_chapter: ${fs.planted_chapter}`,
        `resolved: ${fs.resolved}`,
        fs.resolved_chapter !== null ? `resolved_chapter: ${fs.resolved_chapter}` : "",
        "---",
        "",
        `# 복선 ${fs.id}`,
        "",
        fs.description,
        "",
        `**설치 챕터**: ${fs.planted_chapter}장`,
        fs.resolved
          ? `**해소**: ${fs.resolved_chapter}장에서 해소됨`
          : "**상태**: 미해소",
      ]
        .filter(Boolean)
        .join("\n");

      await this.writeFile(`${basePath}/복선/복선${fs.id}.md`, content);
    }
  }

  // ---- Push methods (Vault → Server) ----

  /**
   * Push chapter changes from Vault to server.
   * Reads YAML frontmatter to find chapter number, then sends content update.
   */
  async pushChapterChanges(projectId: string, file: TFile): Promise<void> {
    const content = await this.app.vault.read(file);
    const fm = this.parseFrontmatter(content);
    const chapterNum = fm?.chapter;
    if (!chapterNum) return;

    // Extract body (after frontmatter + "# N장" header)
    const body = this.extractBody(content);
    await this.api.updateChapter(projectId, chapterNum, { content: body });
  }

  /**
   * Push character changes from Vault to server.
   * Reads YAML frontmatter to find character id, then sends updates.
   */
  async pushCharacterChanges(projectId: string, file: TFile): Promise<void> {
    const content = await this.app.vault.read(file);
    const fm = this.parseFrontmatter(content);
    const charId = fm?.id;
    if (!charId) return;

    const updates: Record<string, unknown> = {};
    if (fm.status) updates.status = fm.status;
    if (fm.location) updates.location = fm.location;
    if (fm.traits) updates.traits = fm.traits;

    await this.api.updateCharacter(projectId, charId, updates);
  }

  /** Check if a file is inside the NovelMaker vault folder */
  isNovelMakerFile(path: string): boolean {
    return path.startsWith(VAULT_FOLDER + "/");
  }

  /** Determine which sub-folder a file belongs to */
  getFileCategory(path: string): "chapter" | "character" | "outline" | "foreshadowing" | "world" | null {
    if (path.startsWith(`${VAULT_FOLDER}/챕터/`)) return "chapter";
    if (path.startsWith(`${VAULT_FOLDER}/등장인물/`)) return "character";
    if (path.startsWith(`${VAULT_FOLDER}/줄거리/`)) return "outline";
    if (path.startsWith(`${VAULT_FOLDER}/복선/`)) return "foreshadowing";
    if (path === `${VAULT_FOLDER}/세계관.md`) return "world";
    return null;
  }

  /** Check if a file was recently written by sync (within 2s) */
  isRecentlySynced(path: string): boolean {
    const ts = this.lastSyncTimestamps.get(path);
    if (!ts) return false;
    return Date.now() - ts < 2000;
  }

  // ---- Helpers ----

  private parseFrontmatter(content: string): Record<string, unknown> | null {
    const match = content.match(/^---\n([\s\S]*?)\n---/);
    if (!match) return null;

    const fm: Record<string, unknown> = {};
    for (const line of match[1].split("\n")) {
      const colonIdx = line.indexOf(":");
      if (colonIdx === -1) continue;
      const key = line.slice(0, colonIdx).trim();
      let value: string | number | boolean = line.slice(colonIdx + 1).trim();
      // Remove quotes
      if (value.startsWith('"') && value.endsWith('"')) {
        value = value.slice(1, -1);
      }
      // Parse numbers and booleans
      if (/^\d+$/.test(String(value))) value = parseInt(String(value), 10);
      if (value === "true") value = true;
      if (value === "false") value = false;
      fm[key] = value;
    }
    return fm;
  }

  private extractBody(content: string): string {
    // Remove frontmatter
    let body = content.replace(/^---\n[\s\S]*?\n---\n*/, "");
    // Remove "# N장" header
    body = body.replace(/^#\s+\d+장\s*\n*/, "");
    return body.trim();
  }

  private worldSettingToMd(ws: { tone: string; rules: string[]; locations: string[]; time_period: string }): string {
    return [
      "---",
      `tone: "${ws.tone}"`,
      `time_period: "${ws.time_period}"`,
      "---",
      "",
      "# 세계관",
      "",
      `**분위기**: ${ws.tone}`,
      `**시대**: ${ws.time_period || "미정"}`,
      "",
      "## 규칙",
      ...ws.rules.map((r) => `- ${r}`),
      "",
      "## 장소",
      ...ws.locations.map((l) => `- ${l}`),
    ].join("\n");
  }

  private async ensureFolder(path: string): Promise<void> {
    if (!this.app.vault.getAbstractFileByPath(path)) {
      await this.app.vault.createFolder(path);
    }
  }

  private async writeFile(path: string, content: string): Promise<void> {
    const normalizedPath = normalizePath(path);
    const existing = this.app.vault.getAbstractFileByPath(normalizedPath);

    if (existing instanceof TFile) {
      await this.app.vault.modify(existing, content);
    } else {
      await this.app.vault.create(normalizedPath, content);
    }

    this.lastSyncTimestamps.set(normalizedPath, Date.now());
  }
}
