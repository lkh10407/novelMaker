import { useEffect, useState } from 'react';
import { listCharacters, addCharacter, updateCharacter, deleteCharacter } from '../api';

const EMPTY = { name: '', traits: '', status: 'alive', location: '', inventory: [], relationships: {} };

export default function CharactersTab({ projectId }) {
  const [characters, setCharacters] = useState([]);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [invText, setInvText] = useState('');
  const [relsText, setRelsText] = useState('');

  const load = () => listCharacters(projectId).then(setCharacters);
  useEffect(() => { load(); }, [projectId]);

  const startEdit = (ch) => {
    setEditing(ch ? ch.id : 'new');
    const data = ch || EMPTY;
    setForm(data);
    setInvText((data.inventory || []).join(', '));
    setRelsText(Object.entries(data.relationships || {}).map(([k, v]) => `${k}:${v}`).join(', '));
  };

  const save = async () => {
    const payload = {
      ...form,
      inventory: invText.split(',').map(s => s.trim()).filter(Boolean),
      relationships: Object.fromEntries(
        relsText.split(',').map(s => s.trim()).filter(Boolean).map(s => {
          const [k, ...v] = s.split(':');
          return [k.trim(), v.join(':').trim()];
        })
      ),
    };
    if (editing === 'new') {
      await addCharacter(projectId, payload);
    } else {
      await updateCharacter(projectId, editing, payload);
    }
    setEditing(null);
    load();
  };

  const handleDelete = async (id) => {
    if (!confirm('삭제하시겠습니까?')) return;
    await deleteCharacter(projectId, id);
    load();
  };

  const STATUS = { alive: '생존', dead: '사망', missing: '실종' };

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold">캐릭터 ({characters.length}명)</h2>
        <button onClick={() => startEdit(null)}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 text-sm">
          + 추가
        </button>
      </div>

      {editing !== null && (
        <div className="bg-white rounded-xl shadow p-5 mb-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium mb-1">이름</label>
              <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1">상태</label>
              <select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
                <option value="alive">생존</option>
                <option value="dead">사망</option>
                <option value="missing">실종</option>
              </select>
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">성격/특성</label>
            <input value={form.traits} onChange={e => setForm({ ...form, traits: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">위치</label>
            <input value={form.location} onChange={e => setForm({ ...form, location: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">소지품 (쉼표 구분)</label>
            <input value={invText} onChange={e => setInvText(e.target.value)}
              placeholder="검, 방패, 물약"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">관계 (이름:관계, 쉼표 구분)</label>
            <input value={relsText} onChange={e => setRelsText(e.target.value)}
              placeholder="영희:연인, 철수:라이벌"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div className="flex gap-2">
            <button onClick={save} className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700">
              저장
            </button>
            <button onClick={() => setEditing(null)} className="text-gray-500 px-4 py-2 text-sm">
              취소
            </button>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {characters.map(ch => (
          <div key={ch.id} className="bg-white rounded-xl shadow p-4 flex justify-between items-start">
            <div>
              <div className="flex items-center gap-2">
                <span className="font-semibold">{ch.name}</span>
                <span className={`text-xs px-2 py-0.5 rounded ${
                  ch.status === 'alive' ? 'bg-green-100 text-green-700' :
                  ch.status === 'dead' ? 'bg-red-100 text-red-700' :
                  'bg-yellow-100 text-yellow-700'
                }`}>
                  {STATUS[ch.status]}
                </span>
              </div>
              <p className="text-sm text-gray-500 mt-1">{ch.traits}</p>
              {ch.location && <p className="text-xs text-gray-400 mt-1">위치: {ch.location}</p>}
              {ch.inventory?.length > 0 && (
                <p className="text-xs text-gray-400">소지품: {ch.inventory.join(', ')}</p>
              )}
            </div>
            <div className="flex gap-2">
              <button onClick={() => startEdit(ch)} className="text-blue-500 text-sm hover:underline">수정</button>
              <button onClick={() => handleDelete(ch.id)} className="text-red-400 text-sm hover:underline">삭제</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
