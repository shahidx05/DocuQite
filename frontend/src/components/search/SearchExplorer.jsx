import React, { useState } from 'react';
import { 
  Search, 
  Sliders, 
  Layers, 
  Clock, 
  FileText, 
  Hash, 
  Bookmark, 
  Cpu, 
  Sparkles,
  AlertCircle
} from 'lucide-react';
import { api } from '../../api/client';
import { useWorkspace } from '../../context/WorkspaceContext';

export function SearchExplorer() {
  const { activeWorkspace } = useWorkspace();
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState('hybrid');
  const [topK, setTopK] = useState(10);
  const [rerank, setRerank] = useState(true);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!query.trim() || !activeWorkspace) return;

    setLoading(true);
    setError(null);
    try {
      const data = await api.searchWorkspace(activeWorkspace.id, {
        q: query.trim(),
        mode,
        topK,
        rerank,
      });
      setResults(data);
    } catch (err) {
      setError(err.detail || err.message || 'Search execution failed');
    } finally {
      setLoading(false);
    }
  };

  if (!activeWorkspace) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-center h-[calc(100vh-4rem)]">
        <Search className="w-12 h-12 text-slate-600 mb-3" />
        <h3 className="text-base font-semibold text-slate-300">No Workspace Selected</h3>
        <p className="text-xs text-slate-500 mt-1 max-w-sm">
          Select a workspace from the top bar to inspect search indexes and test retrieval queries.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-6">
      {/* Search Controls Panel */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-sm">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 rounded-xl bg-brand-500/10 text-brand-400">
            <Search className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white">Hybrid Retrieval & Reranking Explorer</h3>
            <p className="text-xs text-slate-400">
              Query vector and lexical indexes simultaneously with Reciprocal Rank Fusion (RRF) and Cross-Encoder scoring.
            </p>
          </div>
        </div>

        <form onSubmit={handleSearch} className="space-y-4">
          <div className="relative">
            <input
              type="text"
              required
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Enter search query or keywords to test retrieval..."
              className="w-full bg-slate-950/80 border border-slate-800 rounded-xl pl-4 pr-24 py-3 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
            />
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="absolute right-2 top-1/2 -translate-y-1/2 px-4 py-1.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-40 text-white rounded-lg text-xs font-semibold shadow-md shadow-brand-500/20 transition flex items-center gap-1.5"
            >
              {loading ? (
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <>
                  <Search className="w-3.5 h-3.5" />
                  Search
                </>
              )}
            </button>
          </div>

          {/* Knobs */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
            {/* Mode selection */}
            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                Retrieval Engine
              </label>
              <div className="grid grid-cols-3 gap-1 bg-slate-950/60 p-1 rounded-xl border border-slate-800">
                {['hybrid', 'dense', 'sparse'].map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setMode(m)}
                    className={`py-1.5 text-xs font-medium capitalize rounded-lg transition ${
                      mode === m
                        ? 'bg-brand-600 text-white'
                        : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    {m}
                  </button>
                ))}
              </div>
            </div>

            {/* Top-K Slider */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  Top-K Candidates
                </label>
                <span className="text-xs font-mono font-semibold text-brand-400">{topK}</span>
              </div>
              <input
                type="range"
                min="1"
                max="30"
                value={topK}
                onChange={(e) => setTopK(parseInt(e.target.value))}
                className="w-full accent-brand-500 cursor-pointer"
              />
            </div>

            {/* Cross-encoder toggle */}
            <div className="flex items-center sm:justify-end">
              <label className="flex items-center gap-2.5 cursor-pointer mt-4 sm:mt-0">
                <input
                  type="checkbox"
                  checked={rerank}
                  onChange={(e) => setRerank(e.target.checked)}
                  className="rounded border-slate-700 bg-slate-950 text-brand-600 focus:ring-brand-500 h-4 w-4"
                />
                <span className="text-xs font-medium text-slate-300 flex items-center gap-1.5">
                  <Cpu className="w-4 h-4 text-brand-400" />
                  Cross-Encoder Reranker
                </span>
              </label>
            </div>
          </div>
        </form>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Results Section */}
      {results && (
        <div className="space-y-4">
          <div className="flex items-center justify-between text-xs text-slate-400 px-1">
            <div className="flex items-center gap-3">
              <span>
                Found <strong className="text-slate-200">{results.results?.length || 0}</strong> chunk(s)
              </span>
              <span>•</span>
              <span className="flex items-center gap-1 font-mono text-slate-300">
                <Clock className="w-3.5 h-3.5 text-slate-400" />
                Took: {results.took_ms}ms {results.rerank_ms > 0 && `(Rerank: ${results.rerank_ms}ms)`}
              </span>
            </div>
            <span className="uppercase font-mono text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300">
              Mode: {results.mode}
            </span>
          </div>

          <div className="space-y-3">
            {results.results?.map((res, idx) => (
              <div
                key={res.chunk_id || idx}
                className="p-5 rounded-2xl bg-slate-900 border border-slate-800 hover:border-slate-700/80 transition space-y-3"
              >
                <div className="flex items-center justify-between text-xs pb-2 border-b border-slate-800/60">
                  <div className="flex items-center gap-3">
                    <span className="w-5 h-5 rounded-full bg-slate-800 text-slate-300 font-bold font-mono text-[11px] flex items-center justify-center">
                      {idx + 1}
                    </span>
                    <div className="flex items-center gap-1.5 font-medium text-slate-200">
                      <FileText className="w-4 h-4 text-brand-400" />
                      <span>{res.document_name}</span>
                    </div>
                    {res.page_number && (
                      <span className="text-[11px] text-slate-400 font-mono">
                        Page {res.page_number}
                      </span>
                    )}
                    {res.section_title && (
                      <span className="flex items-center gap-1 text-amber-300 text-[11px]">
                        <Bookmark className="w-3.5 h-3.5" />
                        {res.section_title}
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-2 font-mono text-[11px]">
                    {res.rerank_score !== null && res.rerank_score !== undefined && (
                      <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-semibold" title="Rerank Score">
                        Rerank: {res.rerank_score.toFixed(4)}
                      </span>
                    )}
                    <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-400" title="Initial Retrieval Score">
                      Score: {res.score.toFixed(4)}
                    </span>
                  </div>
                </div>

                <p className="text-xs text-slate-200 leading-relaxed font-mono whitespace-pre-wrap bg-slate-950/70 p-3.5 rounded-xl border border-slate-800/40">
                  {res.text}
                </p>
              </div>
            ))}

            {results.results?.length === 0 && (
              <div className="p-12 text-center text-slate-500 text-xs bg-slate-900 border border-slate-800 rounded-2xl">
                No matching chunks found for query "{results.query}".
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
