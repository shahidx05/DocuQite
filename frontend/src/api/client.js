// Centralized API client for all backend endpoints

const API_BASE = '/api';

export const getAuthToken = () => localStorage.getItem('auth_token');
export const setAuthToken = (token) => {
  if (token) {
    localStorage.setItem('auth_token', token);
  } else {
    localStorage.removeItem('auth_token');
  }
};

export async function apiFetch(endpoint, options = {}) {
  const token = getAuthToken();
  const headers = {
    ...(options.headers || {}),
  };

  // Add auth token if available
  if (token && !headers['Authorization']) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // If body is NOT FormData, set JSON content-type
  if (!(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    // If unauthorized, clear token and notify
    if (!endpoint.includes('/auth/login') && !endpoint.includes('/auth/register')) {
      setAuthToken(null);
      window.dispatchEvent(new Event('auth:unauthorized'));
    }
  }

  if (response.status === 204) {
    return null;
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const errorMsg = data?.detail || `Request failed with status ${response.status}`;
    const error = new Error(errorMsg);
    error.status = response.status;
    error.detail = data?.detail;
    throw error;
  }

  return data;
}

// -------------------------------------------------------------
// Endpoints
// -------------------------------------------------------------

export const api = {
  // Health
  getHealth: () => apiFetch('/health'),

  // Auth
  register: (name, email, password) =>
    apiFetch('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ name, email, password }),
    }),
  login: async (email, password) => {
    const res = await apiFetch('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    if (res?.access_token) {
      setAuthToken(res.access_token);
    }
    return res;
  },
  getMe: () => apiFetch('/auth/me'),

  // Workspaces
  listWorkspaces: () => apiFetch('/workspaces'),
  createWorkspace: (name) =>
    apiFetch('/workspaces', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  getWorkspace: (id) => apiFetch(`/workspaces/${id}`),
  deleteWorkspace: (id) =>
    apiFetch(`/workspaces/${id}`, {
      method: 'DELETE',
    }),
  listWorkspaceMembers: (workspaceId) =>
    apiFetch(`/workspaces/${workspaceId}/members`),
  addWorkspaceMember: (workspaceId, email) =>
    apiFetch(`/workspaces/${workspaceId}/members`, {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),
  removeWorkspaceMember: (workspaceId, userId) =>
    apiFetch(`/workspaces/${workspaceId}/members/${userId}`, {
      method: 'DELETE',
    }),

  // Documents
  listDocuments: (workspaceId) =>
    apiFetch(`/workspaces/${workspaceId}/documents`),
  uploadDocument: (workspaceId, file) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiFetch(`/workspaces/${workspaceId}/documents`, {
      method: 'POST',
      body: formData,
    });
  },
  getDocument: (documentId) => apiFetch(`/documents/${documentId}`),
  listChunks: (documentId, offset = 0, limit = 20) =>
    apiFetch(`/documents/${documentId}/chunks?offset=${offset}&limit=${limit}`),
  deleteDocument: (documentId) =>
    apiFetch(`/documents/${documentId}`, {
      method: 'DELETE',
    }),
  retryDocument: (documentId) =>
    apiFetch(`/documents/${documentId}/retry`, {
      method: 'POST',
    }),

  // Search
  searchWorkspace: (workspaceId, { q, mode = 'hybrid', topK = 10, rerank = true }) => {
    const params = new URLSearchParams({
      q,
      mode,
      top_k: topK.toString(),
      rerank: rerank.toString(),
    });
    return apiFetch(`/workspaces/${workspaceId}/search?${params.toString()}`);
  },

  // Direct Grounded Q&A
  askWorkspace: (workspaceId, question) =>
    apiFetch(`/workspaces/${workspaceId}/ask`, {
      method: 'POST',
      body: JSON.stringify({ question }),
    }),

  // Chats
  listChats: (workspaceId) =>
    apiFetch(`/workspaces/${workspaceId}/chats`),
  createChat: (workspaceId, title = 'New Chat') =>
    apiFetch(`/workspaces/${workspaceId}/chats`, {
      method: 'POST',
      body: JSON.stringify({ title }),
    }),
  getChat: (chatId) => apiFetch(`/chats/${chatId}`),
  deleteChat: (chatId) =>
    apiFetch(`/chats/${chatId}`, {
      method: 'DELETE',
    }),
  postChatMessage: (chatId, question) =>
    apiFetch(`/chats/${chatId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ question }),
    }),
};
