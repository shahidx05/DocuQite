import React, { useState } from 'react';
import { 
  Sparkles, 
  Send, 
  BookOpen, 
  Clock, 
  Zap, 
  AlertTriangle, 
  FileText, 
  AlertCircle,
  HelpCircle
} from 'lucide-react';
import { api } from '../../api/client';
import { useWorkspace } from '../../context/WorkspaceContext';

export function DirectQAView() {
  const { activeWorkspace } = useWorkspace();
  const [question, setQuestion] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleAsk = async (e) => {
    e.preventDefault();
    if (!question.trim() || !activeWorkspace) return;

    setLoading(true);
    setError(null);
    try {
      const data = await api.askWorkspace(activeWorkspace.id, question.trim());
      setResult(data);
    } catch (err) {
      setError(err.detail || err.message || 'Failed to generate answer');
    } finally {
      setLoading(false);
    }
  };

  if (!activeWorkspace) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-center h-[calc(100vh-4rem)]">
        <Sparkles className="w-12 h-12 text-slate-600 mb-3" />
        <h3 className="text-base font-semibold text-slate-300">No Workspace Selected</h3>
        <p className="text-xs text-slate-500 mt-1 max-w-sm">
          Select or create a workspace using the header dropdown to run direct grounded Q&A.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-sm">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 rounded-xl bg-brand-500/10 text-brand-400">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white">Direct Grounded Q&A</h3>
            <p className="text-xs text-slate-400">
              One-shot query evaluation pipeline with strict citation attribution and abstention control.
            </p>
          </div>
        </div>

        <form onSubmit={handleAsk} className="space-y-4">
          <div className="relative">
            <textarea
              rows={3}
              required
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Enter a specific question to answer based strictly on the uploaded workspace documents..."
              className="w-full bg-slate-950/80 border border-slate-800 rounded-xl p-3.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 resize-none"
            />
          </div>

          <div className="flex items-center justify-between">
            <span className="text-[11px] text-slate-500 font-mono">
              {question.length}/500 characters
            </span>
            <button
              type="submit"
              disabled={loading || !question.trim()}
              className="px-5 py-2.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-40 text-white rounded-xl text-xs font-semibold shadow-md shadow-brand-500/20 transition flex items-center gap-2"
            >
              {loading ? (
                <>
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Synthesizing...</span>
                </>
              ) : (
                <>
                  <Send className="w-3.5 h-3.5" />
                  <span>Generate Grounded Answer</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Result Card */}
      {result && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-sm space-y-5 animate-in fade-in duration-200">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <span className="text-xs font-semibold text-slate-300 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-brand-400" />
              Generated Answer
            </span>

            {result.abstained && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                <AlertTriangle className="w-3.5 h-3.5" />
                Abstained (No Sufficient Grounding)
              </span>
            )}
          </div>

          {/* Answer content */}
          <div className="text-xs sm:text-sm text-slate-100 leading-relaxed whitespace-pre-wrap bg-slate-950/60 p-4 rounded-xl border border-slate-800/60 font-sans">
            {result.answer}
          </div>

          {/* Citations */}
          {result.citations && result.citations.length > 0 && (
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 block mb-3 flex items-center gap-1.5">
                <BookOpen className="w-4 h-4 text-brand-400" />
                Grounded Citations ({result.citations.length})
              </span>
              <div className="grid grid-cols-1 gap-2.5">
                {result.citations.map((c) => (
                  <div
                    key={c.n}
                    className="p-3.5 rounded-xl bg-slate-950/40 border border-slate-800/80 text-xs space-y-1.5"
                  >
                    <div className="flex items-center justify-between text-slate-300">
                      <div className="flex items-center gap-2">
                        <span className="w-5 h-5 rounded-full bg-brand-500/20 text-brand-400 font-bold font-mono text-[11px] flex items-center justify-center">
                          {c.n}
                        </span>
                        <span className="font-medium text-slate-200">{c.document_name}</span>
                        {c.page_number && (
                          <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 font-mono text-[10px]">
                            p.{c.page_number}
                          </span>
                        )}
                      </div>
                      {c.section_title && (
                        <span className="text-amber-400 text-[11px] font-medium">
                          {c.section_title}
                        </span>
                      )}
                    </div>
                    <p className="text-slate-400 font-mono text-[11px] bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/40">
                      "{c.snippet}"
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Metrics */}
          {(result.timings || result.tokens) && (
            <div className="pt-3 border-t border-slate-800 flex flex-wrap items-center gap-4 text-[11px] font-mono text-slate-400">
              {result.timings && (
                <div className="flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5 text-slate-400" />
                  <span>
                    Total: <strong className="text-slate-200">{result.timings.total_ms}ms</strong> (Retrieval: {result.timings.retrieval_ms}ms, LLM: {result.timings.llm_ms}ms)
                  </span>
                </div>
              )}
              {result.tokens && (
                <div className="flex items-center gap-1.5">
                  <Zap className="w-3.5 h-3.5 text-amber-400" />
                  <span>
                    Tokens: <strong className="text-slate-200">{result.tokens.input_tokens}</strong> in / <strong className="text-slate-200">{result.tokens.output_tokens}</strong> out
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
