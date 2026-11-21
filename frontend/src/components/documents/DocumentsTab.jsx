import { useState, useEffect, useRef, useCallback } from 'react';
import api from '../../services/api';

const ALLOWED_EXTENSIONS = ['pdf', 'docx', 'pptx'];
const MAX_FILE_BYTES = 25 * 1024 * 1024; // 25 MB

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

export default function DocumentsTab({ workspaceId }) {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [retryingId, setRetryingId] = useState(null);
  const [deletingId, setDeletingId] = useState(null);

  const fileInputRef = useRef(null);
  const pollTimerRef = useRef(null);

  // Fetch document list
  const fetchDocuments = useCallback(async (isPolling = false) => {
    try {
      const res = await api.get(`/api/workspaces/${workspaceId}/documents`);
      setDocuments(res.data);
      if (!isPolling) setLoading(false);
      return res.data;
    } catch (err) {
      if (!isPolling) {
        setError('Failed to fetch documents.');
        setLoading(false);
      }
      return null;
    }
  }, [workspaceId]);

  // Initial load
  useEffect(() => {
    fetchDocuments(false);
  }, [fetchDocuments]);

  // Polling logic: poll every 3 seconds ONLY while any document is not COMPLETED or FAILED
  useEffect(() => {
    const hasUnfinishedDocs = documents.some(
      (doc) => doc.status !== 'COMPLETED' && doc.status !== 'FAILED'
    );

    if (hasUnfinishedDocs) {
      if (!pollTimerRef.current) {
        pollTimerRef.current = setInterval(() => {
          fetchDocuments(true);
        }, 3000);
      }
    } else {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    }

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [documents, fetchDocuments]);

  // Upload handler
  const handleUpload = async (e) => {
    e.preventDefault();
    const file = fileInputRef.current?.files?.[0];
    if (!file) return;

    setError('');
    setSuccess('');

    // 1. Client-side extension check
    const ext = file.name.split('.').pop()?.toLowerCase();
    if (!ext || !ALLOWED_EXTENSIONS.includes(ext)) {
      setError(`Unsupported file type '.${ext || ''}'. Allowed: PDF, DOCX, PPTX.`);
      return;
    }

    // 2. Client-side size check (25 MB)
    if (file.size > MAX_FILE_BYTES) {
      setError(`File size (${formatBytes(file.size)}) exceeds the 25 MB limit.`);
      return;
    }

    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await api.post(`/api/workspaces/${workspaceId}/documents`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setSuccess(`Document "${res.data.filename}" uploaded successfully. Ingestion in progress...`);
      if (fileInputRef.current) fileInputRef.current.value = '';
      await fetchDocuments(false);
    } catch (err) {
      const msg =
        err.response?.data?.detail ||
        (typeof err.response?.data === 'string' ? err.response.data : null) ||
        'Upload failed. Please try again.';
      setError(msg);
    } finally {
      setUploading(false);
    }
  };

  // Retry handler
  const handleRetry = async (docId) => {
    setError('');
    setRetryingId(docId);
    try {
      await api.post(`/api/documents/${docId}/retry`);
      setSuccess('Ingestion retry started.');
      await fetchDocuments(false);
    } catch (err) {
      const msg =
        err.response?.data?.detail ||
        (typeof err.response?.data === 'string' ? err.response.data : null) ||
        'Failed to retry document ingestion.';
      setError(msg);
    } finally {
      setRetryingId(null);
    }
  };

  // Delete handler
  const handleDelete = async (docId, filename) => {
    if (!window.confirm(`Are you sure you want to delete "${filename}"? All vectors and indexed chunks will be removed.`)) {
      return;
    }

    setError('');
    setDeletingId(docId);
    try {
      await api.delete(`/api/documents/${docId}`);
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
      setSuccess(`Document "${filename}" deleted.`);
    } catch (err) {
      const msg =
        err.response?.data?.detail ||
        (typeof err.response?.data === 'string' ? err.response.data : null) ||
        'Failed to delete document.';
      setError(msg);
    } finally {
      setDeletingId(null);
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'PENDING':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">
            PENDING
          </span>
        );
      case 'PROCESSING':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200 animate-pulse">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-ping"></span>
            PROCESSING
          </span>
        );
      case 'CHUNKED':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-indigo-50 text-indigo-700 border border-indigo-200">
            CHUNKED
          </span>
        );
      case 'INDEXING':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-purple-50 text-purple-700 border border-purple-200 animate-pulse">
            <span className="w-1.5 h-1.5 rounded-full bg-purple-600 animate-ping"></span>
            INDEXING
          </span>
        );
      case 'COMPLETED':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
            <svg className="w-3.5 h-3.5 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
            </svg>
            COMPLETED
          </span>
        );
      case 'FAILED':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-50 text-red-700 border border-red-200">
            FAILED
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200">
            {status}
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Notifications */}
      {error && (
        <div className="p-4 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-red-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>{error}</span>
          </div>
          <button onClick={() => setError('')} className="text-red-500 hover:text-red-700 text-xs font-semibold">
            Dismiss
          </button>
        </div>
      )}

      {success && (
        <div className="p-4 rounded-lg bg-emerald-50 border border-emerald-200 text-sm text-emerald-700 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-emerald-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <span>{success}</span>
          </div>
          <button onClick={() => setSuccess('')} className="text-emerald-500 hover:text-emerald-700 text-xs font-semibold">
            Dismiss
          </button>
        </div>
      )}

      {/* Upload Card */}
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <h2 className="text-base font-semibold text-slate-900 mb-1">Upload Document</h2>
        <p className="text-xs text-slate-500 mb-4">
          Supported formats: PDF, DOCX, PPTX (max 25 MB). Files are parsed, cleaned, chunked, and embedded automatically.
        </p>

        <form onSubmit={handleUpload} className="flex flex-col sm:flex-row items-center gap-3">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.pptx"
            required
            disabled={uploading}
            className="block w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 cursor-pointer border border-slate-200 rounded-lg p-1 bg-slate-50"
          />
          <button
            type="submit"
            disabled={uploading}
            className="w-full sm:w-auto inline-flex justify-center items-center px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 transition-colors shrink-0"
          >
            {uploading ? (
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                <span>Uploading...</span>
              </div>
            ) : (
              'Upload'
            )}
          </button>
        </form>
      </div>

      {/* Documents List */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-slate-900">Workspace Documents</h2>
          <span className="text-xs font-medium text-slate-500 bg-slate-100 px-2.5 py-1 rounded-full border border-slate-200">
            {documents.length} Total
          </span>
        </div>

        {loading ? (
          <div className="bg-white rounded-xl border border-slate-200 p-8 text-center">
            <div className="w-6 h-6 border-3 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
            <p className="text-sm text-slate-500">Loading documents...</p>
          </div>
        ) : documents.length === 0 ? (
          <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
            <div className="w-12 h-12 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center mx-auto mb-3">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <h3 className="text-base font-semibold text-slate-800">No documents yet</h3>
            <p className="text-sm text-slate-500 mt-1 max-w-sm mx-auto">
              Upload your first PDF, DOCX, or PPTX above to make its knowledge searchable in this workspace.
            </p>
          </div>
        ) : (
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
                <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider text-xs font-semibold">
                  <tr>
                    <th scope="col" className="px-5 py-3">Document</th>
                    <th scope="col" className="px-4 py-3">Type</th>
                    <th scope="col" className="px-4 py-3">Size</th>
                    <th scope="col" className="px-4 py-3">Status</th>
                    <th scope="col" className="px-4 py-3">Chunks</th>
                    <th scope="col" className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white">
                  {documents.map((doc) => (
                    <tr key={doc.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="px-5 py-4">
                        <div className="font-medium text-slate-900 truncate max-w-xs sm:max-w-md" title={doc.filename}>
                          {doc.filename}
                        </div>
                        {doc.status === 'FAILED' && doc.error_message && (
                          <p className="text-xs text-red-600 mt-1 font-mono bg-red-50 p-1 rounded border border-red-100 max-w-md break-words">
                            Error: {doc.error_message}
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap">
                        <span className="uppercase text-xs font-bold text-slate-500 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                          {doc.file_type}
                        </span>
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap text-slate-600 text-xs">
                        {formatBytes(doc.file_size)}
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap">
                        {getStatusBadge(doc.status)}
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap text-slate-600 text-xs font-medium">
                        {doc.chunk_count != null ? doc.chunk_count : '—'}
                      </td>
                      <td className="px-4 py-4 whitespace-nowrap text-right space-x-2">
                        {doc.status === 'FAILED' && (
                          <button
                            type="button"
                            onClick={() => handleRetry(doc.id)}
                            disabled={retryingId === doc.id}
                            className="inline-flex items-center px-2.5 py-1 text-xs font-medium rounded text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 transition-colors disabled:opacity-50"
                          >
                            {retryingId === doc.id ? 'Retrying...' : 'Retry'}
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => handleDelete(doc.id, doc.filename)}
                          disabled={deletingId === doc.id}
                          className="inline-flex items-center px-2.5 py-1 text-xs font-medium rounded text-red-700 bg-red-50 hover:bg-red-100 border border-red-200 transition-colors disabled:opacity-50"
                          title="Delete document"
                        >
                          {deletingId === doc.id ? 'Deleting...' : 'Delete'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
