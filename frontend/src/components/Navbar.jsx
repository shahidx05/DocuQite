import React, { useState, useEffect } from 'react';
import { 
  Boxes, 
  FolderGit2, 
  Plus, 
  Users, 
  FileText, 
  MessageSquare, 
  Search, 
  Sparkles, 
  Activity, 
  LogOut, 
  LogIn, 
  User as UserIcon,
  ChevronDown,
  Trash2
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useWorkspace } from '../context/WorkspaceContext';
import { api } from '../api/client';

export function Navbar({ activeTab, setActiveTab, onOpenAuth, onOpenNewWorkspace, onOpenMembers }) {
  const { user, logout } = useAuth();
  const { workspaces, activeWorkspace, setActiveWorkspace, deleteWorkspace } = useWorkspace();
  const [healthStatus, setHealthStatus] = useState({ ok: null, checking: false });
  const [showWorkspaceMenu, setShowWorkspaceMenu] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);

  useEffect(() => {
    let isMounted = true;
    const checkHealth = async () => {
      try {
        const res = await api.getHealth();
        if (isMounted) setHealthStatus({ ok: res?.status === 'ok' || !!res, checking: false });
      } catch {
        if (isMounted) setHealthStatus({ ok: false, checking: false });
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  const navItems = [
    { id: 'chat', label: 'Chat Assistant', icon: MessageSquare },
    { id: 'documents', label: 'Documents', icon: FileText },
    { id: 'search', label: 'Search Explorer', icon: Search },
    { id: 'qa', label: 'Direct Q&A', icon: Sparkles },
  ];

  return (
    <header className="h-16 bg-slate-900/90 border-b border-slate-800 backdrop-blur sticky top-0 z-40 px-4 flex items-center justify-between">
      {/* Brand & Workspace */}
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-brand-600 to-indigo-500 flex items-center justify-center shadow-lg shadow-brand-500/20">
            <Boxes className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-lg tracking-tight text-white">DocuMind</span>
              <span className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded bg-brand-500/10 text-brand-400 border border-brand-500/20">
                Studio
              </span>
            </div>
            <p className="text-[11px] text-slate-400 leading-none">Intelligent Knowledge Workspace</p>
          </div>
        </div>

        {/* Workspace Switcher */}
        {user && (
          <div className="relative">
            <button
              onClick={() => setShowWorkspaceMenu(!showWorkspaceMenu)}
              className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-800/80 hover:bg-slate-800 text-slate-200 border border-slate-700/60 transition"
            >
              <FolderGit2 className="w-4 h-4 text-brand-400" />
              <span className="max-w-[140px] truncate">
                {activeWorkspace ? activeWorkspace.name : 'Select Workspace'}
              </span>
              <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
            </button>

            {showWorkspaceMenu && (
              <>
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setShowWorkspaceMenu(false)}
                />
                <div className="absolute left-0 mt-2 w-64 bg-slate-900 border border-slate-800 rounded-xl shadow-2xl p-1.5 z-20">
                  <div className="px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    Workspaces
                  </div>
                  <div className="max-h-56 overflow-y-auto space-y-0.5">
                    {workspaces.map((ws) => (
                      <div
                        key={ws.id}
                        className={`flex items-center justify-between px-2.5 py-2 rounded-lg text-xs cursor-pointer transition ${
                          activeWorkspace?.id === ws.id
                            ? 'bg-brand-500/15 text-brand-300 font-medium'
                            : 'text-slate-300 hover:bg-slate-800'
                        }`}
                        onClick={() => {
                          setActiveWorkspace(ws);
                          setShowWorkspaceMenu(false);
                        }}
                      >
                        <span className="truncate flex-1">{ws.name}</span>
                        {activeWorkspace?.id === ws.id && (
                          <span className="w-1.5 h-1.5 rounded-full bg-brand-400 ml-2" />
                        )}
                      </div>
                    ))}
                    {workspaces.length === 0 && (
                      <div className="px-3 py-3 text-center text-xs text-slate-500">
                        No workspaces yet
                      </div>
                    )}
                  </div>

                  <div className="pt-1.5 mt-1 border-t border-slate-800 flex flex-col gap-1">
                    <button
                      onClick={() => {
                        setShowWorkspaceMenu(false);
                        onOpenNewWorkspace();
                      }}
                      className="w-full flex items-center gap-2 px-2.5 py-2 text-xs font-medium text-brand-400 hover:bg-brand-500/10 rounded-lg transition"
                    >
                      <Plus className="w-4 h-4" />
                      Create New Workspace
                    </button>
                    {activeWorkspace && (
                      <button
                        onClick={() => {
                          setShowWorkspaceMenu(false);
                          onOpenMembers();
                        }}
                        className="w-full flex items-center gap-2 px-2.5 py-2 text-xs font-medium text-slate-300 hover:bg-slate-800 rounded-lg transition"
                      >
                        <Users className="w-4 h-4 text-slate-400" />
                        Manage Members
                      </button>
                    )}
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {/* Center Nav tabs */}
      {user && (
        <nav className="flex items-center gap-1 bg-slate-950/60 p-1 rounded-xl border border-slate-800">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition ${
                  isActive
                    ? 'bg-brand-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                <Icon className="w-4 h-4" />
                {item.label}
              </button>
            );
          })}
        </nav>
      )}

      {/* Right controls: Health & User */}
      <div className="flex items-center gap-3">
        {/* Health status */}
        <div
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium border ${
            healthStatus.ok === true
              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
              : healthStatus.ok === false
              ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
              : 'bg-slate-800 text-slate-400 border-slate-700'
          }`}
          title={
            healthStatus.ok === true
              ? 'Backend API Connected'
              : healthStatus.ok === false
              ? 'Backend API Unreachable'
              : 'Checking API...'
          }
        >
          <span
            className={`w-2 h-2 rounded-full ${
              healthStatus.ok === true
                ? 'bg-emerald-400 animate-pulse'
                : healthStatus.ok === false
                ? 'bg-amber-400'
                : 'bg-slate-500'
            }`}
          />
          <span className="hidden sm:inline">
            {healthStatus.ok === true ? 'Backend Online' : healthStatus.ok === false ? 'Offline' : 'Checking'}
          </span>
        </div>

        {/* User profile / Login */}
        {user ? (
          <div className="relative">
            <button
              onClick={() => setShowUserMenu(!showUserMenu)}
              className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg hover:bg-slate-800 text-xs text-slate-300 transition border border-transparent hover:border-slate-700"
            >
              <div className="w-6 h-6 rounded-full bg-slate-700 flex items-center justify-center text-[11px] font-bold text-slate-200">
                {user.name ? user.name[0].toUpperCase() : 'U'}
              </div>
              <span className="max-w-[100px] truncate">{user.name || user.email}</span>
              <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
            </button>

            {showUserMenu && (
              <>
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setShowUserMenu(false)}
                />
                <div className="absolute right-0 mt-2 w-52 bg-slate-900 border border-slate-800 rounded-xl shadow-2xl p-2 z-20">
                  <div className="px-2.5 py-2 border-b border-slate-800 mb-1">
                    <p className="text-xs font-semibold text-slate-200">{user.name}</p>
                    <p className="text-[11px] text-slate-400 truncate">{user.email}</p>
                    <span className="inline-block mt-1 text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                      {user.role || 'Member'}
                    </span>
                  </div>
                  <button
                    onClick={() => {
                      setShowUserMenu(false);
                      logout();
                    }}
                    className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-rose-400 hover:bg-rose-500/10 rounded-lg transition"
                  >
                    <LogOut className="w-4 h-4" />
                    Sign Out
                  </button>
                </div>
              </>
            )}
          </div>
        ) : (
          <button
            onClick={onOpenAuth}
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold shadow-md shadow-brand-500/20 transition"
          >
            <LogIn className="w-4 h-4" />
            Sign In / Register
          </button>
        )}
      </div>
    </header>
  );
}
