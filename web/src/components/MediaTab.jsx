import { useState, useRef, useEffect } from 'react';
import { startMediaGeneration, stopMediaGeneration, getMediaStatus, getMediaDownloadUrl, getChapterVideoUrl, getChapterAudioUrl, listChapters } from '../api';

const VOICES = [
  { id: 'ko-KR-SunHiNeural', name: '선희 (여성)' },
  { id: 'ko-KR-InJoonNeural', name: '인준 (남성)' },
  { id: 'ko-KR-HyunsuMultilingualNeural', name: '현수 (남성, 다국어)' },
];

export default function MediaTab({ projectId }) {
  const [status, setStatus] = useState('idle');
  const [fileSizeMb, setFileSizeMb] = useState(null);
  const [voice, setVoice] = useState('ko-KR-SunHiNeural');
  const [bgColor, setBgColor] = useState('#1a1a2e');
  const [includeTitles, setIncludeTitles] = useState(true);
  const [events, setEvents] = useState([]);
  const [chapters, setChapters] = useState([]);
  const [progress, setProgress] = useState(0);
  const eventSourceRef = useRef(null);
  const logEndRef = useRef(null);

  useEffect(() => {
    getMediaStatus(projectId).then(d => {
      setStatus(d.status === 'ready' || d.status === 'completed' ? 'ready' : d.status);
      if (d.file_size_mb) setFileSizeMb(d.file_size_mb);
    }).catch(() => {});
    listChapters(projectId).then(setChapters).catch(() => {});
  }, [projectId]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  const handleStart = async () => {
    setEvents([]);
    setProgress(0);
    try {
      await startMediaGeneration(projectId, {
        voice,
        background_color: bgColor,
        include_title_cards: includeTitles,
      });
      setStatus('running');
      listenSSE();
    } catch (e) {
      setEvents([{ type: 'error', text: e.message }]);
    }
  };

  const handleStop = async () => {
    try {
      await stopMediaGeneration(projectId);
      eventSourceRef.current?.close();
      setStatus('idle');
      setEvents(prev => [...prev, { type: 'error', text: '영상 생성이 중단되었습니다.' }]);
    } catch (e) {
      console.error(e);
    }
  };

  const listenSSE = () => {
    const es = new EventSource(`/api/projects/${projectId}/media/stream`);
    eventSourceRef.current = es;

    es.addEventListener('media_phase', (e) => {
      const data = JSON.parse(e.data);
      if (data.progress) setProgress(Math.round(data.progress * 100));
      setEvents(prev => [...prev, { type: 'phase', text: data.message || data.phase }]);
    });

    es.addEventListener('media_chapter_complete', (e) => {
      const data = JSON.parse(e.data);
      setProgress(Math.round(data.progress * 100));
      setEvents(prev => [...prev, {
        type: 'chapter',
        text: `${data.chapter}장 영상 완료 (${data.duration}초)`,
      }]);
    });

    es.addEventListener('media_done', (e) => {
      const data = JSON.parse(e.data);
      setFileSizeMb(data.file_size_mb);
      setProgress(100);
      setEvents(prev => [...prev, {
        type: 'done',
        text: `영상 생성 완료! ${data.duration}초, ${data.file_size_mb}MB, ${data.chapters_processed}챕터`,
      }]);
      setStatus('ready');
      es.close();
    });

    es.addEventListener('media_error', (e) => {
      const data = JSON.parse(e.data);
      setEvents(prev => [...prev, { type: 'error', text: `오류: ${data.message}` }]);
      setStatus('idle');
      es.close();
    });

    es.addEventListener('end', () => { es.close(); });
    es.addEventListener('ping', () => {});

    es.onerror = () => {
      es.close();
      setStatus(prev => prev === 'running' ? 'idle' : prev);
    };
  };

  return (
    <div className="space-y-6">
      {/* Settings */}
      <div className="bg-white rounded-xl shadow p-6">
        <h2 className="text-lg font-semibold mb-4">YouTube 영상 생성</h2>
        <p className="text-sm text-gray-500 mb-4">
          소설 챕터를 TTS 음성 + 자막 영상으로 변환합니다.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">음성</label>
            <select value={voice} onChange={e => setVoice(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
              disabled={status === 'running'}>
              {VOICES.map(v => (
                <option key={v.id} value={v.id}>{v.name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">배경 색상</label>
            <div className="flex items-center gap-3">
              <input type="color" value={bgColor} onChange={e => setBgColor(e.target.value)}
                className="w-10 h-10 rounded border cursor-pointer" disabled={status === 'running'} />
              <input type="text" value={bgColor} onChange={e => setBgColor(e.target.value)}
                className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:outline-none"
                disabled={status === 'running'} />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <input type="checkbox" id="titleCards" checked={includeTitles}
              onChange={e => setIncludeTitles(e.target.checked)}
              className="rounded border-gray-300" disabled={status === 'running'} />
            <label htmlFor="titleCards" className="text-sm text-gray-700">챕터 타이틀 카드 포함</label>
          </div>
        </div>

        {/* Progress bar */}
        {status === 'running' && (
          <div className="mb-4">
            <div className="flex justify-between text-sm text-gray-600 mb-1">
              <span>진행률</span>
              <span>{progress}%</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-3">
              <div className="bg-blue-600 h-3 rounded-full transition-all duration-300"
                style={{ width: `${progress}%` }} />
            </div>
          </div>
        )}

        {/* Action buttons */}
        <div className="flex gap-3 flex-wrap">
          {status !== 'running' ? (
            <button onClick={handleStart}
              disabled={chapters.length === 0}
              className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition disabled:opacity-50 disabled:cursor-not-allowed">
              {chapters.length === 0 ? '챕터가 없습니다' : '영상 생성 시작'}
            </button>
          ) : (
            <button onClick={handleStop}
              className="bg-red-600 text-white px-6 py-2 rounded-lg hover:bg-red-700 transition">
              중단
            </button>
          )}

          {status === 'ready' && (
            <>
              <a href={getMediaDownloadUrl(projectId)} target="_blank"
                className="bg-green-600 text-white px-6 py-2 rounded-lg hover:bg-green-700 transition inline-flex items-center gap-2">
                전체 영상 다운로드 {fileSizeMb && `(${fileSizeMb}MB)`}
              </a>
            </>
          )}
        </div>
      </div>

      {/* Per-chapter downloads */}
      {status === 'ready' && chapters.length > 0 && (
        <div className="bg-white rounded-xl shadow p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">챕터별 다운로드</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {chapters.map(ch => (
              <div key={ch.chapter} className="flex gap-1">
                <a href={getChapterVideoUrl(projectId, ch.chapter)} target="_blank"
                  className="flex-1 bg-gray-100 text-gray-700 px-3 py-1.5 rounded text-xs text-center hover:bg-gray-200 transition">
                  {ch.chapter}장 영상
                </a>
                <a href={getChapterAudioUrl(projectId, ch.chapter)} target="_blank"
                  className="bg-gray-100 text-gray-700 px-2 py-1.5 rounded text-xs hover:bg-gray-200 transition">
                  MP3
                </a>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Event log */}
      {events.length > 0 && (
        <div className="bg-gray-900 text-gray-100 rounded-xl p-4 max-h-80 overflow-y-auto font-mono text-sm">
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
