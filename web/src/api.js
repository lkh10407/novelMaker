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
export const deleteProject = (id) => request(`${BASE}/${id}`, { method: 'DELETE' });

// Characters
export const listCharacters = (pid) => request(`${BASE}/${pid}/characters`);
export const addCharacter = (pid, data) => request(`${BASE}/${pid}/characters`, { method: 'POST', body: JSON.stringify(data) });
export const updateCharacter = (pid, cid, data) => request(`${BASE}/${pid}/characters/${cid}`, { method: 'PUT', body: JSON.stringify(data) });
export const deleteCharacter = (pid, cid) => request(`${BASE}/${pid}/characters/${cid}`, { method: 'DELETE' });

// Settings
export const getSettings = (pid) => request(`${BASE}/${pid}/settings`);
export const updateSettings = (pid, data) => request(`${BASE}/${pid}/settings`, { method: 'PUT', body: JSON.stringify(data) });

// Outline
export const getOutline = (pid) => request(`${BASE}/${pid}/outline`);
export const updateOutline = (pid, data) => request(`${BASE}/${pid}/outline`, { method: 'PUT', body: JSON.stringify(data) });

// Generation
export const startGeneration = (pid, data) => request(`${BASE}/${pid}/generate`, { method: 'POST', body: JSON.stringify(data) });
export const stopGeneration = (pid) => request(`${BASE}/${pid}/generate/stop`, { method: 'POST' });
export const getGenerationStatus = (pid) => request(`${BASE}/${pid}/generate/status`);
export const approveChapter = (pid, chapterNum, data) => request(`${BASE}/${pid}/generate/approve/${chapterNum}`, { method: 'POST', body: JSON.stringify(data) });

// Chapters
export const listChapters = (pid) => request(`${BASE}/${pid}/chapters`);
export const getChapter = (pid, num) => request(`${BASE}/${pid}/chapters/${num}`);

// Tokens
export const getTokenUsage = (pid) => request(`${BASE}/${pid}/tokens`);

// Export
export const getExportMarkdownUrl = (pid) => `${BASE}/${pid}/export/markdown`;
