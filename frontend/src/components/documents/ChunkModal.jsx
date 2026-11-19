import React, { useState, useEffect } from 'react';
import { X, Layers, ChevronLeft, ChevronRight, FileText, Hash, Bookmark } from 'lucide-react';
import { api } from '../../api/client';

export function ChunkModal({ isOpen, onClose, document }) {
  const [chunks, setChunks] = useState([]);
  const [offset, setOffset] = useState(0);
  const [limit] = useState(10);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (isOpen && document) {
      setOffset(0);
      loadChunks(0);
    }
  }, [isOpen, document]);

  const loadChunks = async (currentOffset) => {
    if (!document) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.listChunks(document.id, currentOffset, limit);
      setChunks(data || []);
    } catch (err) {
      setError(err.detail || err.message || 'Failed to load chunks');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen || !document) return null;

  const handleNext = () => {
    const nextOffset = offset + limit;
    setOffset(nextOffset);
    loadChunks(nextOffset);
  };

  const handlePrev = () => {
    const prevOffset = Math.max(0, offset - limit);
    setOffset(prevOffset);
    loadChunks(prevOffset);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
      <div className="w-full max-w-4xl max-h-[85vh] bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-brand-500/10 text-brand-400">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                Document Chunks
                <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 font-mono">
                  {document.filename}
                </span>
              </h3>
              <p className="text-xs text-slate-400">
                Total Chunks: {document.chunk_count || 0} • Pages: {document.page_count || 1}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg text-slate-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <span className="w-8 h-8 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin" />
            </div>
          ) : error ? (
            <div className="p-4 rounded-xl bg-rose-500/10 text-rose-300 text-xs">
              {error}
            </div>
          ) : chunks.length === 0 ? (
            <div className="text-center py-12 text-slate-500 text-xs">
              No chunks available for this document.
            </div>
          ) : (
            chunks.map((chunk) => (
              <div
                key={chunk.id}
                className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 hover:border-slate-700/80 transition text-xs"
              >
                <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800/50 text-[11px] text-slate-400">
                  <div className="flex items-center gap-3">
                    <span className="flex items-center gap-1 font-mono text-brand-400 font-semibold">
                      <Hash className="w-3.5 h-3.5" />
                      Chunk #{chunk.chunk_index}
                    </span>
                    {chunk.page_number && (
                      <span className="flex items-center gap-1">
                        <FileText className="w-3.5 h-3.5 text-slate-500" />
                        Page {chunk.page_number}
                      </span>
                    )}
                    {chunk.section_title && (
                      <span className="flex items-center gap-1 text-slate-300">
                        <Bookmark className="w-3.5 h-3.5 text-amber-400" />
                        {chunk.section_title}
                      </span>
                    )}
                  </div>
                  <span className="text-slate-500 font-mono">{chunk.char_count} chars</span>
                </div>
                <p className="text-slate-200 leading-relaxed font-mono whitespace-pre-wrap text-[11.5px] bg-slate-900/60 p-3 rounded-lg border border-slate-800/40">
                  {chunk.text}
                </p>
              </div>
            ))
          )}
        </div>

        {/* Footer Pagination */}
        <div className="px-6 py-3 border-t border-slate-800 flex items-center justify-between text-xs bg-slate-950/40">
          <span className="text-slate-400">
            Showing {offset + 1} - {offset + chunks.length} of {document.chunk_count || chunks.length}
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={handlePrev}
              disabled={offset === 0 || loading}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-200 transition"
            >
              <ChevronLeft className="w-4 h-4" />
              Previous
            </button>
            <button
              onClick={handleNext}
              disabled={chunks.length < limit || loading}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-200 transition"
            >
              Next
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
