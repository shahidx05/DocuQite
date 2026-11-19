import React from 'react';
import { 
  Bot, 
  User, 
  AlertTriangle, 
  BookOpen, 
  Clock, 
  Zap, 
  Repeat, 
  FileText,
  Bookmark
} from 'lucide-react';

export function ChatMessage({ message, onSelectCitation }) {
  const isAssistant = message.role === 'assistant';
  const meta = message.metadata || {};
  const timings = meta.timings;
  const tokens = meta.tokens;
  const rewrittenQuestion = meta.rewritten_question;

  return (
    <div
      className={`py-4 px-4 sm:px-6 flex gap-4 ${
        isAssistant ? 'bg-slate-900/40 border-y border-slate-800/40' : 'bg-transparent'
      }`}
    >
      {/* Avatar */}
      <div className="shrink-0 pt-0.5">
        {isAssistant ? (
          <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-brand-600 to-indigo-600 flex items-center justify-center shadow-md shadow-brand-500/20 text-white">
            <Bot className="w-4 h-4" />
          </div>
        ) : (
          <div className="w-8 h-8 rounded-xl bg-slate-800 flex items-center justify-center text-slate-300">
            <User className="w-4 h-4" />
          </div>
        )}
      </div>

      {/* Body */}
      <div className="flex-1 space-y-2.5 overflow-hidden">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-300">
              {isAssistant ? 'DocuMind Assistant' : 'You'}
            </span>
            <span className="text-[10px] text-slate-500">
              {new Date(message.created_at || Date.now()).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </span>
          </div>

          {/* Abstained badge */}
          {isAssistant && message.abstained && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
              <AlertTriangle className="w-3 h-3" />
              Abstained (Insufficient Context)
            </span>
          )}
        </div>

        {/* Rewritten Question Indicator */}
        {isAssistant && rewrittenQuestion && (
          <div className="flex items-center gap-1.5 text-[11px] text-slate-400 bg-slate-950/40 px-2.5 py-1 rounded-lg border border-slate-800/60 w-fit">
            <Repeat className="w-3 h-3 text-brand-400 shrink-0" />
            <span className="text-slate-500">Resolved Query:</span>
            <span className="text-slate-300 font-medium truncate max-w-md">"{rewrittenQuestion}"</span>
          </div>
        )}

        {/* Message Content */}
        <div className="text-xs sm:text-sm text-slate-200 leading-relaxed whitespace-pre-wrap font-sans">
          {message.content}
        </div>

        {/* Citations section */}
        {isAssistant && message.citations && message.citations.length > 0 && (
          <div className="pt-2 border-t border-slate-800/60 mt-3">
            <span className="text-[10px] uppercase font-bold tracking-wider text-slate-400 block mb-1.5 flex items-center gap-1">
              <BookOpen className="w-3 h-3 text-brand-400" />
              Source Citations ({message.citations.length})
            </span>
            <div className="flex flex-wrap gap-2">
              {message.citations.map((c, i) => (
                <button
                  key={i}
                  onClick={() => onSelectCitation(c)}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700/60 text-slate-200 text-xs transition group text-left"
                >
                  <span className="w-4 h-4 rounded-full bg-brand-500/20 text-brand-400 font-bold text-[10px] flex items-center justify-center">
                    {c.n || i + 1}
                  </span>
                  <span className="font-medium truncate max-w-[150px]">{c.document_name}</span>
                  {c.page_number && (
                    <span className="text-[10px] text-slate-400">p.{c.page_number}</span>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Metrics footer (Timings & Tokens) */}
        {isAssistant && (timings || tokens) && (
          <div className="flex flex-wrap items-center gap-3 pt-2 text-[10px] text-slate-500 font-mono">
            {timings && (
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3 text-slate-400" />
                <span>
                  Total: {timings.total_ms}ms (Retrieval: {timings.retrieval_ms}ms, LLM: {timings.llm_ms}ms)
                </span>
              </span>
            )}
            {tokens && (
              <span className="flex items-center gap-1">
                <Zap className="w-3 h-3 text-amber-400" />
                <span>
                  Tokens: {tokens.input_tokens} in / {tokens.output_tokens} out
                </span>
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
