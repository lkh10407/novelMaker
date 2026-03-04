import { App, PluginSettingTab, Setting, Notice } from "obsidian";
import type NovelMakerPlugin from "./main";
import type { Project } from "./types";

export class NovelMakerSettingTab extends PluginSettingTab {
  plugin: NovelMakerPlugin;

  constructor(app: App, plugin: NovelMakerPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    containerEl.createEl("h2", { text: "NovelMaker 설정" });

    // Server URL
    new Setting(containerEl)
      .setName("서버 URL")
      .setDesc("NovelMaker API 서버 주소")
      .addText((text) =>
        text
          .setPlaceholder("http://localhost:8080")
          .setValue(this.plugin.settings.serverUrl)
          .onChange(async (value) => {
            this.plugin.settings.serverUrl = value;
            await this.plugin.saveSettings();
          }),
      );

    // Connection test button
    new Setting(containerEl)
      .setName("연결 테스트")
      .setDesc("서버 연결 상태를 확인합니다")
      .addButton((btn) =>
        btn.setButtonText("테스트").onClick(async () => {
          try {
            const result = await this.plugin.api.healthCheck();
            new Notice(`연결 성공! 서버 버전: ${result.version}`);
          } catch (e) {
            new Notice(`연결 실패: ${e instanceof Error ? e.message : String(e)}`);
          }
        }),
      );

    // Project selection
    new Setting(containerEl)
      .setName("프로젝트")
      .setDesc("작업할 프로젝트를 선택합니다")
      .addDropdown(async (dropdown) => {
        dropdown.addOption("", "-- 프로젝트 선택 --");
        try {
          const projects: Project[] = await this.plugin.api.listProjects();
          for (const p of projects) {
            dropdown.addOption(p.id, p.name);
          }
        } catch {
          // Server might not be reachable
        }
        dropdown.setValue(this.plugin.settings.projectId);
        dropdown.onChange(async (value) => {
          this.plugin.settings.projectId = value;
          await this.plugin.saveSettings();
        });
      });

    // Language
    new Setting(containerEl)
      .setName("언어")
      .setDesc("소설 생성 언어")
      .addDropdown((dropdown) =>
        dropdown
          .addOption("ko", "한국어")
          .addOption("en", "English")
          .setValue(this.plugin.settings.language)
          .onChange(async (value) => {
            this.plugin.settings.language = value;
            await this.plugin.saveSettings();
          }),
      );

    // Auto-sync toggle
    new Setting(containerEl)
      .setName("자동 동기화")
      .setDesc("파일 변경 시 서버와 자동 동기화")
      .addToggle((toggle) =>
        toggle.setValue(this.plugin.settings.autoSync).onChange(async (value) => {
          this.plugin.settings.autoSync = value;
          await this.plugin.saveSettings();
        }),
      );
  }
}
