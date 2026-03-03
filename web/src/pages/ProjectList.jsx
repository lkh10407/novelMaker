import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listProjects, createProject, deleteProject } from '../api';

const PHASE_LABELS = {
  planning: '기획 중',
  writing: '집필 중',
  checking: '검수 중',
  refining: '교정 중',
  updating: '상태 업데이트',
  replanning: '재기획',
  done: '완료',
};

export default function ProjectList() {
  const [projects, setProjects] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState('');
  const [logline, setLogline] = useState('');
  const [chapters, setChapters] = useState(3);
  const navigate = useNavigate();

  const load = () => listProjects().then(setProjects).catch(console.error);
  useEffect(() => { load(); }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    await createProject({ title, logline, total_chapters: chapters });
    setTitle(''); setLogline(''); setChapters(3); setShowForm(false);
    load();
  };

  const handleDelete = async (e, id) => {
    e.stopPropagation();
    if (!confirm('정말 삭제하시겠습니까?')) return;
    await deleteProject(id);
    load();
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">프로젝트</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition"
        >
          + 새 프로젝트
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="bg-white rounded-xl shadow p-6 mb-6 space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">제목</label>
            <input value={title} onChange={e => setTitle(e.target.value)} required
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:outline-none" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">로그라인</label>
            <textarea value={logline} onChange={e => setLogline(e.target.value)} required rows={2}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:outline-none" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">챕터 수</label>
            <input type="number" value={chapters} onChange={e => setChapters(+e.target.value)} min={1} max={50}
              className="w-24 border border-gray-300 rounded-lg px-3 py-2" />
          </div>
          <button type="submit" className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition">
            생성
          </button>
        </form>
      )}

      {projects.length === 0 ? (
        <p className="text-gray-500 text-center py-12">프로젝트가 없습니다. 새 프로젝트를 만들어보세요.</p>
      ) : (
        <div className="grid gap-4">
          {projects.map(p => (
            <div key={p.project_id}
              onClick={() => navigate(`/project/${p.project_id}`)}
              className="bg-white rounded-xl shadow p-5 cursor-pointer hover:shadow-md transition flex justify-between items-center">
              <div>
                <h2 className="text-lg font-semibold">{p.title}</h2>
                <p className="text-gray-500 text-sm mt-1">{p.logline}</p>
                <div className="flex gap-3 mt-2 text-xs text-gray-400">
                  <span>{p.chapters_written || 0}/{p.total_chapters || 0}장</span>
                  <span>{p.character_count || 0}명</span>
                  <span className="bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
                    {PHASE_LABELS[p.phase] || p.phase}
                  </span>
                </div>
              </div>
              <button onClick={(e) => handleDelete(e, p.project_id)}
                className="text-red-400 hover:text-red-600 text-sm px-3 py-1">
                삭제
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
