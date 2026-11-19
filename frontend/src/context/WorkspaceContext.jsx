import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import { useAuth } from './AuthContext';

const WorkspaceContext = createContext(null);

export function WorkspaceProvider({ children }) {
  const { user } = useAuth();
  const [workspaces, setWorkspaces] = useState([]);
  const [activeWorkspace, setActiveWorkspace] = useState(null);
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchWorkspaces = useCallback(async () => {
    if (!user) {
      setWorkspaces([]);
      setActiveWorkspace(null);
      return;
    }

    setLoading(true);
    try {
      const data = await api.listWorkspaces();
      setWorkspaces(data || []);
      if (data && data.length > 0) {
        // Keep active workspace if still valid, or default to first
        setActiveWorkspace((prev) => {
          if (prev && data.some((ws) => ws.id === prev.id)) {
            return data.find((ws) => ws.id === prev.id);
          }
          return data[0];
        });
      } else {
        setActiveWorkspace(null);
      }
      setError(null);
    } catch (err) {
      console.error('Failed to list workspaces:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    fetchWorkspaces();
  }, [fetchWorkspaces]);

  const fetchMembers = useCallback(async () => {
    if (!activeWorkspace) {
      setMembers([]);
      return;
    }
    try {
      const data = await api.listWorkspaceMembers(activeWorkspace.id);
      setMembers(data || []);
    } catch (err) {
      console.warn('Could not fetch workspace members:', err);
    }
  }, [activeWorkspace]);

  useEffect(() => {
    fetchMembers();
  }, [fetchMembers]);

  const createWorkspace = async (name) => {
    try {
      const created = await api.createWorkspace(name);
      await fetchWorkspaces();
      setActiveWorkspace(created);
      return created;
    } catch (err) {
      throw err;
    }
  };

  const deleteWorkspace = async (workspaceId) => {
    try {
      await api.deleteWorkspace(workspaceId);
      await fetchWorkspaces();
    } catch (err) {
      throw err;
    }
  };

  const addMember = async (email) => {
    if (!activeWorkspace) return;
    try {
      const member = await api.addWorkspaceMember(activeWorkspace.id, email);
      await fetchMembers();
      return member;
    } catch (err) {
      throw err;
    }
  };

  const removeMember = async (userId) => {
    if (!activeWorkspace) return;
    try {
      await api.removeWorkspaceMember(activeWorkspace.id, userId);
      await fetchMembers();
    } catch (err) {
      throw err;
    }
  };

  return (
    <WorkspaceContext.Provider
      value={{
        workspaces,
        activeWorkspace,
        setActiveWorkspace,
        loading,
        error,
        members,
        fetchWorkspaces,
        createWorkspace,
        deleteWorkspace,
        fetchMembers,
        addMember,
        removeMember,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  const context = useContext(WorkspaceContext);
  if (!context) {
    throw new Error('useWorkspace must be used within a WorkspaceProvider');
  }
  return context;
}
