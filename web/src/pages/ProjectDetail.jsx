import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getProject, updateProject } from '../api';
import SettingsTab from '../components/SettingsTab';
import CharactersTab from '../components/CharactersTab';
import OutlineTab from '../components/OutlineTab';
import GenerateTab from '../components/GenerateTab';
import ChaptersTab from '../components/ChaptersTab';

const TABS = [
  { key: 'settings', label: '세계관' },
  { key: 'characters', label: '캐릭터' },
  { key: 'outline', label: '줄거리' },
  { key: 'generate', label: '생성' },
  { key: 'chapters', label: '챕터' },
];

export default function ProjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState(null);
  const [tab, setTab] = useState('settings');
  const [error, setError] = useState('');

  // Meta editing state
  const [editingMeta, setEditingMeta] = useState(false);
  const [metaTitle, setMetaTitle] = useState('');
  const [metaLogline, setMetaLogline] = useState('');

  const load = () => {
    getProject(id)
      .then(setProject)
      .catch(e => { setError(e.message); });
  };

  useEffect(() => { load(); }, [id]);

  const startEditMeta = () => {
    setMetaTitle(project.title);
    setMetaLogline(project.logline);
    setEditingMeta(true);
  };

  const saveMeta = async () => {
    await updateProject(id, { title: metaTitle, logline: metaLogline });
    setProject({ ...project, title: metaTitle, logline: metaLogline });
    setEditingMeta(false);
  };

  if (error) return <p className="text-red-500 py-12 text-center">{error}</p>;
  if (!project) return <p className="text-gray-400 py-12 text-center">로딩 중...</p>;

  return (
    <div>
      <button onClick={() => navigate('/')} className="text-blue-600 text-sm mb-4 hover:underline">
        &larr; 프로젝트 목록
      </button>

      <div className="mb-6">
        {editingMeta ? (
          <div className="space-y-2">
            <input value={metaTitle} onChange={e => setMetaTitle(e.target.value)}
              className="text-2xl font-bold w-full border border-gray-300 rounded-lg px-3 py-1 focus:ring-2 focus:ring-blue-500 focus:outline-none" />
            <textarea value={metaLogline} onChange={e => setMetaLogline(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none" rows={2} />
            <div className="flex gap-2">
              <button onClick={saveMeta}
                className="bg-blue-600 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-blue-700 transition">
                저장
              </button>
              <button onClick={() => setEditingMeta(false)}
                className="text-gray-500 px-3 py-1.5 text-sm hover:bg-gray-100 rounded-lg transition">
                취소
              </button>
            </div>
          </div>
        ) : (
          <div className="group">
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold">{project.title}</h1>
              <button onClick={startEditMeta}
                className="text-gray-400 hover:text-blue-600 text-sm opacity-0 group-hover:opacity-100 transition">
                수정
              </button>
            </div>
            <p className="text-gray-500 text-sm mt-1">{project.logline}</p>
          </div>
        )}
      </div>

      <div className="flex gap-1 border-b border-gray-200 mb-6">
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition ${
              tab === t.key
                ? 'bg-white border border-b-white border-gray-200 text-blue-600 -mb-px'
                : 'text-gray-500 hover:text-gray-700'
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'settings' && <SettingsTab projectId={id} />}
      {tab === 'characters' && <CharactersTab projectId={id} />}
      {tab === 'outline' && <OutlineTab projectId={id} />}
      {tab === 'generate' && <GenerateTab projectId={id} onDone={load} />}
      {tab === 'chapters' && <ChaptersTab projectId={id} />}
    </div>
  );
}
