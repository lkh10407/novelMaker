import { useState, useRef, useEffect } from 'react';
import { startAnimationGeneration, stopAnimationGeneration, getAnimationStatus, listStoryboard, listDialogue } from '../api';

export default function AnimationTab({ projectId }) {
  const [status, setStatus] = useState('idle');
  const [events, setEvents] = useState([]);
  const [storyboard, setStoryboard] = useState([]);
  const [dialogue, setDialogue] = useState([]);
  const [selectedChapter, setSelectedChapter] = useState(null);
  const [copiedIdx, setCopiedIdx] = useState(null);
  const logEndRef = useRef(null);

  useEffect(() => {
    getAnimationStatus(projectId).then(d => {
      setStatus(d.status);
      if (d.status === 'ready' || d.status === 'completed') loadData();
    }).catch(() => {});
  }, [projectId]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  const loadData = async () => {
    const [sb, dl] = await Promise.all([
      listStoryboard(projectId).catch(() => []),
      listDialogue(projectId).catch(() => []),
    ]);
    setStoryboard(sb);
    setDialogue(dl);
  };

  const handleStart = async () => {
    setEvents([]);
    try {
      await startAnimationGeneration(projectId, {});
      setStatus('running');
      listenSSE();
    } catch (e) {
      setEvents([{ type: 'error', text: e.message }]);
    }
  };

  const handleStop = async () => {
    try {
      await stopAnimationGeneration(projectId);
      setStatus('idle');
    } catch (e) { console.error(e); }
  };

  const listenSSE = () => {
    const es = new EventSource(`/api/projects/${projectId}/animation/stream`);

    es.addEventListener('anim_phase', (e) => {
      const data = JSON.parse(e.data);
      setEvents(prev => [...prev, { type: 'phase', text: data.message || data.phase }]);
    });
    es.addEventListener('anim_storyboard_complete', (e) => {
      const data = JSON.parse(e.data);
      setEvents(prev => [...prev, { type: 'chapter', text: `${data.chapter}장 스토리보드 ${data.scene_count}장면` }]);
    });
    es.addEventListener('anim_dialogue_complete', (e) => {
      const data = JSON.parse(e.data);
      setEvents(prev => [...prev, { type: 'chapter', text: `${data.chapter}장 대본 ${data.line_count}라인` }]);
    });
    es.addEventListener('anim_done', (e) => {
      const data = JSON.parse(e.data);
      setEvents(prev => [...prev, { type: 'done', text: `완료! ${data.total_scenes}장면, ${data.total_lines}대사 (≈$${data.cost_usd})` }]);
      setStatus('ready');
      es.close();
      loadData();
    });
    es.addEventListener('anim_error', (e) => {
      const data = JSON.parse(e.data);
      setEvents(prev => [...prev, { type: 'error', text: data.message }]);
      setStatus('idle');
      es.close();
    });
    es.addEventListener('end', () => es.close());
    es.addEventListener('ping', () => {});
    es.onerror = () => { es.close(); setStatus(prev => prev === 'running' ? 'idle' : prev); };
  };

  const copyPrompt = (text, idx) => {
    navigator.clipboard.writeText(text);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  const chapters = [...new Set(storyboard.map(s => s.chapter))].sort((a, b) => a - b);
  const filteredScenes = selectedChapter ? storyboard.filter(s => s.chapter === selectedChapter) : storyboard;
  const filteredDialogue = selectedChapter ? dialogue.filter(d => d.chapter === selectedChapter) : dialogue;

  return (
    <div className="space-y-6">
      {/* Controls */}
      <div className="bg-white rounded-xl shadow p-6">
        <h2 className="text-lg font-semibold mb-2">스토리보드 + 대본 생성</h2>
        <p className="text-sm text-gray-500 mb-4">
          소설 챕터를 애니메이션 키프레임 장면과 대본으로 자동 분해합니다.
          생성된 이미지 프롬프트를 Flux/Midjourney에 복사해서 사용하세요.
        </p>

        <div className="flex gap-3">
          {status !== 'running' ? (
            <button onClick={handleStart}
              className="bg-purple-600 text-white px-6 py-2 rounded-lg hover:bg-purple-700 transition">
              스토리보드 생성
            </button>
          ) : (
            <button onClick={handleStop}
              className="bg-red-600 text-white px-6 py-2 rounded-lg hover:bg-red-700 transition">
              중단
            </button>
          )}
        </div>
      </div>

      {/* Event log */}
      {events.length > 0 && (
        <div className="bg-gray-900 text-gray-100 rounded-xl p-4 max-h-60 overflow-y-auto font-mono text-sm">
          {events.map((ev, i) => (
            <div key={i} className={`py-1 ${
              ev.type === 'error' ? 'text-red-400' :
              ev.type === 'done' ? 'text-green-400' :
              ev.type === 'chapter' ? 'text-yellow-300' :
              'text-gray-300'
            }`}>{ev.text}</div>
          ))}
          <div ref={logEndRef} />
        </div>
      )}

      {/* Storyboard viewer */}
      {storyboard.length > 0 && (
        <div className="bg-white rounded-xl shadow p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">스토리보드 ({storyboard.length}장면)</h3>
            <select value={selectedChapter || ''} onChange={e => setSelectedChapter(e.target.value ? Number(e.target.value) : null)}
              className="border rounded-lg px-3 py-1.5 text-sm">
              <option value="">전체</option>
              {chapters.map(ch => <option key={ch} value={ch}>{ch}장</option>)}
            </select>
          </div>

          <div className="space-y-4">
            {filteredScenes.map((scene, i) => (
              <div key={`${scene.chapter}-${scene.scene_number}`}
                className="border rounded-lg p-4 hover:bg-gray-50 transition">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-sm">
                    {scene.chapter}장 장면 {scene.scene_number}
                  </span>
                  <div className="flex items-center gap-2 text-xs text-gray-500">
                    <span className="bg-blue-100 text-blue-700 px-2 py-0.5 rounded">{scene.camera_angle}</span>
                    <span className="bg-purple-100 text-purple-700 px-2 py-0.5 rounded">{scene.mood}</span>
                    <span>{scene.duration_seconds}초</span>
                  </div>
                </div>

                <p className="text-sm text-gray-700 mb-2">{scene.visual_description}</p>

                <div className="bg-gray-50 rounded-lg p-3 flex items-start gap-2">
                  <code className="text-xs text-gray-600 flex-1 break-all">{scene.image_prompt}</code>
                  <button onClick={() => copyPrompt(scene.image_prompt, i)}
                    className={`shrink-0 px-3 py-1 rounded text-xs transition ${
                      copiedIdx === i ? 'bg-green-500 text-white' : 'bg-gray-200 hover:bg-gray-300 text-gray-700'
                    }`}>
                    {copiedIdx === i ? '복사됨!' : '복사'}
                  </button>
                </div>

                {scene.characters_present.length > 0 && (
                  <div className="mt-2 flex gap-1 flex-wrap">
                    {scene.characters_present.map(c => (
                      <span key={c} className="bg-gray-100 text-gray-600 px-2 py-0.5 rounded text-xs">{c}</span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Dialogue viewer */}
      {filteredDialogue.length > 0 && (
        <div className="bg-white rounded-xl shadow p-6">
          <h3 className="text-lg font-semibold mb-4">대본 ({filteredDialogue.length}라인)</h3>

          <div className="space-y-2">
            {filteredDialogue.map((line, i) => (
              <div key={i} className={`rounded-lg p-3 ${
                line.speaker === '해설' ? 'bg-gray-50 border-l-4 border-gray-300' : 'bg-blue-50 border-l-4 border-blue-300'
              }`}>
                <div className="flex items-center gap-2 mb-1">
                  <span className={`font-medium text-sm ${
                    line.speaker === '해설' ? 'text-gray-600' : 'text-blue-700'
                  }`}>{line.speaker}</span>
                  <span className="text-xs bg-white px-2 py-0.5 rounded text-gray-500">
                    {line.chapter}장-{line.scene_number}
                  </span>
                  <span className="text-xs text-gray-400">{line.emotion}</span>
                  {line.direction && <span className="text-xs italic text-gray-400">{line.direction}</span>}
                </div>
                <p className="text-sm">{line.text}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
