import React, { useState, useRef } from 'react';
import { UploadCloud, FileType, AlertCircle, CheckCircle2 } from 'lucide-react';
import { api } from '../../api/client';
import { useWorkspace } from '../../context/WorkspaceContext';

export function UploadCard({ onUploaded }) {
  const { activeWorkspace } = useWorkspace();
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const fileInputRef = useRef(null);

  const allowedExts = ['pdf', 'docx', 'pptx'];
  const maxBytes = 25 * 1024 * 1024; // 25MB

  const handleFiles = async (files) => {
    if (!files || files.length === 0) return;
    const file = files[0];
    const ext = file.name.split('.').pop()?.toLowerCase();

    if (!allowedExts.includes(ext)) {
      setError(`Unsupported file type .${ext}. Only PDF, DOCX, and PPTX are supported.`);
      return;
    }

    if (file.size > maxBytes) {
      setError('File exceeds maximum upload size of 25 MB.');
      return;
    }

    if (!activeWorkspace) {
      setError('Please select or create a workspace first.');
      return;
    }

    setError(null);
    setSuccess(null);
    setUploading(true);

    try {
      const doc = await api.uploadDocument(activeWorkspace.id, file);
      setSuccess(`"${file.name}" uploaded successfully. Processing started.`);
      if (onUploaded) onUploaded(doc);
    } catch (err) {
      setError(err.detail || err.message || 'Failed to upload document');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-semibold text-white">Upload New Document</h3>
          <p className="text-xs text-slate-400">PDF, DOCX, or PPTX up to 25MB</p>
        </div>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition flex flex-col items-center justify-center gap-2 ${
          isDragging
            ? 'border-brand-500 bg-brand-500/10'
            : 'border-slate-800 hover:border-slate-700 bg-slate-950/40'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.pptx"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />

        <div className="w-12 h-12 rounded-full bg-slate-800 flex items-center justify-center text-slate-400 group-hover:text-brand-400">
          {uploading ? (
            <span className="w-6 h-6 border-2 border-brand-500/30 border-t-brand-400 rounded-full animate-spin" />
          ) : (
            <UploadCloud className="w-6 h-6 text-brand-400" />
          )}
        </div>

        <div>
          <p className="text-xs font-medium text-slate-200">
            {uploading ? 'Uploading & scheduling ingestion...' : 'Click or drag file here'}
          </p>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Automatic text extraction, cleaning, and semantic chunking
          </p>
        </div>
      </div>

      {error && (
        <div className="mt-3 p-2.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {success && (
        <div className="mt-3 p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{success}</span>
        </div>
      )}
    </div>
  );
}
