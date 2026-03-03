import { useEffect, useState } from 'react';
import { listChapters, getChapter, updateChapter, regenerateChapter, createBranch, listBranches, adoptBranch } from '../api';
import useCollaboration from '../hooks/useCollaboration';

export default function ChaptersTab({ projectId }) {
  const collab = useCollaboration(projectId);
  const [chapters, setChapters] = useState([]);
  const [selected, setSelected] = useState(null);
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(false);

  // Editing state
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [editSummary, setEditSummary] = useState('');
  const [saving, setSaving] = useState(false);

  // Regeneration state
  const [showRegenForm, setShowRegenForm] = useState(false);
  const [regenGuidance, setRegenGuidance] = useState('');
  const [regenerating, setRegenerating] = useState(false);

  // Branch state
  const [branches, setBranches] = useState([]);
  const [showBranches, setShowBranches] = useState(false);
  const [branchGuidance, setBranchGuidance] = useState('');
  const [branching, setBranching] = useState(false);
  const [compareVersion, setCompareVersion] = useState(null);

  useEffect(() => {
    listChapters(projectId).then(setChapters);
  }, [projectId]);

  const openChapter = async (num) => {
    setLoading(true);
    setEditing(false);
    setShowRegenForm(false);
    setShowBranches(false);
    setCompareVersion(null);
    try {
      const data = await getChapter(projectId, num);
      setSelected(num);
      setContent(data.content);
    } finally {
      setLoading(false);
    }
  };

  // Auto-refresh when another user updates a chapter
  useEffect(() => {
    if (collab.lastUpdate && collab.lastUpdate.chapter === selected) {
      getChapter(projectId, selected).then(data => setContent(data.content));
      listChapters(projectId).then(setChapters);
    }
  }, [collab.lastUpdate]);

  const isLockedByOther = (chNum) => {
    const lock = collab.locks[chNum];
    return lock ? true : false;
  };

  const startEdit = () => {
    collab.lockChapter(selected);
    setEditContent(content);
    setEditSummary(chapters.find(c => c.chapter === selected)?.summary || '');
    setEditing(true);
    setShowRegenForm(false);
    setShowBranches(false);
  };

  const cancelEdit = () => {
    collab.unlockChapter(selected);
    setEditing(false);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateChapter(projectId, selected, {
        content: editContent,
        summary: editSummary,
      });
      collab.saveChapter(selected, editContent, editSummary);
      setContent(editContent);
      setEditing(false);
      listChapters(projectId).then(setChapters);
    } finally {
      setSaving(false);
    }
  };

  const handleRegenerate = async () => {
    setRegenerating(true);
    try {
      await regenerateChapter(projectId, selected, { guidance: regenGuidance });
      const poll = setInterval(async () => {
        try {
          const data = await getChapter(projectId, selected);
          if (data.content !== content) {
            setContent(data.content);
            listChapters(projectId).then(setChapters);
            setRegenerating(false);
            setShowRegenForm(false);
            setRegenGuidance('');
            clearInterval(poll);
          }
        } catch { /* keep polling */ }
      }, 3000);
      setTimeout(() => {
        clearInterval(poll);
        setRegenerating(false);
      }, 120000);
    } catch (e) {
      alert(`재생성 오류: ${e.message}`);
      setRegenerating(false);
    }
  };

  const loadBranches = async () => {
    if (!selected) return;
    const data = await listBranches(projectId, selected);
    setBranches(data);
    setShowBranches(true);
    setEditing(false);
    setShowRegenForm(false);
  };

  const handleCreateBranch = async () => {
    setBranching(true);
    try {
      await createBranch(projectId, selected, { guidance: branchGuidance });
      const poll = setInterval(async () => {
        try {
          const data = await listBranches(projectId, selected);
          if (data.length > branches.length) {
            setBranches(data);
            setBranching(false);
            setBranchGuidance('');
            clearInterval(poll);
          }
        } catch { /* keep polling */ }
      }, 3000);
      setTimeout(() => {
        clearInterval(poll);
        setBranching(false);
      }, 120000);
    } catch (e) {
      alert(`분기 생성 오류: ${e.message}`);
      setBranching(false);
    }
  };

  const handleAdopt = async (version) => {
    try {
      await adoptBranch(projectId, selected, version);
      const data = await getChapter(projectId, selected);
      setContent(data.content);
      listChapters(projectId).then(setChapters);
      setCompareVersion(null);
      alert(`v${version} 채택 완료`);
    } catch (e) {
      alert(`채택 오류: ${e.message}`);
    }
  };

  if (chapters.length === 0) {
    return (
      <p className="text-gray-400 text-center py-12">
        아직 작성된 챕터가 없습니다. 생성 탭에서 소설을 생성해보세요.
      </p>
    );
  }

  return (
    <div className="flex gap-6">
      {/* Chapter list */}
      <div className="w-64 shrink-0 space-y-2">
        {/* Collaboration status */}
        {collab.connected && collab.users.length > 1 && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-2 text-xs text-green-700">
            {collab.users.length}명 접속 중
          </div>
        )}
        {chapters.map(ch => (
          <button key={ch.chapter}
            onClick={() => openChapter(ch.chapter)}
            className={`w-full text-left p-3 rounded-lg transition text-sm ${
              selected === ch.chapter
                ? 'bg-blue-600 text-white shadow'
                : isLockedByOther(ch.chapter)
                  ? 'bg-red-50 shadow border border-red-200'
                  : 'bg-white shadow hover:shadow-md'
            }`}>
            <div className="flex items-center justify-between">
              <span className="font-semibold">{ch.chapter}장</span>
              <div className="flex gap-1">
                {isLockedByOther(ch.chapter) && (
                  <span className="text-xs px-1.5 py-0.5 rounded bg-red-100 text-red-600">
                    편집 중
                  </span>
                )}
                {ch.has_branches && (
                  <span className={`text-xs px-1.5 py-0.5 rounded ${
                    selected === ch.chapter ? 'bg-blue-500' : 'bg-purple-100 text-purple-600'
                  }`}>
                    분기
                  </span>
                )}
              </div>
            </div>
            <div className={`text-xs mt-1 ${selected === ch.chapter ? 'text-blue-100' : 'text-gray-400'}`}>
              {ch.summary || '(요약 없음)'}
            </div>
            <div className={`text-xs mt-1 ${selected === ch.chapter ? 'text-blue-200' : 'text-gray-300'}`}>
              {ch.char_count}자
            </div>
          </button>
        ))}
      </div>

      {/* Chapter content */}
      <div className="flex-1 bg-white rounded-xl shadow p-6 min-h-[400px]">
        {loading ? (
          <p className="text-gray-400">로딩 중...</p>
        ) : selected ? (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold">{selected}장</h2>
              {!editing && !regenerating && !branching && (
                <div className="flex gap-2">
                  <button onClick={startEdit}
                    className="bg-blue-600 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-blue-700 transition">
                    편집
                  </button>
                  <button onClick={() => { setShowRegenForm(!showRegenForm); setEditing(false); setShowBranches(false); }}
                    className="bg-orange-500 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-orange-600 transition">
                    재생성
                  </button>
                  <button onClick={loadBranches}
                    className="bg-purple-600 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-purple-700 transition">
                    분기
                  </button>
                </div>
              )}
            </div>

            {/* Regeneration form */}
            {showRegenForm && !editing && (
              <div className="mb-4 p-4 border border-orange-200 rounded-lg bg-orange-50">
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  재생성 지시사항 (선택)
                </label>
                <textarea
                  value={regenGuidance}
                  onChange={e => setRegenGuidance(e.target.value)}
                  rows={2}
                  placeholder="예: 더 긴장감 있게 다시 써주세요..."
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm mb-3"
                />
                <div className="flex gap-2">
                  <button onClick={handleRegenerate} disabled={regenerating}
                    className="bg-orange-500 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-orange-600 transition disabled:opacity-50">
                    {regenerating ? '재생성 중...' : '재생성 시작'}
                  </button>
                  <button onClick={() => setShowRegenForm(false)}
                    className="text-gray-500 px-3 py-1.5 text-sm hover:bg-gray-100 rounded-lg transition">
                    취소
                  </button>
                </div>
                {regenerating && (
                  <div className="mt-3 flex items-center gap-2 text-sm text-orange-600">
                    <span className="animate-spin inline-block w-4 h-4 border-2 border-orange-400 border-t-transparent rounded-full" />
                    AI가 챕터를 다시 작성하고 있습니다...
                  </div>
                )}
              </div>
            )}

            {/* Branch panel */}
            {showBranches && !editing && (
              <div className="mb-4 p-4 border border-purple-200 rounded-lg bg-purple-50">
                <h3 className="text-sm font-semibold text-purple-700 mb-3">
                  챕터 분기 (What-if) — {branches.length}개 버전
                </h3>

                {/* Create new branch */}
                <div className="mb-4 p-3 bg-white rounded-lg border border-purple-100">
                  <label className="block text-xs font-medium text-gray-600 mb-1">새 분기 지시사항</label>
                  <textarea
                    value={branchGuidance}
                    onChange={e => setBranchGuidance(e.target.value)}
                    rows={2}
                    placeholder="예: 주인공이 다른 선택을 했다면..."
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm mb-2"
                  />
                  <button onClick={handleCreateBranch} disabled={branching}
                    className="bg-purple-600 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-purple-700 transition disabled:opacity-50">
                    {branching ? '생성 중...' : '새 분기 생성'}
                  </button>
                  {branching && (
                    <div className="mt-2 flex items-center gap-2 text-sm text-purple-600">
                      <span className="animate-spin inline-block w-4 h-4 border-2 border-purple-400 border-t-transparent rounded-full" />
                      AI가 대안 버전을 작성하고 있습니다...
                    </div>
                  )}
                </div>

                {/* Version list */}
                {branches.length > 0 && (
                  <div className="space-y-2">
                    {branches.map(b => (
                      <div key={b.version}
                        className={`p-3 rounded-lg border cursor-pointer transition ${
                          compareVersion === b.version
                            ? 'border-purple-400 bg-purple-100'
                            : 'border-gray-200 bg-white hover:border-purple-300'
                        }`}
                        onClick={() => setCompareVersion(compareVersion === b.version ? null : b.version)}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-medium">v{b.version}</span>
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-gray-400">{b.char_count}자</span>
                            <button
                              onClick={(e) => { e.stopPropagation(); handleAdopt(b.version); }}
                              className="text-xs bg-purple-600 text-white px-2 py-0.5 rounded hover:bg-purple-700 transition"
                            >
                              채택
                            </button>
                          </div>
                        </div>
                        <p className="text-xs text-gray-500 mt-1">{b.summary}</p>
                      </div>
                    ))}
                  </div>
                )}

                <button onClick={() => { setShowBranches(false); setCompareVersion(null); }}
                  className="mt-3 text-gray-500 text-xs hover:text-gray-700">
                  닫기
                </button>
              </div>
            )}

            {editing ? (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">요약</label>
                  <input
                    value={editSummary}
                    onChange={e => setEditSummary(e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">내용</label>
                  <textarea
                    value={editContent}
                    onChange={e => setEditContent(e.target.value)}
                    rows={20}
                    className="w-full border border-gray-300 rounded-lg p-3 text-sm leading-relaxed focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  />
                  <div className="text-xs text-gray-400 mt-1 text-right">{editContent.length}자</div>
                </div>
                <div className="flex gap-2">
                  <button onClick={handleSave} disabled={saving}
                    className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition disabled:opacity-50 text-sm">
                    {saving ? '저장 중...' : '저장'}
                  </button>
                  <button onClick={cancelEdit}
                    className="text-gray-500 px-4 py-2 rounded-lg hover:bg-gray-100 transition text-sm">
                    취소
                  </button>
                </div>
              </div>
            ) : compareVersion ? (
              /* Side-by-side comparison */
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-sm font-medium text-purple-700">v{compareVersion} 비교</span>
                  <button onClick={() => setCompareVersion(null)} className="text-xs text-gray-400 hover:text-gray-600">닫기</button>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-xs font-medium text-gray-500 mb-2">현재 버전</div>
                    <div className="prose prose-sm max-w-none whitespace-pre-wrap leading-relaxed text-gray-800 border rounded-lg p-3 max-h-[600px] overflow-y-auto text-sm">
                      {content}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs font-medium text-purple-500 mb-2">v{compareVersion}</div>
                    <div className="prose prose-sm max-w-none whitespace-pre-wrap leading-relaxed text-gray-800 border border-purple-200 rounded-lg p-3 max-h-[600px] overflow-y-auto text-sm bg-purple-50">
                      {branches.find(b => b.version === compareVersion)?.content || ''}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="prose prose-sm max-w-none whitespace-pre-wrap leading-relaxed text-gray-800">
                {content}
              </div>
            )}
          </div>
        ) : (
          <p className="text-gray-400 text-center py-12">왼쪽에서 챕터를 선택하세요.</p>
        )}
      </div>
    </div>
  );
}
