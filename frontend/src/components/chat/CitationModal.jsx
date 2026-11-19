import React from 'react';
import { X, BookOpen, FileText, Bookmark, ExternalLink } from 'lucide-react';

export function CitationModal({ citation, isOpen, onClose }) {
  if (!isOpen || !citation) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="w-full max-w-xl bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-6">
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-brand-500/10 text-brand-400">
              <BookOpen className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                Citation [{citation.n}]
              </h3>
              <p className="text-xs text-slate-400">Grounded Source Verification</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg text-slate-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="mt-4 space-y-3">
          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400 bg-slate-950/50 p-3 rounded-xl border border-slate-800">
            <div className="flex items-center gap-1.5 font-medium text-slate-200">
              <FileText className="w-4 h-4 text-brand-400" />
              <span>{citation.document_name}</span>
            </div>
            {citation.page_number && (
              <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono text-[11px]">
                Page {citation.page_number}
              </span>
            )}
            {citation.section_title && (
              <div className="flex items-center gap-1 text-amber-300">
                <Bookmark className="w-3.5 h-3.5" />
                <span>{citation.section_title}</span>
              </div>
            )}
          </div>

          <div>
            <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block mb-1">
              Referenced Snippet
            </label>
            <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-200 font-mono leading-relaxed whitespace-pre-wrap max-h-64 overflow-y-auto">
              "{citation.snippet}"
            </div>
          </div>
        </div>

        <div className="mt-5 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-medium transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
