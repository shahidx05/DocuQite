import { useState, useEffect, useRef, useCallback } from 'react';
import api from '../../services/api';
import CitationChip from './CitationChip';

const MAX_QUESTION_CHARS = 500;

export default function ChatTab({ workspaceId }) {
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [question, setQuestion] = useState('');
  const [error, setError] = useState('');

  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, sending]);

  // Fetch all chat sessions for this workspace
  const fetchSessions = useCallback(async () => {
    try {
      const res = await api.get(`/api/workspaces/${workspaceId}/chats`);
      setSessions(res.data);
      if (res.data.length > 0 && !activeSessionId) {
        setActiveSessionId(res.data[0].id);
      }
    } catch (err) {
      setError('Failed to load chat sessions.');
    } finally {
      setLoadingSessions(false);
    }
  }, [workspaceId, activeSessionId]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  // Fetch messages when activeSessionId changes
  useEffect(() => {
    if (!activeSessionId) {
      setMessages([]);
      return;
    }

    const fetchMessages = async () => {
      setLoadingMessages(true);
      setError('');
      try {
        const res = await api.get(`/api/chats/${activeSessionId}`);
        setMessages(res.data.messages || []);
      } catch (err) {
        setError('Failed to load messages for this chat.');
      } finally {
        setLoadingMessages(false);
      }
    };

    fetchMessages();
  }, [activeSessionId]);

  // Create a new session
  const handleNewChat = async () => {
    setError('');
    try {
      const res = await api.post(`/api/workspaces/${workspaceId}/chats`, { title: 'New Chat' });
      setSessions((prev) => [res.data, ...prev]);
      setActiveSessionId(res.data.id);
      setMessages([]);
    } catch (err) {
      setError('Failed to create new chat session.');
    }
  };

  // Delete a session
  const handleDeleteSession = async (e, sessionId) => {
    e.stopPropagation();
    if (!window.confirm('Are you sure you want to delete this chat session?')) {
      return;
    }

    try {
      await api.delete(`/api/chats/${sessionId}`);
      const updated = sessions.filter((s) => s.id !== sessionId);
      setSessions(updated);
      if (activeSessionId === sessionId) {
        setActiveSessionId(updated.length > 0 ? updated[0].id : null);
      }
    } catch (err) {
      setError('Failed to delete chat session.');
    }
  };

  // Send message
  const handleSendMessage = async (e) => {
    if (e) e.preventDefault();
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || sending) return;

    if (trimmedQuestion.length > MAX_QUESTION_CHARS) {
      setError(`Question exceeds the ${MAX_QUESTION_CHARS} character limit.`);
      return;
    }

    setError('');
    setSending(true);

    let targetSessionId = activeSessionId;

    try {
      // 1. If no session exists, create one first
      if (!targetSessionId) {
        const newSessionRes = await api.post(`/api/workspaces/${workspaceId}/chats`, {
          title: trimmedQuestion.substring(0, 60),
        });
        targetSessionId = newSessionRes.data.id;
        setActiveSessionId(targetSessionId);
        setSessions((prev) => [newSessionRes.data, ...prev]);
      }

      // Optimistic user message in UI
      const optimisticUserMsg = {
        id: `temp-${Date.now()}`,
        role: 'user',
        content: trimmedQuestion,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, optimisticUserMsg]);
      setQuestion('');

      // 2. Post question to RAG pipeline
      const res = await api.post(`/api/chats/${targetSessionId}/messages`, {
        question: trimmedQuestion,
      });

      // Append assistant answer
      setMessages((prev) => [...prev, res.data]);

      // Update session title in sidebar if it was "New Chat"
      setSessions((prev) =>
        prev.map((s) =>
          s.id === targetSessionId && (s.title === 'New Chat' || !s.title)
            ? { ...s, title: trimmedQuestion.substring(0, 60) }
            : s
        )
      );
    } catch (err) {
      const msg =
        err.response?.data?.detail ||
        (typeof err.response?.data === 'string' ? err.response.data : null) ||
        'Failed to generate answer. Please try again.';
      setError(msg);
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="flex flex-col lg:flex-row h-[720px] bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      {/* Left Column: Chat Sessions List */}
      <div className="w-full lg:w-72 border-b lg:border-b-0 lg:border-r border-slate-200 flex flex-col bg-slate-50">
        <div className="p-3.5 border-b border-slate-200 flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Chat Sessions
          </span>
          <button
            type="button"
            onClick={handleNewChat}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors shadow-sm cursor-pointer"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New chat
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {loadingSessions ? (
            <div className="p-4 text-center text-xs text-slate-400">Loading sessions...</div>
          ) : sessions.length === 0 ? (
            <div className="p-6 text-center text-xs text-slate-400 italic">
              No chats yet.<br />Click "New chat" to begin.
            </div>
          ) : (
            sessions.map((s) => (
              <div
                key={s.id}
                onClick={() => setActiveSessionId(s.id)}
                className={`group flex items-center justify-between px-3 py-2.5 rounded-lg text-sm cursor-pointer transition-colors ${
                  activeSessionId === s.id
                    ? 'bg-indigo-50 text-indigo-900 font-medium'
                    : 'text-slate-700 hover:bg-slate-100'
                }`}
              >
                <div className="flex items-center gap-2 overflow-hidden">
                  <svg
                    className={`w-4 h-4 shrink-0 ${activeSessionId === s.id ? 'text-indigo-600' : 'text-slate-400'}`}
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
                    />
                  </svg>
                  <span className="truncate text-xs">{s.title || 'Untitled chat'}</span>
                </div>
                <button
                  type="button"
                  onClick={(e) => handleDeleteSession(e, s.id)}
                  title="Delete chat"
                  className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-red-600 rounded transition-opacity"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                    />
                  </svg>
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Right Column: Chat Messages & Input */}
      <div className="flex-1 flex flex-col bg-white overflow-hidden">
        {/* Error notification */}
        {error && (
          <div className="p-3 bg-red-50 border-b border-red-200 text-xs text-red-700 flex items-center justify-between shrink-0">
            <span>{error}</span>
            <button onClick={() => setError('')} className="text-red-500 font-bold ml-2">
              ✕
            </button>
          </div>
        )}

        {/* Message Stream */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-5 bg-slate-50/50">
          {loadingMessages ? (
            <div className="h-full flex items-center justify-center">
              <div className="flex flex-col items-center gap-2">
                <div className="w-6 h-6 border-3 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
                <p className="text-xs text-slate-400">Loading conversation...</p>
              </div>
            </div>
          ) : messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center p-6 text-slate-400">
              <div className="w-12 h-12 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center mb-3">
                <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                  />
                </svg>
              </div>
              <h3 className="text-sm font-semibold text-slate-700">Grounded Document Q&A</h3>
              <p className="text-xs max-w-sm mt-1 text-slate-500">
                Ask questions about your uploaded documents. Answers cite specific document sources and abstain when information is missing.
              </p>
            </div>
          ) : (
            messages.map((msg, idx) => (
              <div
                key={msg.id || idx}
                className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {msg.role === 'assistant' && (
                  <div className="w-8 h-8 rounded-lg bg-indigo-600 text-white font-bold flex items-center justify-center text-xs shadow-sm shrink-0 mt-0.5">
                    D
                  </div>
                )}

                <div
                  className={`max-w-xl rounded-2xl px-4 py-3 text-sm shadow-sm ${
                    msg.role === 'user'
                      ? 'bg-indigo-600 text-white rounded-br-none'
                      : 'bg-white border border-slate-200 text-slate-800 rounded-bl-none'
                  }`}
                >
                  {/* Abstained state styling */}
                  {msg.role === 'assistant' && msg.abstained ? (
                    <div className="space-y-2">
                      <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-50 text-amber-800 border border-amber-200">
                        <svg className="w-3.5 h-3.5 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                        Not found in documents
                      </div>
                      <p className="text-slate-600 italic whitespace-pre-wrap">{msg.content}</p>
                    </div>
                  ) : (
                    <div className="whitespace-pre-wrap leading-relaxed">{msg.content}</div>
                  )}

                  {/* Citation chips */}
                  {msg.role === 'assistant' && msg.citations && msg.citations.length > 0 && (
                    <div className="mt-3 pt-2.5 border-t border-slate-100">
                      <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                        Sources ({msg.citations.length})
                      </div>
                      <div>
                        {msg.citations.map((c, cIdx) => (
                          <CitationChip key={c.index || cIdx} citation={c} />
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))
          )}

          {/* Assistant loading indicator */}
          {sending && (
            <div className="flex gap-3 justify-start">
              <div className="w-8 h-8 rounded-lg bg-indigo-600 text-white font-bold flex items-center justify-center text-xs shadow-sm shrink-0">
                D
              </div>
              <div className="bg-white border border-slate-200 rounded-2xl rounded-bl-none px-4 py-3 shadow-sm text-sm text-slate-500 flex items-center gap-2">
                <div className="flex gap-1 items-center">
                  <span className="w-2 h-2 rounded-full bg-indigo-600 animate-bounce" style={{ animationDelay: '0ms' }}></span>
                  <span className="w-2 h-2 rounded-full bg-indigo-600 animate-bounce" style={{ animationDelay: '150ms' }}></span>
                  <span className="w-2 h-2 rounded-full bg-indigo-600 animate-bounce" style={{ animationDelay: '300ms' }}></span>
                </div>
                <span className="text-xs">Searching documents and generating answer...</span>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Form at Bottom */}
        <div className="p-4 border-t border-slate-200 bg-white">
          <form onSubmit={handleSendMessage} className="space-y-2">
            <div className="relative">
              <textarea
                ref={textareaRef}
                rows={2}
                maxLength={MAX_QUESTION_CHARS}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask a question about this workspace's documents... (Press Enter to send)"
                disabled={sending}
                className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-300 rounded-lg text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm resize-none"
              />
              <div className="flex items-center justify-between text-xs text-slate-400 mt-1 px-1">
                <span>
                  {question.length}/{MAX_QUESTION_CHARS} chars
                </span>
                <button
                  type="submit"
                  disabled={sending || !question.trim()}
                  className="inline-flex items-center gap-1.5 px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-40 transition-colors cursor-pointer text-xs"
                >
                  {sending ? 'Searching...' : 'Send'}
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                  </svg>
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
