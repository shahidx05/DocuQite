import React, { useState } from 'react';
import { X, FolderPlus, Users, UserPlus, Trash2, Shield, AlertCircle, Check } from 'lucide-react';
import { useWorkspace } from '../context/WorkspaceContext';
import { useAuth } from '../context/AuthContext';

export function CreateWorkspaceModal({ isOpen, onClose }) {
  const { createWorkspace } = useWorkspace();
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    setError(null);
    setLoading(true);

    try {
      await createWorkspace(name.trim());
      setName('');
      onClose();
    } catch (err) {
      setError(err.detail || err.message || 'Failed to create workspace');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
      <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-6">
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-brand-500/10 text-brand-400">
              <FolderPlus className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">Create New Workspace</h3>
              <p className="text-xs text-slate-400">Isolate documents, search, and conversations</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg text-slate-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        {error && (
          <div className="mt-4 p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              Workspace Name
            </label>
            <input
              type="text"
              required
              autoFocus
              placeholder="e.g. Legal Research, Engineering Docs"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-slate-950/70 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500"
            />
          </div>

          <div className="flex items-center justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-2 text-xs font-medium text-slate-400 hover:text-white hover:bg-slate-800 rounded-xl transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !name.trim()}
              className="px-4 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white rounded-xl text-xs font-semibold shadow-md shadow-brand-500/20 transition flex items-center gap-2"
            >
              {loading ? 'Creating...' : 'Create Workspace'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function WorkspaceMembersModal({ isOpen, onClose }) {
  const { user } = useAuth();
  const { activeWorkspace, members, addMember, removeMember, deleteWorkspace } = useWorkspace();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  if (!isOpen || !activeWorkspace) return null;

  const isOwner = activeWorkspace.owner_id === user?.id;

  const handleAddMember = async (e) => {
    e.preventDefault();
    if (!email.trim()) return;
    setError(null);
    setSuccess(null);
    setLoading(true);

    try {
      await addMember(email.trim());
      setSuccess(`User "${email}" added to workspace`);
      setEmail('');
    } catch (err) {
      setError(err.detail || err.message || 'Failed to add member');
    } finally {
      setLoading(false);
    }
  };

  const handleRemove = async (userId) => {
    if (!confirm('Are you sure you want to remove this member?')) return;
    try {
      await removeMember(userId);
    } catch (err) {
      alert(err.detail || err.message || 'Failed to remove member');
    }
  };

  const handleDeleteWs = async () => {
    try {
      await deleteWorkspace(activeWorkspace.id);
      onClose();
    } catch (err) {
      alert(err.detail || err.message || 'Failed to delete workspace');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
      <div className="w-full max-w-lg bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-6">
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-brand-500/10 text-brand-400">
              <Users className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">Workspace Members</h3>
              <p className="text-xs text-slate-400">{activeWorkspace.name}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg text-slate-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        {error && (
          <div className="mt-3 p-2.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}
        {success && (
          <div className="mt-3 p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-xs flex items-center gap-2">
            <Check className="w-4 h-4 shrink-0" />
            <span>{success}</span>
          </div>
        )}

        {/* Add member form (Owner only) */}
        {isOwner && (
          <form onSubmit={handleAddMember} className="mt-4 flex gap-2">
            <input
              type="email"
              required
              placeholder="Enter member's registered email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="flex-1 bg-slate-950/70 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-brand-500"
            />
            <button
              type="submit"
              disabled={loading || !email.trim()}
              className="px-3.5 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white rounded-xl text-xs font-semibold flex items-center gap-1.5 transition"
            >
              <UserPlus className="w-4 h-4" />
              Add
            </button>
          </form>
        )}

        {/* Members list */}
        <div className="mt-4">
          <label className="text-xs font-semibold uppercase tracking-wider text-slate-400 block mb-2">
            Current Members ({members.length})
          </label>
          <div className="max-h-52 overflow-y-auto space-y-1.5">
            {members.map((m) => (
              <div
                key={m.user_id}
                className="flex items-center justify-between p-2.5 rounded-xl bg-slate-950/40 border border-slate-800/80 text-xs"
              >
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-full bg-slate-800 flex items-center justify-center font-bold text-slate-300 text-[11px]">
                    {m.user_id.slice(0, 2).toUpperCase()}
                  </div>
                  <div>
                    <span className="font-mono text-slate-300 text-[11px] block">{m.user_id}</span>
                    <span className="text-[10px] text-slate-500 flex items-center gap-1">
                      {m.role === 'owner' ? (
                        <>
                          <Shield className="w-3 h-3 text-brand-400" />
                          <span className="text-brand-400 font-semibold">Owner</span>
                        </>
                      ) : (
                        <span>Member</span>
                      )}
                    </span>
                  </div>
                </div>

                {isOwner && m.role !== 'owner' && (
                  <button
                    onClick={() => handleRemove(m.user_id)}
                    className="p-1 text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition"
                    title="Remove member"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Workspace Danger Zone (Owner only) */}
        {isOwner && (
          <div className="mt-6 pt-4 border-t border-slate-800 flex items-center justify-between">
            {!deleteConfirm ? (
              <button
                type="button"
                onClick={() => setDeleteConfirm(true)}
                className="text-xs text-rose-400 hover:text-rose-300 flex items-center gap-1.5 transition"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Delete Workspace
              </button>
            ) : (
              <div className="flex items-center gap-2">
                <span className="text-xs text-rose-400">Permanently delete workspace?</span>
                <button
                  onClick={handleDeleteWs}
                  className="px-2.5 py-1 text-xs bg-rose-600 hover:bg-rose-500 text-white font-semibold rounded-lg shadow transition"
                >
                  Confirm Delete
                </button>
                <button
                  onClick={() => setDeleteConfirm(false)}
                  className="px-2.5 py-1 text-xs text-slate-400 hover:text-white"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
