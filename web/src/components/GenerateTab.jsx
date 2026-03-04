import { useState, useRef, useEffect, useMemo } from 'react';
import { startGeneration, stopGeneration, getGenerationStatus, getExportMarkdownUrl, getExportEpubUrl, getExportPdfUrl, approveChapter, getTokenUsage } from '../api';

const PHASE_LABELS = {
  planning: '기획 중...',
  writing: '집필 중...',
  checking: '검수 중...',
  refining: '교정 중...',
  updating_state: '상태 업데이트 중...',
  replanning: '줄거리 재조정 중...',
  resumed: '이어서 진행 중...',
  awaiting_approval: '승인 대기 중...',
  done: '완료!',
};

const AGENT_LABELS = {
  planner: '기획',
  writer: '집필',
  checker: '검수',
  refiner: '교정',
  state_update: '상태',
  replanner: '재기획',
};

export default function GenerateTab({ projectId, onDone }) {
  const [status, setStatus] = useState('idle');
  const [events, setEvents] = useState([]);
  const [currentPhase, setCurrentPhase] = useState('');
  const [currentChapter, setCurrentChapter] = useState(0);
  const eventSourceRef = useRef(null);
  const logEndRef = useRef(null);

  // HITL approval state
  const [awaitingApproval, setAwaitingApproval] = useState(false);
  const [approvalChapter, setApprovalChapter] = useState(0);
  const [editedContent, setEditedContent] = useState('');
  const [guidance, setGuidance] = useState('');
  const [approving, setApproving] = useState(false);

  // Token usage
  const [tokenData, setTokenData] = useState(null);

  useEffect(() => {
    getGenerationStatus(projectId).then(d => setStatus(d.status));
    getTokenUsage(projectId).then(setTokenData).catch(() => {});
    return () => {
      eventSourceRef.current?.close();
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    };
  }, [projectId]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  // Reload token data when generation completes
  useEffect(() => {
    if (status === 'completed') {
      getTokenUsage(projectId).then(setTokenData).catch(() => {});
    }
  }, [status, projectId]);

  const agentSummary = useMemo(() => {
    if (!tokenData?.records) return {};
    const summary = {};
    tokenData.records.forEach(r => {
      const agent = r.agent || 'unknown';
      if (!summary[agent]) summary[agent] = { input: 0, output: 0 };
      summary[agent].input += r.input_tokens || 0;
      summary[agent].output += r.output_tokens || 0;
    });
    return summary;
  }, [tokenData]);

  const handleStart = async (interactive = true) => {
    setEvents([]);
    setCurrentPhase('');
    setAwaitingApproval(false);
    try {
      await startGeneration(projectId, { language: 'ko', interactive });
      setStatus('running');
      listenSSE();
    } catch (e) {
      setEvents([{ type: 'error', text: e.message }]);
    }
  };

  const handleApprove = async (withEdit = false) => {
    setApproving(true);
    try {
      await approveChapter(projectId, approvalChapter, {
        approved: true,
        edited_content: withEdit ? editedContent : null,
        guidance,
      });
      setAwaitingApproval(false);
      setEvents(prev => [...prev, {
        type: 'phase',
        text: `${approvalChapter}장 승인됨${guidance ? ' (지시사항 포함)' : ''}`,
      }]);
    } catch (e) {
      setEvents(prev => [...prev, { type: 'error', text: `승인 오류: ${e.message}` }]);
    } finally {
      setApproving(false);
    }
  };

  const reconnectTimerRef = useRef(null);

  const listenSSE = () => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }

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

    es.addEventListener('awaiting_approval', (e) => {
      const data = JSON.parse(e.data);
      setApprovalChapter(data.chapter);
      setEditedContent(data.content || '');
      setGuidance('');
      setAwaitingApproval(true);
      setEvents(prev => [...prev, {
        type: 'approval',
        text: `${data.chapter}장 승인 대기 — 검토 후 승인해주세요`,
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
      es.close();
      onDone?.();
    });

    es.addEventListener('error', (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.message) {
          setEvents(prev => [...prev, { type: 'error', text: `오류: ${data.message}` }]);
          setStatus('idle');
          es.close();
          return;
        }
      } catch { /* connection error, not a data error */ }
    });

    es.addEventListener('end', () => {
      es.close();
      setStatus(prev => prev === 'running' ? 'completed' : prev);
    });

    // Ignore ping heartbeats (keep-alive)
    es.addEventListener('ping', () => {});

    es.onerror = () => {
      es.close();
      // Auto-reconnect: check if generation is still running
      reconnectTimerRef.current = setTimeout(async () => {
        try {
          const s = await getGenerationStatus(projectId);
          if (s.status === 'running') {
            setEvents(prev => [...prev, { type: 'phase', text: '연결 재시도 중...' }]);
            listenSSE();
          } else if (s.status === 'completed') {
            setStatus('completed');
            setCurrentPhase('done');
            setEvents(prev => [...prev, { type: 'done', text: '생성 완료! (연결 복구 후 확인)' }]);
            onDone?.();
          } else {
            setStatus('idle');
          }
        } catch {
          setStatus('idle');
          setEvents(prev => [...prev, { type: 'error', text: '서버 연결 실패' }]);
        }
      }, 3000);
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

        <div className="flex gap-3 flex-wrap">
          {status !== 'running' ? (
            <>
              <button onClick={() => handleStart(true)}
                className="bg-green-600 text-white px-6 py-2 rounded-lg hover:bg-green-700 transition">
                인터랙티브 생성
              </button>
              <button onClick={() => handleStart(false)}
                className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition">
                자동 생성
              </button>
            </>
          ) : (
            <button onClick={handleStop}
              className="bg-red-600 text-white px-6 py-2 rounded-lg hover:bg-red-700 transition">
              중단
            </button>
          )}
          <a href={getExportMarkdownUrl(projectId)} target="_blank"
            className="bg-gray-200 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-300 transition text-sm flex items-center">
            MD
          </a>
          <a href={getExportEpubUrl(projectId)} target="_blank"
            className="bg-gray-200 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-300 transition text-sm flex items-center">
            EPUB
          </a>
          <a href={getExportPdfUrl(projectId)} target="_blank"
            className="bg-gray-200 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-300 transition text-sm flex items-center">
            PDF
          </a>
        </div>
      </div>

      {awaitingApproval && (
        <div className="bg-white rounded-xl shadow p-6 border-l-4 border-yellow-400">
          <h3 className="text-lg font-semibold mb-3">{approvalChapter}장 검토</h3>

          <label className="block text-sm font-medium text-gray-700 mb-1">챕터 내용</label>
          <textarea
            value={editedContent}
            onChange={(e) => setEditedContent(e.target.value)}
            rows={12}
            className="w-full border rounded-lg p-3 font-mono text-sm mb-4 focus:ring-2 focus:ring-yellow-300 focus:border-yellow-400"
          />

          <label className="block text-sm font-medium text-gray-700 mb-1">다음 챕터 지시사항 (선택)</label>
          <textarea
            value={guidance}
            onChange={(e) => setGuidance(e.target.value)}
            rows={3}
            placeholder="예: 다음 장에서 주인공이 비밀을 밝히게 해주세요..."
            className="w-full border rounded-lg p-3 text-sm mb-4 focus:ring-2 focus:ring-yellow-300 focus:border-yellow-400"
          />

          <div className="flex gap-3">
            <button
              onClick={() => handleApprove(false)}
              disabled={approving}
              className="bg-green-600 text-white px-6 py-2 rounded-lg hover:bg-green-700 transition disabled:opacity-50"
            >
              {approving ? '처리 중...' : '승인'}
            </button>
            <button
              onClick={() => handleApprove(true)}
              disabled={approving}
              className="bg-yellow-500 text-white px-6 py-2 rounded-lg hover:bg-yellow-600 transition disabled:opacity-50"
            >
              {approving ? '처리 중...' : '편집 후 승인'}
            </button>
          </div>
        </div>
      )}

      {events.length > 0 && (
        <div className="bg-gray-900 text-gray-100 rounded-xl p-4 max-h-96 overflow-y-auto font-mono text-sm">
          {events.map((ev, i) => (
            <div key={i} className={`py-1 ${
              ev.type === 'error' ? 'text-red-400' :
              ev.type === 'done' ? 'text-green-400' :
              ev.type === 'chapter' ? 'text-yellow-300' :
              ev.type === 'approval' ? 'text-orange-300' :
              'text-gray-300'
            }`}>
              {ev.text}
            </div>
          ))}
          <div ref={logEndRef} />
        </div>
      )}

      {/* Token usage dashboard */}
      {tokenData && tokenData.total_input_tokens > 0 && (
        <div className="bg-white rounded-xl shadow p-6">
          <h3 className="text-lg font-semibold mb-4">토큰 사용량</h3>
          <div className="grid grid-cols-3 gap-4 mb-6">
            <div className="bg-blue-50 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-blue-600">
                {(tokenData.total_input_tokens || 0).toLocaleString()}
              </div>
              <div className="text-xs text-gray-500 mt-1">입력 토큰</div>
            </div>
            <div className="bg-green-50 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-green-600">
                {(tokenData.total_output_tokens || 0).toLocaleString()}
              </div>
              <div className="text-xs text-gray-500 mt-1">출력 토큰</div>
            </div>
            <div className="bg-purple-50 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-purple-600">
                ${tokenData.estimated_cost_usd ?? '—'}
              </div>
              <div className="text-xs text-gray-500 mt-1">예상 비용</div>
            </div>
          </div>

          {Object.keys(agentSummary).length > 0 && (
            <>
              <h4 className="text-sm font-medium text-gray-700 mb-3">에이전트별 사용량</h4>
              <div className="space-y-2">
                {Object.entries(agentSummary).map(([agent, counts]) => {
                  const total = counts.input + counts.output;
                  const maxTokens = Math.max(...Object.values(agentSummary).map(c => c.input + c.output));
                  const widthPercent = maxTokens > 0 ? (total / maxTokens) * 100 : 0;
                  return (
                    <div key={agent} className="flex items-center gap-3">
                      <span className="w-20 text-xs text-gray-600 text-right shrink-0">
                        {AGENT_LABELS[agent] || agent}
                      </span>
                      <div className="flex-1 bg-gray-100 rounded-full h-5 overflow-hidden">
                        <div className="bg-blue-500 h-full rounded-full transition-all"
                          style={{ width: `${widthPercent}%` }} />
                      </div>
                      <span className="text-xs text-gray-500 w-24 text-right shrink-0">
                        {total.toLocaleString()}
                      </span>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
