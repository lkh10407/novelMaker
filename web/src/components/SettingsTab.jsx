import { useEffect, useState, useRef } from 'react';
import { getSettings, updateSettings, listForeshadowing, addForeshadowing, updateForeshadowing, deleteForeshadowing, getStyleReference, uploadStyleReference, deleteStyleReference } from '../api';

export default function SettingsTab({ projectId }) {
  const [form, setForm] = useState({ tone: '', rules: [], locations: [], time_period: '' });
  const [saved, setSaved] = useState(false);
  const [rulesText, setRulesText] = useState('');
  const [locsText, setLocsText] = useState('');

  // Foreshadowing state
  const [fsList, setFsList] = useState([]);
  const [addingFs, setAddingFs] = useState(false);
  const [fsDesc, setFsDesc] = useState('');
  const [fsChapter, setFsChapter] = useState(1);

  // Style reference state
  const [styleRef, setStyleRef] = useState('');
  const [uploadingStyle, setUploadingStyle] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    getSettings(projectId).then(s => {
      setForm(s);
      setRulesText((s.rules || []).join('\n'));
      setLocsText((s.locations || []).join('\n'));
    });
    loadFs();
    getStyleReference(projectId).then(d => setStyleRef(d.text || '')).catch(() => {});
  }, [projectId]);

  const loadFs = () => {
    listForeshadowing(projectId).then(setFsList).catch(() => {});
  };

  const save = async () => {
    await updateSettings(projectId, {
      ...form,
      rules: rulesText.split('\n').map(s => s.trim()).filter(Boolean),
      locations: locsText.split('\n').map(s => s.trim()).filter(Boolean),
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const handleAddFs = async () => {
    if (!fsDesc.trim()) return;
    await addForeshadowing(projectId, { planted_chapter: fsChapter, description: fsDesc });
    setFsDesc('');
    setFsChapter(1);
    setAddingFs(false);
    loadFs();
  };

  const handleToggleFs = async (fs) => {
    await updateForeshadowing(projectId, fs.id, {
      resolved: !fs.resolved,
      resolved_chapter: !fs.resolved ? fs.planted_chapter : null,
    });
    loadFs();
  };

  const handleDeleteFs = async (fsId) => {
    if (!confirm('이 복선을 삭제하시겠습니까?')) return;
    await deleteForeshadowing(projectId, fsId);
    loadFs();
  };

  return (
    <div className="space-y-6">
      {/* World settings */}
      <div className="bg-white rounded-xl shadow p-6 space-y-4">
        <h2 className="text-lg font-semibold mb-2">세계관 설정</h2>
        <div>
          <label className="block text-sm font-medium mb-1">톤/분위기</label>
          <input value={form.tone} onChange={e => setForm({ ...form, tone: e.target.value })}
            placeholder="다크, 코믹, 서정적 등"
            className="w-full border border-gray-300 rounded-lg px-3 py-2" />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">시대/배경</label>
          <input value={form.time_period} onChange={e => setForm({ ...form, time_period: e.target.value })}
            placeholder="현대, 중세, 미래 등"
            className="w-full border border-gray-300 rounded-lg px-3 py-2" />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">세계관 규칙 (줄바꿈으로 구분)</label>
          <textarea value={rulesText} onChange={e => setRulesText(e.target.value)} rows={4}
            placeholder="하나의 규칙당 한 줄씩"
            className="w-full border border-gray-300 rounded-lg px-3 py-2" />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">주요 장소 (줄바꿈으로 구분)</label>
          <textarea value={locsText} onChange={e => setLocsText(e.target.value)} rows={3}
            placeholder="장소 이름, 한 줄씩"
            className="w-full border border-gray-300 rounded-lg px-3 py-2" />
        </div>
        <div className="flex items-center gap-3">
          <button onClick={save} className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition">
            저장
          </button>
          {saved && <span className="text-green-600 text-sm">저장되었습니다</span>}
        </div>
      </div>

      {/* Style reference */}
      <div className="bg-white rounded-xl shadow p-6 space-y-4">
        <h2 className="text-lg font-semibold mb-2">문체 레퍼런스</h2>
        <p className="text-sm text-gray-500">참고할 문체 샘플을 업로드하면 AI가 비슷한 스타일로 작성합니다. (.txt / .md)</p>

        {styleRef ? (
          <div>
            <div className="border border-gray-200 rounded-lg p-3 bg-gray-50 max-h-48 overflow-y-auto">
              <pre className="text-sm text-gray-700 whitespace-pre-wrap">{styleRef.slice(0, 2000)}</pre>
              {styleRef.length > 2000 && (
                <p className="text-xs text-gray-400 mt-2">... ({styleRef.length.toLocaleString()}자 중 2,000자 미리보기)</p>
              )}
            </div>
            <div className="flex items-center gap-3 mt-3">
              <span className="text-xs text-gray-400">{styleRef.length.toLocaleString()}자</span>
              <button onClick={async () => {
                await deleteStyleReference(projectId);
                setStyleRef('');
              }} className="text-xs text-red-500 hover:text-red-700">삭제</button>
            </div>
          </div>
        ) : (
          <div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,.md"
              className="hidden"
              onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                setUploadingStyle(true);
                try {
                  await uploadStyleReference(projectId, file);
                  const d = await getStyleReference(projectId);
                  setStyleRef(d.text || '');
                } catch (err) {
                  alert(`업로드 실패: ${err.message}`);
                } finally {
                  setUploadingStyle(false);
                  if (fileInputRef.current) fileInputRef.current.value = '';
                }
              }}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploadingStyle}
              className="bg-gray-100 border-2 border-dashed border-gray-300 rounded-lg px-6 py-4 w-full text-sm text-gray-500 hover:border-blue-400 hover:text-blue-600 transition disabled:opacity-50"
            >
              {uploadingStyle ? '업로드 중...' : '파일 선택 (.txt / .md)'}
            </button>
          </div>
        )}
      </div>

      {/* Foreshadowing management */}
      <div className="bg-white rounded-xl shadow p-6 space-y-4">
        <div className="flex justify-between items-center">
          <h2 className="text-lg font-semibold">복선 / 떡밥 ({fsList.length}개)</h2>
          <button onClick={() => setAddingFs(!addingFs)}
            className="bg-blue-600 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-blue-700 transition">
            {addingFs ? '취소' : '+ 추가'}
          </button>
        </div>

        {addingFs && (
          <div className="border border-gray-200 rounded-lg p-4 space-y-3 bg-gray-50">
            <div className="flex gap-3">
              <div className="w-24">
                <label className="block text-xs font-medium mb-1">심은 장</label>
                <input type="number" min={1} value={fsChapter}
                  onChange={e => setFsChapter(Number(e.target.value))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
              </div>
              <div className="flex-1">
                <label className="block text-xs font-medium mb-1">설명</label>
                <input value={fsDesc} onChange={e => setFsDesc(e.target.value)}
                  placeholder="복선/떡밥 설명..."
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
              </div>
            </div>
            <button onClick={handleAddFs}
              className="bg-green-600 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-green-700 transition">
              저장
            </button>
          </div>
        )}

        {fsList.length === 0 && !addingFs && (
          <p className="text-gray-400 text-sm text-center py-4">등록된 복선이 없습니다.</p>
        )}

        {fsList.map(fs => (
          <div key={fs.id}
            className={`rounded-lg border p-4 ${fs.resolved ? 'bg-green-50 border-green-200' : 'bg-white border-gray-200'}`}>
            <div className="flex justify-between items-start">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                    fs.resolved ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'
                  }`}>
                    {fs.resolved ? `해결 (${fs.resolved_chapter}장)` : '미해결'}
                  </span>
                  <span className="text-xs text-gray-400">{fs.planted_chapter}장에서 심음</span>
                </div>
                <p className="text-sm text-gray-700">{fs.description}</p>
              </div>
              <div className="flex gap-2 ml-3 shrink-0">
                <button onClick={() => handleToggleFs(fs)}
                  className={`text-xs px-2 py-1 rounded ${
                    fs.resolved
                      ? 'text-yellow-600 hover:bg-yellow-50'
                      : 'text-green-600 hover:bg-green-50'
                  }`}>
                  {fs.resolved ? '미해결로' : '해결'}
                </button>
                <button onClick={() => handleDeleteFs(fs.id)}
                  className="text-xs text-red-400 hover:text-red-600 px-2 py-1">
                  삭제
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
