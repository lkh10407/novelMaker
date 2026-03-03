import { useState, useRef, useEffect } from 'react';
import { startGeneration, stopGeneration, getGenerationStatus, getExportMarkdownUrl } from '../api';

const PHASE_LABELS = {
  planning: '기획 중...',
  writing: '집필 중...',
  checking: '검수 중...',
  refining: '교정 중...',
  updating_state: '상태 업데이트 중...',
  replanning: '줄거리 재조정 중...',
  resumed: '이어서 진행 중...',
  done: '완료!',
};

export default function GenerateTab({ projectId, onDone }) {
  const [status, setStatus] = useState('idle');
  const [events, setEvents] = useState([]);
  const [currentPhase, setCurrentPhase] = useState('');
  const [currentChapter, setCurrentChapter] = useState(0);
  const eventSourceRef = useRef(null);
  const logEndRef = useRef(null);

  useEffect(() => {
    getGenerationStatus(projectId).then(d => setStatus(d.status));
    return () => { eventSourceRef.current?.close(); };
  }, [projectId]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  const handleStart = async () => {
    setEvents([]);
    setCurrentPhase('');
    try {
      await startGeneration(projectId, { language: 'ko' });
      setStatus('running');
      listenSSE();
    } catch (e) {
      setEvents([{ type: 'error', message: e.message }]);
    }
  };

  const listenSSE = () => {
    const es = new EventSource(`/api/projects/${projectId}/generate/stream`);
    eventSourceRef.current = es;

    es.addEventListener('phase', (e) => {
      const data = JSON.parse(e.data);
      setCurrentPhase(data.phase);
      if (data.chapter) setCurrentChapter(data.chapter);
      setEvents(prev => [...prev, { type: 'phase', text: PHASE_LABELS[data.phase] || data.phase, chapter: data.chapter }]);
    });

    es.addEventListener('chapter_complete', (e) => {
      const data = JSON.parse(e.data);
      setEvents(prev => [...prev, {
        type: 'chapter',
        text: `${data.chapter}장 완료 (${data.char_count}자) — ${data.summary}`,
      }]);
    });

    es.addEventListener('done', (e) => {
      const data = JSON.parse(e.data);
      setEvents(prev => [...prev, {
        type: 'done',
        text: `생성 완료! 총 토큰: ${data.total_tokens?.toLocaleString()} (≈$${data.cost_usd})`,
      }]);
      setStatus('completed');
      setCurrentPhase('done');
      onDone?.();
    });

    es.addEventListener('error', (e) => {
      try {
        const data = JSON.parse(e.data);
        setEvents(prev => [...prev, { type: 'error', text: `오류: ${data.message}` }]);
      } catch {
        setEvents(prev => [...prev, { type: 'error', text: '연결 오류' }]);
      }
      setStatus('idle');
    });

    es.addEventListener('end', () => {
      es.close();
      setStatus(prev => prev === 'running' ? 'completed' : prev);
    });

    es.onerror = () => {
      es.close();
    };
  };

  const handleStop = async () => {
    try {
      await stopGeneration(projectId);
      eventSourceRef.current?.close();
      setStatus('idle');
      setEvents(prev => [...prev, { type: 'error', text: '생성이 중단되었습니다.' }]);
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-xl shadow p-6">
        <h2 className="text-lg font-semibold mb-4">소설 생성</h2>

        {status === 'running' && currentPhase && (
          <div className="mb-4 p-3 bg-blue-50 text-blue-700 rounded-lg flex items-center gap-2">
            <span className="animate-spin inline-block w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full" />
            <span>
              {currentChapter > 0 && `${currentChapter}장 `}
              {PHASE_LABELS[currentPhase] || currentPhase}
            </span>
          </div>
        )}

        <div className="flex gap-3">
          {status !== 'running' ? (
            <button onClick={handleStart}
              className="bg-green-600 text-white px-6 py-2 rounded-lg hover:bg-green-700 transition">
              생성 시작
            </button>
          ) : (
            <button onClick={handleStop}
              className="bg-red-600 text-white px-6 py-2 rounded-lg hover:bg-red-700 transition">
              중단
            </button>
          )}
          <a href={getExportMarkdownUrl(projectId)} target="_blank"
            className="bg-gray-200 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-300 transition text-sm flex items-center">
            Markdown 내보내기
          </a>
        </div>
      </div>

      {events.length > 0 && (
        <div className="bg-gray-900 text-gray-100 rounded-xl p-4 max-h-96 overflow-y-auto font-mono text-sm">
          {events.map((ev, i) => (
            <div key={i} className={`py-1 ${
              ev.type === 'error' ? 'text-red-400' :
              ev.type === 'done' ? 'text-green-400' :
              ev.type === 'chapter' ? 'text-yellow-300' :
              'text-gray-300'
            }`}>
              {ev.text}
            </div>
          ))}
          <div ref={logEndRef} />
        </div>
      )}
    </div>
  );
}
