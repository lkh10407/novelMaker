import { useEffect, useState } from 'react';
import { getSettings, updateSettings } from '../api';

export default function SettingsTab({ projectId }) {
  const [form, setForm] = useState({ tone: '', rules: [], locations: [], time_period: '' });
  const [saved, setSaved] = useState(false);
  const [rulesText, setRulesText] = useState('');
  const [locsText, setLocsText] = useState('');

  useEffect(() => {
    getSettings(projectId).then(s => {
      setForm(s);
      setRulesText((s.rules || []).join('\n'));
      setLocsText((s.locations || []).join('\n'));
    });
  }, [projectId]);

  const save = async () => {
    await updateSettings(projectId, {
      ...form,
      rules: rulesText.split('\n').map(s => s.trim()).filter(Boolean),
      locations: locsText.split('\n').map(s => s.trim()).filter(Boolean),
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
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
  );
}
