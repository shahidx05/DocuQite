import { useState } from 'react';

export default function CitationChip({ citation }) {
  const [expanded, setExpanded] = useState(false);

  const { index, document_name, page_number, section_title, snippet } = citation;

  return (
    <div className="inline-block mr-2 mb-2 text-left">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border transition-colors cursor-pointer ${
          expanded
            ? 'bg-indigo-100 text-indigo-800 border-indigo-300'
            : 'bg-indigo-50 text-indigo-700 border-indigo-200 hover:bg-indigo-100'
        }`}
        title="Click to view citation snippet"
      >
        <span className="font-bold">[{index}]</span>
        <span className="truncate max-w-[160px]">{document_name || 'Document'}</span>
        {page_number && <span className="text-indigo-500">p. {page_number}</span>}
        <svg
          className={`w-3.5 h-3.5 transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="mt-2 p-3.5 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-700 shadow-sm space-y-1.5 max-w-xl">
          <div className="flex items-center justify-between text-slate-500 border-b border-slate-200 pb-1.5 font-medium">
            <span className="truncate">{document_name}</span>
            <div className="flex items-center gap-2">
              {page_number && <span>Page {page_number}</span>}
              <button
                type="button"
                onClick={() => setExpanded(false)}
                className="text-slate-400 hover:text-slate-600 ml-2"
                title="Close snippet"
              >
                ✕
              </button>
            </div>
          </div>
          {section_title && (
            <div className="font-semibold text-slate-800">
              Section: <span className="font-normal text-slate-700">{section_title}</span>
            </div>
          )}
          <div className="italic text-slate-600 bg-white p-2.5 rounded border border-slate-200 max-h-48 overflow-y-auto whitespace-pre-wrap leading-relaxed">
            "{snippet}"
          </div>
        </div>
      )}
    </div>
  );
}
