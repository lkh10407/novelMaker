import { useEffect, useState } from 'react';
import { listChapters, getChapter } from '../api';

export default function ChaptersTab({ projectId }) {
  const [chapters, setChapters] = useState([]);
  const [selected, setSelected] = useState(null);
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    listChapters(projectId).then(setChapters);
  }, [projectId]);

  const openChapter = async (num) => {
    setLoading(true);
    try {
      const data = await getChapter(projectId, num);
      setSelected(num);
      setContent(data.content);
    } finally {
      setLoading(false);
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
        {chapters.map(ch => (
          <button key={ch.chapter}
            onClick={() => openChapter(ch.chapter)}
            className={`w-full text-left p-3 rounded-lg transition text-sm ${
              selected === ch.chapter
                ? 'bg-blue-600 text-white shadow'
                : 'bg-white shadow hover:shadow-md'
            }`}>
            <div className="font-semibold">{ch.chapter}장</div>
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
            <h2 className="text-xl font-bold mb-4">{selected}장</h2>
            <div className="prose prose-sm max-w-none whitespace-pre-wrap leading-relaxed text-gray-800">
              {content}
            </div>
          </div>
        ) : (
          <p className="text-gray-400 text-center py-12">왼쪽에서 챕터를 선택하세요.</p>
        )}
      </div>
    </div>
  );
}
