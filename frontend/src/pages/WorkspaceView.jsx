import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import api from '../services/api';
import DocumentsTab from '../components/documents/DocumentsTab';
import ChatTab from '../components/chat/ChatTab';
import MetricsTab from '../components/metrics/MetricsTab';

export default function WorkspaceView() {
  const { id } = useParams();
  const [workspace, setWorkspace] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState('documents'); // 'documents' | 'chat' | 'metrics'

  useEffect(() => {
    const fetchWorkspace = async () => {
      setLoading(true);
      setError('');
      try {
        const res = await api.get(`/api/workspaces/${id}`);
        setWorkspace(res.data);
        document.title = `${res.data.name} — DocuQite`;
      } catch (err) {
        const msg =
          err.response?.status === 404
            ? 'Workspace not found or you are not a member.'
            : 'Failed to load workspace details.';
        setError(msg);
      } finally {
        setLoading(false);
      }
    };

    fetchWorkspace();
  }, [id]);

  if (loading) {
    return (
      <div className="py-12 flex flex-col items-center justify-center">
        <div className="w-8 h-8 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mb-3"></div>
        <p className="text-sm text-slate-500 font-medium">Loading workspace...</p>
      </div>
    );
  }

  if (error || !workspace) {
    return (
      <div className="bg-white rounded-xl border border-red-200 p-8 text-center max-w-lg mx-auto shadow-sm">
        <div className="w-12 h-12 rounded-full bg-red-50 text-red-600 flex items-center justify-center mx-auto mb-3">
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <h2 className="text-base font-semibold text-slate-800">{error || 'Workspace Error'}</h2>
        <div className="mt-4">
          <Link
            to="/dashboard"
            className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg shadow-sm transition-colors"
          >
            ← Back to Workspaces
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Top Header & Breadcrumbs */}
      <div>
        <div className="flex items-center gap-2 text-xs text-slate-500 mb-1">
          <Link to="/dashboard" className="hover:text-indigo-600 transition-colors">
            Workspaces
          </Link>
          <span>/</span>
          <span className="text-slate-800 font-medium truncate">{workspace.name}</span>
        </div>

        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mt-2">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">{workspace.name}</h1>
            <p className="text-xs text-slate-400 font-mono mt-0.5">ID: {workspace.id}</p>
          </div>

          {/* Tab navigation pills */}
          <div className="flex bg-slate-200/80 p-1 rounded-xl shadow-inner self-start sm:self-auto">
            <button
              type="button"
              onClick={() => setActiveTab('documents')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all cursor-pointer ${
                activeTab === 'documents'
                  ? 'bg-white text-indigo-700 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              Documents
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('chat')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all cursor-pointer ${
                activeTab === 'chat'
                  ? 'bg-white text-indigo-700 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
              </svg>
              Chat
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('metrics')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all cursor-pointer ${
                activeTab === 'metrics'
                  ? 'bg-white text-indigo-700 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              Metrics
            </button>
          </div>
        </div>
      </div>

      {/* Tab Panels */}
      <div>
        {activeTab === 'documents' && <DocumentsTab workspaceId={workspace.id} />}
        {activeTab === 'chat' && <ChatTab workspaceId={workspace.id} />}
        {activeTab === 'metrics' && <MetricsTab workspaceId={workspace.id} />}
      </div>
    </div>
  );
}
