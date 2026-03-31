/**
 * VaultSync — synchronizes server data to/from Obsidian vault.
 *
 * Each project gets its own folder: NovelMaker/{프로젝트명}/
 * On sync, existing files are cleaned and recreated from server state.
 */

import { App, TFile, TFolder, normalizePath } from "obsidian";
import type { NovelMakerAPI } from "./api";
import type { Project } from "./types";

const ROOT_FOLDER = "NovelMaker";

export class VaultSync {
  /** Tracks file write timestamps to prevent sync loops */
  private lastSyncTimestamps = new Map<string, number>();
  private currentProjectFolder = "";

  constructor(
    private app: App,
    private api: NovelMakerAPI,
  ) {}

  async pullAll(projectId: string): Promise<void> {
    // Get project info for folder name
    let project: Project;
    try {
      project = await this.api.getProject(projectId);
    } catch {
      // Fallback to ID if project fetch fails
      project = { project_id: projectId, title: projectId } as Project;
    }

    const projectFolder = this.sanitizeFolderName(project.title || projectId);
    const basePath = normalizePath(`${ROOT_FOLDER}/${projectFolder}`);
    this.currentProjectFolder = basePath;

    // Ensure base folders
    await this.ensureFolder(ROOT_FOLDER);
    await this.ensureFolder(basePath);

    const subfolders = ["등장인물", "줄거리", "챕터", "복선"];
    for (const sub of subfolders) {
      await this.ensureFolder(`${basePath}/${sub}`);
    }

    // Clean existing files in subfolders before syncing
    for (const sub of subfolders) {
      await this.cleanFolder(`${basePath}/${sub}`);
    }
    // Also clean the world setting file
    await this.deleteFileIfExists(`${basePath}/세계관.md`);

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
          ? `## 소지품\n${ch.inventory.map((i: string) => `- ${i}`).join("\n")}`
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
        ...ol.key_events.map((e: string) => `- ${e}`),
        "",
        "## 등장인물",
        ...ol.involved_characters.map((c: string) => `- [[${c}]]`),
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

  async pushChapterChanges(projectId: string, file: TFile): Promise<void> {
    const content = await this.app.vault.read(file);
    const fm = this.parseFrontmatter(content);
    const chapterNum = fm?.chapter;
    if (!chapterNum) return;

    const body = this.extractBody(content);
    await this.api.updateChapter(projectId, chapterNum as number, { content: body });
  }

  async pushCharacterChanges(projectId: string, file: TFile): Promise<void> {
    const content = await this.app.vault.read(file);
    const fm = this.parseFrontmatter(content);
    const charId = fm?.id;
    if (!charId) return;

    const updates: Record<string, unknown> = {};
    if (fm.status) updates.status = fm.status;
    if (fm.location) updates.location = fm.location;
    if (fm.traits) updates.traits = fm.traits;

    await this.api.updateCharacter(projectId, charId as number, updates);
  }

  /** Check if a file is inside the NovelMaker vault folder */
  isNovelMakerFile(path: string): boolean {
    return path.startsWith(ROOT_FOLDER + "/");
  }

  /** Determine which sub-folder a file belongs to */
  getFileCategory(path: string): "chapter" | "character" | "outline" | "foreshadowing" | "world" | null {
    if (path.includes("/챕터/")) return "chapter";
    if (path.includes("/등장인물/")) return "character";
    if (path.includes("/줄거리/")) return "outline";
    if (path.includes("/복선/")) return "foreshadowing";
    if (path.endsWith("세계관.md")) return "world";
    return null;
  }

  /** Check if a file was recently written by sync (within 2s) */
  isRecentlySynced(path: string): boolean {
    const ts = this.lastSyncTimestamps.get(path);
    if (!ts) return false;
    return Date.now() - ts < 2000;
  }

  // ---- Helpers ----

  private sanitizeFolderName(name: string): string {
    // Remove characters not safe for folder names
    return name.replace(/[\\/:*?"<>|]/g, "_").trim() || "unnamed";
  }

  private parseFrontmatter(content: string): Record<string, unknown> | null {
    const match = content.match(/^---\n([\s\S]*?)\n---/);
    if (!match) return null;

    const fm: Record<string, unknown> = {};
    for (const line of match[1].split("\n")) {
      const colonIdx = line.indexOf(":");
      if (colonIdx === -1) continue;
      const key = line.slice(0, colonIdx).trim();
      let value: string | number | boolean = line.slice(colonIdx + 1).trim();
      if (value.startsWith('"') && value.endsWith('"')) {
        value = value.slice(1, -1);
      }
      if (/^\d+$/.test(String(value))) value = parseInt(String(value), 10);
      if (value === "true") value = true;
      if (value === "false") value = false;
      fm[key] = value;
    }
    return fm;
  }

  private extractBody(content: string): string {
    let body = content.replace(/^---\n[\s\S]*?\n---\n*/, "");
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
    const normalized = normalizePath(path);
    if (!this.app.vault.getAbstractFileByPath(normalized)) {
      await this.app.vault.createFolder(normalized);
    }
  }

  /** Delete all .md files in a folder (clean before re-sync) */
  private async cleanFolder(path: string): Promise<void> {
    const normalized = normalizePath(path);
    const folder = this.app.vault.getAbstractFileByPath(normalized);
    if (!(folder instanceof TFolder)) return;

    const filesToDelete: TFile[] = [];
    for (const child of folder.children) {
      if (child instanceof TFile && child.extension === "md") {
        filesToDelete.push(child);
      }
    }

    for (const file of filesToDelete) {
      await this.app.vault.delete(file);
    }
  }

  private async deleteFileIfExists(path: string): Promise<void> {
    const normalized = normalizePath(path);
    const file = this.app.vault.getAbstractFileByPath(normalized);
    if (file instanceof TFile) {
      await this.app.vault.delete(file);
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
