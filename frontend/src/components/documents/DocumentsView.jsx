import React, { useState, useEffect, useCallback } from 'react';
import { 
  FileText, 
  Trash2, 
  RotateCw, 
  Layers, 
  AlertCircle, 
  Clock, 
  CheckCircle, 
  XCircle, 
  FileCode,
  HardDrive
} from 'lucide-react';
import { api } from '../../api/client';
import { useWorkspace } from '../../context/WorkspaceContext';
import { UploadCard } from './UploadCard';
import { ChunkModal } from './ChunkModal';

export function DocumentsView() {
  const { activeWorkspace } = useWorkspace();
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedDocForChunks, setSelectedDocForChunks] = useState(null);

  const fetchDocuments = useCallback(async (quiet = false) => {
    if (!activeWorkspace) {
      setDocuments([]);
      return;
    }
    if (!quiet) setLoading(true);
    try {
      const data = await api.listDocuments(activeWorkspace.id);
      setDocuments(data || []);
      setError(null);
    } catch (err) {
      if (!quiet) setError(err.detail || err.message || 'Failed to load documents');
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [activeWorkspace]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  // Polling if any document is in progress
  useEffect(() => {
    const hasPending = documents.some(
      (d) => d.status === 'PENDING' || d.status === 'PROCESSING'
    );
    if (!hasPending) return;

    const interval = setInterval(() => {
      fetchDocuments(true);
    }, 3000);

    return () => clearInterval(interval);
  }, [documents, fetchDocuments]);

  const handleDelete = async (docId) => {
    if (!confirm('Are you sure you want to delete this document and all its chunks?')) return;
    try {
      await api.deleteDocument(docId);
      fetchDocuments(true);
    } catch (err) {
      alert(err.detail || err.message || 'Failed to delete document');
    }
  };

  const handleRetry = async (docId) => {
    try {
      await api.retryDocument(docId);
      fetchDocuments(true);
    } catch (err) {
      alert(err.detail || err.message || 'Failed to retry ingestion');
    }
  };

  const formatBytes = (bytes) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const getStatusBadge = (status, errorMsg) => {
    switch (status) {
      case 'READY':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <CheckCircle className="w-3.5 h-3.5" />
            Ready
          </span>
        );
      case 'PROCESSING':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium bg-brand-500/10 text-brand-400 border border-brand-500/20">
            <RotateCw className="w-3.5 h-3.5 animate-spin" />
            Processing
          </span>
        );
      case 'PENDING':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <Clock className="w-3.5 h-3.5" />
            Pending
          </span>
        );
      case 'FAILED':
        return (
          <span
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium bg-rose-500/10 text-rose-400 border border-rose-500/20 cursor-help"
            title={errorMsg || 'Ingestion failed'}
          >
            <XCircle className="w-3.5 h-3.5" />
            Failed
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium bg-slate-800 text-slate-400">
            {status}
          </span>
        );
    }
  };

  if (!activeWorkspace) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-center">
        <HardDrive className="w-12 h-12 text-slate-600 mb-3" />
        <h3 className="text-base font-semibold text-slate-300">No Workspace Selected</h3>
        <p className="text-xs text-slate-500 mt-1 max-w-sm">
          Select or create a workspace using the dropdown above to view and upload documents.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-6">
      {/* Upload card */}
      <UploadCard onUploaded={() => fetchDocuments(true)} />

      {/* Documents table / list */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-sm">
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-white">Workspace Documents</h3>
            <p className="text-xs text-slate-400">
              {documents.length} document{documents.length === 1 ? '' : 's'} indexed in this workspace
            </p>
          </div>
          <button
            onClick={() => fetchDocuments()}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-400 hover:text-white bg-slate-800/80 hover:bg-slate-800 rounded-lg transition"
          >
            <RotateCw className="w-3.5 h-3.5" />
            Refresh
          </button>
        </div>

        {error && (
          <div className="p-4 bg-rose-500/10 border-b border-rose-500/20 text-rose-300 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4" />
            <span>{error}</span>
          </div>
        )}

        {loading ? (
          <div className="p-12 flex items-center justify-center">
            <span className="w-8 h-8 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin" />
          </div>
        ) : documents.length === 0 ? (
          <div className="p-12 text-center text-slate-500 text-xs">
            No documents uploaded yet in this workspace.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/60 border-b border-slate-800/80 text-slate-400 font-semibold uppercase text-[10px] tracking-wider">
                <tr>
                  <th className="px-6 py-3">Document Name</th>
                  <th className="px-6 py-3">Status</th>
                  <th className="px-6 py-3">Type / Size</th>
                  <th className="px-6 py-3">Pages / Chunks</th>
                  <th className="px-6 py-3">Uploaded At</th>
                  <th className="px-6 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {documents.map((doc) => (
                  <tr key={doc.id} className="hover:bg-slate-800/30 transition">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-slate-800 text-slate-300">
                          <FileText className="w-4 h-4 text-brand-400" />
                        </div>
                        <div>
                          <p className="font-medium text-slate-200">{doc.filename}</p>
                          <p className="font-mono text-[10px] text-slate-500">{doc.id}</p>
                        </div>
                      </div>
                    </td>

                    <td className="px-6 py-4">
                      {getStatusBadge(doc.status, doc.error_message)}
                      {doc.error_message && (
                        <p className="text-[10px] text-rose-400 mt-1 max-w-xs truncate" title={doc.error_message}>
                          {doc.error_message}
                        </p>
                      )}
                    </td>

                    <td className="px-6 py-4">
                      <span className="uppercase font-mono text-[11px] font-semibold text-slate-300 px-1.5 py-0.5 rounded bg-slate-800 mr-2">
                        {doc.file_type}
                      </span>
                      <span className="text-slate-400 text-[11px]">{formatBytes(doc.file_size)}</span>
                    </td>

                    <td className="px-6 py-4 text-slate-300">
                      <span>{doc.page_count ?? '—'} pages</span>
                      <span className="mx-1 text-slate-600">•</span>
                      <span className="font-semibold text-brand-400">{doc.chunk_count ?? 0} chunks</span>
                    </td>

                    <td className="px-6 py-4 text-slate-400 text-[11px]">
                      {new Date(doc.created_at).toLocaleString()}
                    </td>

                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        {doc.status === 'READY' && (
                          <button
                            onClick={() => setSelectedDocForChunks(doc)}
                            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition"
                            title="Inspect text chunks"
                          >
                            <Layers className="w-3.5 h-3.5 text-brand-400" />
                            Chunks
                          </button>
                        )}

                        {doc.status === 'FAILED' && (
                          <button
                            onClick={() => handleRetry(doc.id)}
                            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 text-xs font-medium transition"
                            title="Retry document processing"
                          >
                            <RotateCw className="w-3.5 h-3.5" />
                            Retry
                          </button>
                        )}

                        <button
                          onClick={() => handleDelete(doc.id)}
                          className="p-1.5 rounded-lg hover:bg-rose-500/10 text-slate-400 hover:text-rose-400 transition"
                          title="Delete document"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Chunk Modal */}
      <ChunkModal
        isOpen={!!selectedDocForChunks}
        document={selectedDocForChunks}
        onClose={() => setSelectedDocForChunks(null)}
      />
    </div>
  );
}
