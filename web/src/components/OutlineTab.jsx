import { useEffect, useState } from 'react';
import { getOutline, updateOutline } from '../api';

export default function OutlineTab({ projectId }) {
  const [outline, setOutline] = useState([]);
  const [totalChapters, setTotalChapters] = useState(0);

  const load = () => {
    getOutline(projectId).then(data => {
      setOutline(data.outline || []);
      setTotalChapters(data.total_chapters || 0);
    });
  };
  useEffect(() => { load(); }, [projectId]);

  const updateField = (idx, field, value) => {
    const updated = [...outline];
    updated[idx] = { ...updated[idx], [field]: value };
    setOutline(updated);
  };

  const save = async () => {
    await updateOutline(projectId, outline);
    load();
  };

  const addChapter = () => {
    const next = outline.length + 1;
    setOutline([...outline, {
      chapter: next, goal: '', key_events: [], pov_character: '', involved_characters: [],
    }]);
  };

  const removeChapter = (idx) => {
    const updated = outline.filter((_, i) => i !== idx).map((ol, i) => ({ ...ol, chapter: i + 1 }));
    setOutline(updated);
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold">줄거리 ({outline.length}장)</h2>
        <div className="flex gap-2">
          <button onClick={addChapter}
            className="bg-gray-200 text-gray-700 px-3 py-2 rounded-lg text-sm hover:bg-gray-300">
            + 장 추가
          </button>
          <button onClick={save}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700">
            전체 저장
          </button>
        </div>
      </div>

      {outline.length === 0 ? (
        <p className="text-gray-400 text-center py-8">
          줄거리가 없습니다. AI 기획을 사용하거나 직접 추가해보세요.
        </p>
      ) : (
        <div className="space-y-4">
          {outline.map((ol, idx) => (
            <div key={idx} className="bg-white rounded-xl shadow p-5 space-y-3">
              <div className="flex justify-between items-center">
                <h3 className="font-semibold text-blue-600">{ol.chapter}장</h3>
                <button onClick={() => removeChapter(idx)}
                  className="text-red-400 text-xs hover:underline">삭제</button>
              </div>
              <div>
                <label className="block text-xs font-medium mb-1">목표</label>
                <input value={ol.goal} onChange={e => updateField(idx, 'goal', e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium mb-1">시점 캐릭터</label>
                  <input value={ol.pov_character} onChange={e => updateField(idx, 'pov_character', e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="block text-xs font-medium mb-1">등장인물 (쉼표 구분)</label>
                  <input value={(ol.involved_characters || []).join(', ')}
                    onChange={e => updateField(idx, 'involved_characters',
                      e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium mb-1">핵심 이벤트 (쉼표 구분)</label>
                <input value={(ol.key_events || []).join(', ')}
                  onChange={e => updateField(idx, 'key_events',
                    e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
