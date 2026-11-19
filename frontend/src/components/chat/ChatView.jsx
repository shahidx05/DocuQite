import React, { useState, useEffect, useRef, useCallback } from 'react';
import { 
  Plus, 
  MessageSquare, 
  Trash2, 
  Send, 
  Sparkles, 
  Bot, 
  AlertCircle,
  HelpCircle
} from 'lucide-react';
import { api } from '../../api/client';
import { useWorkspace } from '../../context/WorkspaceContext';
import { ChatMessage } from './ChatMessage';
import { CitationModal } from './CitationModal';

export function ChatView() {
  const { activeWorkspace } = useWorkspace();
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [inputQuestion, setInputQuestion] = useState('');
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const [selectedCitation, setSelectedCitation] = useState(null);

  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // Fetch sessions for active workspace
  const fetchSessions = useCallback(async () => {
    if (!activeWorkspace) {
      setSessions([]);
      setActiveSessionId(null);
      return;
    }
    setLoadingSessions(true);
    try {
      const data = await api.listChats(activeWorkspace.id);
      setSessions(data || []);
      if (data && data.length > 0) {
        setActiveSessionId((prev) => (prev && data.some((s) => s.id === prev) ? prev : data[0].id));
      } else {
        setActiveSessionId(null);
        setMessages([]);
      }
    } catch (err) {
      console.warn('Failed to load chats:', err);
    } finally {
      setLoadingSessions(false);
    }
  }, [activeWorkspace]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  // Fetch messages for active session
  const fetchMessages = useCallback(async (sessionId) => {
    if (!sessionId) {
      setMessages([]);
      return;
    }
    setLoadingMessages(true);
    try {
      const sessionDetail = await api.getChat(sessionId);
      setMessages(sessionDetail?.messages || []);
      setError(null);
    } catch (err) {
      setError(err.detail || err.message || 'Failed to load conversation');
    } finally {
      setLoadingMessages(false);
    }
  }, []);

  useEffect(() => {
    if (activeSessionId) {
      fetchMessages(activeSessionId);
    }
  }, [activeSessionId, fetchMessages]);

  useEffect(() => {
    scrollToBottom();
  }, [messages, sending]);

  const handleCreateNewSession = async () => {
    if (!activeWorkspace) return;
    try {
      const newSession = await api.createChat(activeWorkspace.id, 'New Conversation');
      await fetchSessions();
      setActiveSessionId(newSession.id);
    } catch (err) {
      alert(err.detail || err.message || 'Failed to create chat session');
    }
  };

  const handleDeleteSession = async (e, sessionId) => {
    e.stopPropagation();
    if (!confirm('Delete this conversation?')) return;
    try {
      await api.deleteChat(sessionId);
      if (activeSessionId === sessionId) {
        setActiveSessionId(null);
      }
      await fetchSessions();
    } catch (err) {
      alert(err.detail || err.message || 'Failed to delete chat');
    }
  };

  const handleSendMessage = async (e) => {
    if (e) e.preventDefault();
    const q = inputQuestion.trim();
    if (!q || sending) return;

    if (!activeWorkspace) {
      alert('Please select a workspace first');
      return;
    }

    let currentSessionId = activeSessionId;

    // If no active session, create one first
    if (!currentSessionId) {
      try {
        const newSession = await api.createChat(activeWorkspace.id, q.slice(0, 30));
        currentSessionId = newSession.id;
        setActiveSessionId(currentSessionId);
        await fetchSessions();
      } catch (err) {
        setError(err.detail || err.message || 'Failed to create chat session');
        return;
      }
    }

    // Optimistically add user message to list
    const tempUserMsg = {
      id: 'temp-' + Date.now(),
      role: 'user',
      content: q,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);
    setInputQuestion('');
    setSending(true);
    setError(null);

    try {
      const assistantMsg = await api.postChatMessage(currentSessionId, q);
      // Replace with refreshed state or append
      setMessages((prev) => [...prev, assistantMsg]);
      // Update session title in session list
      fetchSessions();
    } catch (err) {
      setError(err.detail || err.message || 'Failed to generate answer');
    } finally {
      setSending(false);
    }
  };

  const samplePrompts = [
    'What are the key findings or takeaways across the documents?',
    'Explain the main architecture and methodologies described.',
    'List all references and procedures mentioned in the uploaded files.',
  ];

  if (!activeWorkspace) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-center h-[calc(100vh-4rem)]">
        <MessageSquare className="w-12 h-12 text-slate-600 mb-3" />
        <h3 className="text-base font-semibold text-slate-300">No Workspace Selected</h3>
        <p className="text-xs text-slate-500 mt-1 max-w-sm">
          Select or create a workspace using the header dropdown to start a grounded conversation.
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
      {/* Session sidebar */}
      <aside className="w-64 bg-slate-900 border-r border-slate-800 flex flex-col shrink-0">
        <div className="p-3 border-b border-slate-800">
          <button
            onClick={handleCreateNewSession}
            className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold shadow-md shadow-brand-500/20 transition"
          >
            <Plus className="w-4 h-4" />
            New Conversation
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {loadingSessions ? (
            <div className="p-4 text-center">
              <span className="w-4 h-4 border-2 border-slate-600 border-t-brand-400 rounded-full animate-spin inline-block" />
            </div>
          ) : sessions.length === 0 ? (
            <div className="text-center p-6 text-slate-500 text-xs">
              No conversations yet
            </div>
          ) : (
            sessions.map((s) => (
              <div
                key={s.id}
                onClick={() => setActiveSessionId(s.id)}
                className={`group flex items-center justify-between px-3 py-2.5 rounded-xl text-xs cursor-pointer transition ${
                  activeSessionId === s.id
                    ? 'bg-slate-800 text-brand-300 font-medium border border-slate-700/60'
                    : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                }`}
              >
                <div className="flex items-center gap-2 truncate">
                  <MessageSquare className="w-3.5 h-3.5 shrink-0" />
                  <span className="truncate">{s.title || 'Untitled Chat'}</span>
                </div>
                <button
                  onClick={(e) => handleDeleteSession(e, s.id)}
                  className="opacity-0 group-hover:opacity-100 p-1 text-slate-500 hover:text-rose-400 rounded transition"
                  title="Delete chat"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))
          )}
        </div>
      </aside>

      {/* Main chat window */}
      <main className="flex-1 flex flex-col bg-slate-950 overflow-hidden">
        {/* Messages Stream */}
        <div className="flex-1 overflow-y-auto divide-y divide-slate-800/30">
          {loadingMessages ? (
            <div className="flex items-center justify-center h-full">
              <span className="w-8 h-8 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin" />
            </div>
          ) : messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center p-6 text-center max-w-lg mx-auto">
              <div className="w-12 h-12 rounded-2xl bg-brand-500/10 text-brand-400 flex items-center justify-center mb-3">
                <Sparkles className="w-6 h-6" />
              </div>
              <h3 className="text-base font-bold text-slate-200">Grounded Document Assistant</h3>
              <p className="text-xs text-slate-400 mt-1">
                Ask any question about your indexed documents. Answers are strictly grounded in retrieved passages with verifiable citations.
              </p>

              <div className="mt-6 w-full space-y-2 text-left">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 block">
                  Suggested Prompts
                </span>
                {samplePrompts.map((prompt, i) => (
                  <button
                    key={i}
                    onClick={() => {
                      setInputQuestion(prompt);
                    }}
                    className="w-full text-left p-2.5 rounded-xl bg-slate-900 hover:bg-slate-800/80 border border-slate-800 text-xs text-slate-300 transition flex items-center justify-between group"
                  >
                    <span>{prompt}</span>
                    <span className="text-brand-400 opacity-0 group-hover:opacity-100 transition">→</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((msg) => (
              <ChatMessage
                key={msg.id}
                message={msg}
                onSelectCitation={(citation) => setSelectedCitation(citation)}
              />
            ))
          )}

          {sending && (
            <div className="py-4 px-6 flex gap-4 bg-slate-900/40 border-y border-slate-800/40">
              <div className="w-8 h-8 rounded-xl bg-brand-600 flex items-center justify-center text-white shrink-0">
                <Bot className="w-4 h-4" />
              </div>
              <div className="flex items-center gap-3 text-xs text-slate-400">
                <span className="w-4 h-4 border-2 border-brand-400/30 border-t-brand-400 rounded-full animate-spin" />
                <span>Searching knowledge base, reranking passages, and generating grounded response...</span>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Error notification */}
        {error && (
          <div className="px-6 py-2 bg-rose-500/10 border-t border-rose-500/20 text-rose-300 text-xs flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4" />
              <span>{error}</span>
            </div>
            <button onClick={() => setError(null)} className="text-rose-400 hover:text-white">
              ✕
            </button>
          </div>
        )}

        {/* Input box */}
        <div className="p-4 bg-slate-900/90 border-t border-slate-800">
          <form onSubmit={handleSendMessage} className="max-w-4xl mx-auto relative flex items-center">
            <textarea
              rows={1}
              value={inputQuestion}
              onChange={(e) => setInputQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSendMessage();
                }
              }}
              placeholder="Ask a question about the workspace documents (Press Enter to send)..."
              className="w-full bg-slate-950/80 border border-slate-800 rounded-2xl pl-4 pr-12 py-3 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 resize-none max-h-32"
            />
            <button
              type="submit"
              disabled={sending || !inputQuestion.trim()}
              className="absolute right-2 p-2 rounded-xl bg-brand-600 hover:bg-brand-500 disabled:opacity-30 text-white transition shadow-sm"
              title="Send question"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
          <p className="text-[10px] text-center text-slate-500 mt-2">
            Non-agentic local-first RAG. Generated responses include direct citations to source text.
          </p>
        </div>
      </main>

      {/* Citation Modal */}
      <CitationModal
        isOpen={!!selectedCitation}
        citation={selectedCitation}
        onClose={() => setSelectedCitation(null)}
      />
    </div>
  );
}
