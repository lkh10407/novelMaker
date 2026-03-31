const BASE = '/api/projects';

async function request(url, options = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}

// Projects
export const listProjects = () => request(BASE);
export const createProject = (data) => request(BASE, { method: 'POST', body: JSON.stringify(data) });
export const getProject = (id) => request(`${BASE}/${id}`);
export const updateProject = (id, data) => request(`${BASE}/${id}`, { method: 'PUT', body: JSON.stringify(data) });
export const deleteProject = (id) => request(`${BASE}/${id}`, { method: 'DELETE' });

// Characters
export const listCharacters = (pid) => request(`${BASE}/${pid}/characters`);
export const addCharacter = (pid, data) => request(`${BASE}/${pid}/characters`, { method: 'POST', body: JSON.stringify(data) });
export const updateCharacter = (pid, cid, data) => request(`${BASE}/${pid}/characters/${cid}`, { method: 'PUT', body: JSON.stringify(data) });
export const deleteCharacter = (pid, cid) => request(`${BASE}/${pid}/characters/${cid}`, { method: 'DELETE' });

// Settings
export const getSettings = (pid) => request(`${BASE}/${pid}/settings`);
export const updateSettings = (pid, data) => request(`${BASE}/${pid}/settings`, { method: 'PUT', body: JSON.stringify(data) });

// Foreshadowing
export const listForeshadowing = (pid) => request(`${BASE}/${pid}/foreshadowing`);
export const addForeshadowing = (pid, data) => request(`${BASE}/${pid}/foreshadowing`, { method: 'POST', body: JSON.stringify(data) });
export const updateForeshadowing = (pid, fsId, data) => request(`${BASE}/${pid}/foreshadowing/${fsId}`, { method: 'PUT', body: JSON.stringify(data) });
export const deleteForeshadowing = (pid, fsId) => request(`${BASE}/${pid}/foreshadowing/${fsId}`, { method: 'DELETE' });

// Outline
export const getOutline = (pid) => request(`${BASE}/${pid}/outline`);
export const updateOutline = (pid, data) => request(`${BASE}/${pid}/outline`, { method: 'PUT', body: JSON.stringify(data) });

// Style Reference
export const getStyleReference = (pid) => request(`${BASE}/${pid}/style-reference`);
export const uploadStyleReference = async (pid, file) => {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${BASE}/${pid}/style-reference`, { method: 'POST', body: formData });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
};
export const deleteStyleReference = (pid) => request(`${BASE}/${pid}/style-reference`, { method: 'DELETE' });

// Generation
export const startGeneration = (pid, data) => request(`${BASE}/${pid}/generate`, { method: 'POST', body: JSON.stringify(data) });
export const resumeGeneration = (pid, data) => request(`${BASE}/${pid}/generate/resume`, { method: 'POST', body: JSON.stringify(data) });
export const stopGeneration = (pid) => request(`${BASE}/${pid}/generate/stop`, { method: 'POST' });
export const getGenerationStatus = (pid) => request(`${BASE}/${pid}/generate/status`);
export const approveChapter = (pid, chapterNum, data) => request(`${BASE}/${pid}/generate/approve/${chapterNum}`, { method: 'POST', body: JSON.stringify(data) });

// Chapters
export const listChapters = (pid) => request(`${BASE}/${pid}/chapters`);
export const getChapter = (pid, num) => request(`${BASE}/${pid}/chapters/${num}`);
export const updateChapter = (pid, num, data) => request(`${BASE}/${pid}/chapters/${num}`, { method: 'PUT', body: JSON.stringify(data) });
export const regenerateChapter = (pid, num, data) => request(`${BASE}/${pid}/chapters/${num}/regenerate`, { method: 'POST', body: JSON.stringify(data) });

// Branches
export const createBranch = (pid, num, data) => request(`${BASE}/${pid}/chapters/${num}/branch`, { method: 'POST', body: JSON.stringify(data) });
export const listBranches = (pid, num) => request(`${BASE}/${pid}/chapters/${num}/branches`);
export const adoptBranch = (pid, num, ver) => request(`${BASE}/${pid}/chapters/${num}/branches/${ver}/adopt`, { method: 'POST' });

// Tokens
export const getTokenUsage = (pid) => request(`${BASE}/${pid}/tokens`);

// Export
export const getExportMarkdownUrl = (pid) => `${BASE}/${pid}/export/markdown`;
export const getExportEpubUrl = (pid) => `${BASE}/${pid}/export/epub`;
export const getExportPdfUrl = (pid) => `${BASE}/${pid}/export/pdf`;

// Media (YouTube Video)
export const listVoices = (pid) => request(`${BASE}/${pid}/media/voices`);
export const startMediaGeneration = (pid, data) => request(`${BASE}/${pid}/media/generate`, { method: 'POST', body: JSON.stringify(data) });
export const stopMediaGeneration = (pid) => request(`${BASE}/${pid}/media/stop`, { method: 'POST' });
export const getMediaStatus = (pid) => request(`${BASE}/${pid}/media/status`);
export const getMediaDownloadUrl = (pid) => `${BASE}/${pid}/media/download`;
export const getChapterVideoUrl = (pid, ch) => `${BASE}/${pid}/media/download/${ch}`;
export const getChapterAudioUrl = (pid, ch) => `${BASE}/${pid}/media/download-audio/${ch}`;
