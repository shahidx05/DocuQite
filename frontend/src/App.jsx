import React, { useState } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { WorkspaceProvider, useWorkspace } from './context/WorkspaceContext';
import { Navbar } from './components/Navbar';
import { AuthModal } from './components/AuthModal';
import { CreateWorkspaceModal, WorkspaceMembersModal } from './components/WorkspaceModal';
import { DocumentsView } from './components/documents/DocumentsView';
import { ChatView } from './components/chat/ChatView';
import { SearchExplorer } from './components/search/SearchExplorer';
import { DirectQAView } from './components/qa/DirectQAView';
import { Boxes, Sparkles, Shield, Database, Search, ArrowRight } from 'lucide-react';

function MainContent() {
  const { user, loading } = useAuth();
  const { workspaces, activeWorkspace } = useWorkspace();
  const [activeTab, setActiveTab] = useState('chat');
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [newWorkspaceModalOpen, setNewWorkspaceModalOpen] = useState(false);
  const [membersModalOpen, setMembersModalOpen] = useState(false);

  if (loading) {
    return (
      <div className="h-screen w-full flex items-center justify-center bg-slate-950">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-brand-600 flex items-center justify-center text-white shadow-xl shadow-brand-500/20">
            <Boxes className="w-6 h-6 animate-pulse" />
          </div>
          <span className="text-xs text-slate-400 font-mono">Initializing DocuMind Studio...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col">
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onOpenAuth={() => setAuthModalOpen(true)}
        onOpenNewWorkspace={() => setNewWorkspaceModalOpen(true)}
        onOpenMembers={() => setMembersModalOpen(true)}
      />

      <div className="flex-1 overflow-y-auto">
        {!user ? (
          /* Unauthenticated Landing / Welcome Hero */
          <div className="max-w-4xl mx-auto px-6 py-16 text-center">
            <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-brand-500/10 border border-brand-500/20 text-brand-300 text-xs font-medium mb-6">
              <Sparkles className="w-3.5 h-3.5" />
              <span>Next-Gen Local-First Document Knowledge Engine</span>
            </div>

            <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-white max-w-2xl mx-auto leading-tight">
              Grounded Document Intelligence & Verification
            </h1>
            <p className="mt-4 text-sm sm:text-base text-slate-400 max-w-xl mx-auto leading-relaxed">
              Upload PDFs, Word documents, and presentations into isolated workspaces. Search with hybrid dense/sparse vector retrieval and converse with strictly cited answers.
            </p>

            <div className="mt-8 flex items-center justify-center gap-4">
              <button
                onClick={() => setAuthModalOpen(true)}
                className="px-6 py-3 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs sm:text-sm font-semibold shadow-lg shadow-brand-500/25 flex items-center gap-2 transition"
              >
                <span>Get Started / Sign In</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>

            {/* Feature highlights */}
            <div className="mt-16 grid grid-cols-1 sm:grid-cols-3 gap-6 text-left">
              <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800">
                <div className="w-9 h-9 rounded-xl bg-brand-500/10 text-brand-400 flex items-center justify-center mb-3">
                  <Database className="w-5 h-5" />
                </div>
                <h3 className="text-sm font-semibold text-white">Hybrid Retrieval</h3>
                <p className="text-xs text-slate-400 mt-1">
                  Combines BAAI dense embeddings and BM25 sparse vectors in Qdrant with Reciprocal Rank Fusion.
                </p>
              </div>

              <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800">
                <div className="w-9 h-9 rounded-xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center mb-3">
                  <Shield className="w-5 h-5" />
                </div>
                <h3 className="text-sm font-semibold text-white">Strict Citation & Abstention</h3>
                <p className="text-xs text-slate-400 mt-1">
                  Every answer directly references source document passages. The model abstains when confidence is insufficient.
                </p>
              </div>

              <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800">
                <div className="w-9 h-9 rounded-xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center mb-3">
                  <Search className="w-5 h-5" />
                </div>
                <h3 className="text-sm font-semibold text-white">Cross-Encoder Reranking</h3>
                <p className="text-xs text-slate-400 mt-1">
                  Re-scores candidate chunks with Xenova cross-encoders to ensure maximum relevance before generation.
                </p>
              </div>
            </div>
          </div>
        ) : (
          /* Authenticated Views */
          <div>
            {workspaces.length === 0 ? (
              <div className="max-w-md mx-auto my-20 p-8 text-center bg-slate-900 border border-slate-800 rounded-3xl shadow-xl">
                <div className="w-12 h-12 rounded-2xl bg-brand-500/10 text-brand-400 flex items-center justify-center mx-auto mb-4">
                  <Boxes className="w-6 h-6" />
                </div>
                <h3 className="text-base font-bold text-white">Create Your First Workspace</h3>
                <p className="text-xs text-slate-400 mt-1.5 mb-6">
                  Workspaces keep documents, chunk vectors, and conversation histories completely isolated.
                </p>
                <button
                  onClick={() => setNewWorkspaceModalOpen(true)}
                  className="px-5 py-2.5 bg-brand-600 hover:bg-brand-500 text-white rounded-xl text-xs font-semibold shadow-md shadow-brand-500/20 transition inline-flex items-center gap-2"
                >
                  Create Workspace
                </button>
              </div>
            ) : (
              <>
                {activeTab === 'chat' && <ChatView />}
                {activeTab === 'documents' && <DocumentsView />}
                {activeTab === 'search' && <SearchExplorer />}
                {activeTab === 'qa' && <DirectQAView />}
              </>
            )}
          </div>
        )}
      </div>

      {/* Modals */}
      <AuthModal isOpen={authModalOpen} onClose={() => setAuthModalOpen(false)} />
      <CreateWorkspaceModal
        isOpen={newWorkspaceModalOpen}
        onClose={() => setNewWorkspaceModalOpen(false)}
      />
      <WorkspaceMembersModal
        isOpen={membersModalOpen}
        onClose={() => setMembersModalOpen(false)}
      />
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <WorkspaceProvider>
        <MainContent />
      </WorkspaceProvider>
    </AuthProvider>
  );
}
