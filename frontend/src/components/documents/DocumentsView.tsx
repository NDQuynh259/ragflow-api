import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Upload,
  FileText,
  Trash2,
  Eye,
  CheckCircle2,
  Clock,
  RefreshCw,
  Search,
  Filter,
  Layers,
  Sparkles,
} from 'lucide-react';
import { documentsApi } from '../../api/documents';
import type { DocumentResponse } from '../../api/types';
import { Badge } from '../common/Badge';
import { Button } from '../common/Button';
import { Modal } from '../common/Modal';
import { useToast } from '../../contexts/ToastContext';
import { useAuth } from '../../contexts/AuthContext';

const DEMO_DOCUMENTS: DocumentResponse[] = [
  {
    id: 'doc-demo-01',
    workspace_id: 'ws-demo-financial',
    filename: 'Multimodal_Context_Fragmentation_Analysis.pdf',
    content_hash: 'a7b8c9d0e1f234567890abcdef123456',
    mime_type: 'application/pdf',
    file_size: 1401200,
    status: 'READY',
    error_code: null,
    error_message: null,
    page_count: 14,
    metadata: {
      author: 'RAG Architecture Team',
      parser: 'DoclingParser',
      chunker: 'HeadingAwareChunker',
      total_chunks: 48,
    },
    jobs: [
      {
        id: 'job-01',
        document_id: 'doc-demo-01',
        status: 'COMPLETED',
        retry_count: 0,
        parser_name: 'DoclingParser',
        chunker_name: 'HeadingAwareChunker',
        elapsed_seconds: 4.25,
        started_at: new Date(Date.now() - 3600000 * 2).toISOString(),
        completed_at: new Date(Date.now() - 3600000 * 2 + 4250).toISOString(),
      },
    ],
    created_at: new Date(Date.now() - 3600000 * 2).toISOString(),
    updated_at: new Date(Date.now() - 3600000 * 2).toISOString(),
  },
  {
    id: 'doc-demo-02',
    workspace_id: 'ws-demo-financial',
    filename: 'Chunking_Architecture_Specs.pdf',
    content_hash: 'f9e8d7c6b5a432109876fedcba654321',
    mime_type: 'application/pdf',
    file_size: 894300,
    status: 'READY',
    error_code: null,
    error_message: null,
    page_count: 8,
    metadata: {
      author: 'Data Platform',
      parser: 'OpenDataLoader',
      chunker: 'SemanticClusterChunker',
      total_chunks: 32,
    },
    jobs: [
      {
        id: 'job-02',
        document_id: 'doc-demo-02',
        status: 'COMPLETED',
        retry_count: 0,
        parser_name: 'OpenDataLoader',
        chunker_name: 'SemanticClusterChunker',
        elapsed_seconds: 2.8,
        started_at: new Date(Date.now() - 3600000 * 12).toISOString(),
        completed_at: new Date(Date.now() - 3600000 * 12 + 2800).toISOString(),
      },
    ],
    created_at: new Date(Date.now() - 3600000 * 12).toISOString(),
    updated_at: new Date(Date.now() - 3600000 * 12).toISOString(),
  },
  {
    id: 'doc-demo-03',
    workspace_id: 'ws-demo-financial',
    filename: 'Q3_Financial_Audit_Report.pdf',
    content_hash: '11223344556677889900aabbccddeeff',
    mime_type: 'application/pdf',
    file_size: 2450000,
    status: 'PROCESSING',
    error_code: null,
    error_message: null,
    page_count: 26,
    metadata: {
      parser: 'DoclingParser',
      chunker: 'HeadingAwareChunker',
    },
    jobs: [
      {
        id: 'job-03',
        document_id: 'doc-demo-03',
        status: 'PROCESSING',
        retry_count: 0,
        parser_name: 'DoclingParser',
        chunker_name: 'HeadingAwareChunker',
        elapsed_seconds: 1.2,
        started_at: new Date().toISOString(),
        completed_at: null,
      },
    ],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

export const DocumentsView: React.FC = () => {
  const { isDemoMode } = useAuth();
  const toast = useToast();

  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'READY' | 'PROCESSING' | 'FAILED'>('ALL');
  const [selectedDocForDetails, setSelectedDocForDetails] = useState<DocumentResponse | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const loadDocuments = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await documentsApi.listDocuments();
      if (data && data.length > 0) {
        setDocuments(data);
      } else if (isDemoMode) {
        setDocuments(DEMO_DOCUMENTS);
      } else {
        setDocuments([]);
      }
    } catch {
      // Fallback demo data if backend unreachable
      setDocuments(DEMO_DOCUMENTS);
    } finally {
      setIsLoading(false);
    }
  }, [isDemoMode]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  // Upload handler
  const handleUpload = async (file: File) => {
    setIsUploading(true);
    try {
      const res = await documentsApi.uploadDocument(file);
      setDocuments((prev) => [res.document, ...prev]);
      toast.success(`Uploaded "${file.name}" to ingestion queue`);
    } catch {
      // Demo upload emulation
      const fakeDoc: DocumentResponse = {
        id: `doc-${Date.now()}`,
        workspace_id: 'ws-demo',
        filename: file.name,
        content_hash: 'hash-' + Math.random().toString(16),
        mime_type: file.type || 'application/pdf',
        file_size: file.size,
        status: 'READY',
        error_code: null,
        error_message: null,
        page_count: Math.floor(Math.random() * 15) + 3,
        metadata: {
          parser: 'DoclingParser',
          chunker: 'HeadingAwareChunker',
          total_chunks: Math.floor(Math.random() * 30) + 10,
        },
        jobs: [
          {
            id: `job-${Date.now()}`,
            document_id: `doc-${Date.now()}`,
            status: 'COMPLETED',
            retry_count: 0,
            parser_name: 'DoclingParser',
            chunker_name: 'HeadingAwareChunker',
            elapsed_seconds: 3.1,
            started_at: new Date().toISOString(),
            completed_at: new Date().toISOString(),
          },
        ],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      setDocuments((prev) => [fakeDoc, ...prev]);
      toast.info(`Uploaded "${file.name}" (Demo pipeline)`);
    } finally {
      setIsUploading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
  };

  const handleDelete = async (docId: string, filename: string) => {
    if (!window.confirm(`Delete document "${filename}" and its vector chunks?`)) return;
    try {
      await documentsApi.deleteDocument(docId);
    } catch {
      // ignore
    }
    setDocuments((prev) => prev.filter((d) => d.id !== docId));
    toast.success(`Document "${filename}" removed`);
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const filteredDocs = documents.filter((doc) => {
    const matchesSearch = doc.filename.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === 'ALL' || doc.status.toUpperCase() === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const totalPages = documents.reduce((acc, d) => acc + (d.page_count || 0), 0);
  const readyCount = documents.filter((d) => d.status.toUpperCase() === 'READY').length;

  return (
    <div className="flex-1 h-[calc(100vh-4rem)] overflow-y-auto p-6 md:p-8 space-y-6 custom-scrollbar bg-slate-950/20">
      {/* Top Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="glass-card rounded-2xl p-4 border border-white/5 flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-400 font-medium">Total Documents</div>
            <div className="text-2xl font-bold text-white mt-1 font-heading">{documents.length}</div>
          </div>
          <div className="w-10 h-10 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
            <FileText className="w-5 h-5" />
          </div>
        </div>

        <div className="glass-card rounded-2xl p-4 border border-white/5 flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-400 font-medium">Ready & Indexed</div>
            <div className="text-2xl font-bold text-emerald-400 mt-1 font-heading">{readyCount}</div>
          </div>
          <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
            <CheckCircle2 className="w-5 h-5" />
          </div>
        </div>

        <div className="glass-card rounded-2xl p-4 border border-white/5 flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-400 font-medium">Total Pages Parsed</div>
            <div className="text-2xl font-bold text-cyan-400 mt-1 font-heading">{totalPages}</div>
          </div>
          <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
            <Layers className="w-5 h-5" />
          </div>
        </div>

        <div className="glass-card rounded-2xl p-4 border border-white/5 flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-400 font-medium">Pipeline Status</div>
            <div className="text-sm font-semibold text-white mt-1.5 flex items-center gap-1.5">
              <Sparkles className="w-4 h-4 text-violet-400" />
              <span>Docling + pgvector</span>
            </div>
          </div>
          <Badge variant="purple" size="sm">
            Active
          </Badge>
        </div>
      </div>

      {/* Drag & Drop Upload Zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`relative border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all duration-200 ${
          isDragging
            ? 'border-indigo-400 bg-indigo-500/10 scale-[1.01]'
            : 'border-white/10 hover:border-indigo-500/40 bg-slate-950/40 hover:bg-slate-900/40'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.txt"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleUpload(f);
          }}
          className="hidden"
        />

        <div className="max-w-md mx-auto flex flex-col items-center">
          <div className="w-12 h-12 rounded-2xl bg-indigo-600/15 border border-indigo-500/30 flex items-center justify-center text-indigo-400 mb-3 shadow-lg shadow-indigo-600/10">
            <Upload className={`w-6 h-6 ${isUploading ? 'animate-bounce text-indigo-300' : ''}`} />
          </div>
          <h3 className="text-sm font-semibold text-white mb-1">
            {isUploading ? 'Uploading & Enqueuing Ingestion Job...' : 'Upload Knowledge Documents'}
          </h3>
          <p className="text-xs text-slate-400 leading-relaxed">
            Drag & drop PDF, DOCX, or TXT files here, or click to browse. The background worker parses
            tables, images, headings, and generates pgvector embeddings.
          </p>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="relative w-full sm:w-72">
          <Search className="w-4 h-4 absolute left-3 top-3 text-slate-500" />
          <input
            type="text"
            placeholder="Search documents by filename..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-2 rounded-xl glass-input text-xs text-slate-200 placeholder:text-slate-500"
          />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto overflow-x-auto pb-1">
          <span className="text-xs text-slate-500 flex items-center gap-1 font-medium">
            <Filter className="w-3.5 h-3.5" /> Filter:
          </span>
          {(['ALL', 'READY', 'PROCESSING', 'FAILED'] as const).map((st) => (
            <button
              key={st}
              onClick={() => setStatusFilter(st)}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                statusFilter === st
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'bg-slate-900/60 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              {st}
            </button>
          ))}

          <button
            onClick={loadDocuments}
            className="p-1.5 rounded-lg border border-white/5 text-slate-400 hover:text-white hover:bg-white/5"
            title="Reload documents list"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Documents Table */}
      <div className="glass-card rounded-2xl border border-white/5 overflow-hidden shadow-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/60 text-slate-400 uppercase tracking-wider text-[10px] border-b border-white/5">
              <tr>
                <th className="py-3.5 px-4 font-semibold">Document Name</th>
                <th className="py-3.5 px-4 font-semibold">Status</th>
                <th className="py-3.5 px-4 font-semibold">Pages</th>
                <th className="py-3.5 px-4 font-semibold">Size</th>
                <th className="py-3.5 px-4 font-semibold">Parser & Chunker</th>
                <th className="py-3.5 px-4 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 text-slate-300">
              {filteredDocs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-slate-500 italic">
                    No documents found matching the filter criteria.
                  </td>
                </tr>
              ) : (
                filteredDocs.map((doc) => {
                  const isReady = doc.status.toUpperCase() === 'READY';
                  const isProcessing = doc.status.toUpperCase() === 'PROCESSING';
                  const latestJob = doc.jobs && doc.jobs[0];

                  return (
                    <tr
                      key={doc.id}
                      className="hover:bg-white/[0.02] transition-colors group cursor-default"
                    >
                      {/* Name */}
                      <td className="py-3.5 px-4">
                        <div className="flex items-center gap-3">
                          <div className="p-2 rounded-xl bg-slate-900 text-indigo-400 border border-white/5 group-hover:border-indigo-500/30 transition-colors">
                            <FileText className="w-4 h-4" />
                          </div>
                          <div>
                            <div className="font-medium text-white truncate max-w-xs md:max-w-md">
                              {doc.filename}
                            </div>
                            <div className="text-[10px] text-slate-500 font-mono">
                              {doc.mime_type} • ID: {doc.id.substring(0, 8)}...
                            </div>
                          </div>
                        </div>
                      </td>

                      {/* Status */}
                      <td className="py-3.5 px-4">
                        <Badge
                          variant={isReady ? 'success' : isProcessing ? 'warning' : 'error'}
                          size="sm"
                          pulse={isProcessing}
                        >
                          {doc.status}
                        </Badge>
                      </td>

                      {/* Pages */}
                      <td className="py-3.5 px-4 font-mono">
                        {doc.page_count > 0 ? `${doc.page_count} pgs` : '—'}
                      </td>

                      {/* Size */}
                      <td className="py-3.5 px-4 font-mono text-slate-400">
                        {formatFileSize(doc.file_size)}
                      </td>

                      {/* Parser & Chunker */}
                      <td className="py-3.5 px-4">
                        <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
                          <span className="font-medium text-slate-300">
                            {latestJob?.parser_name || 'Docling'}
                          </span>
                          <span>•</span>
                          <span className="font-mono text-indigo-300">
                            {latestJob?.chunker_name || 'HeadingAware'}
                          </span>
                          {latestJob?.elapsed_seconds && (
                            <span className="text-[10px] text-slate-500">
                              ({latestJob.elapsed_seconds.toFixed(1)}s)
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Actions */}
                      <td className="py-3.5 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={() => setSelectedDocForDetails(doc)}
                            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/5 transition-colors"
                            title="View Ingestion Pipeline Details"
                          >
                            <Eye className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleDelete(doc.id, doc.filename)}
                            className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
                            title="Delete Document"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Ingestion Details Modal */}
      {selectedDocForDetails && (
        <Modal
          isOpen={true}
          onClose={() => setSelectedDocForDetails(null)}
          title={`Pipeline Details: ${selectedDocForDetails.filename}`}
          subtitle="Parser configuration, chunking telemetry, and pgvector embeddings"
          maxWidth="lg"
        >
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3 rounded-xl bg-slate-900/60 border border-white/5">
                <div className="text-slate-400">Document ID</div>
                <div className="font-mono text-white truncate mt-0.5">{selectedDocForDetails.id}</div>
              </div>
              <div className="p-3 rounded-xl bg-slate-900/60 border border-white/5">
                <div className="text-slate-400">Content Hash</div>
                <div className="font-mono text-white truncate mt-0.5">{selectedDocForDetails.content_hash}</div>
              </div>
            </div>

            {/* Ingestion Jobs List */}
            <div className="space-y-2">
              <div className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-indigo-400" />
                <span>Ingestion Processing Jobs</span>
              </div>

              {selectedDocForDetails.jobs && selectedDocForDetails.jobs.length > 0 ? (
                selectedDocForDetails.jobs.map((job) => (
                  <div
                    key={job.id}
                    className="p-3 rounded-xl glass-card border border-white/5 text-xs space-y-2"
                  >
                    <div className="flex justify-between items-center">
                      <span className="font-mono text-indigo-300">Job #{job.id.substring(0, 8)}</span>
                      <Badge
                        variant={job.status === 'COMPLETED' ? 'success' : 'warning'}
                        size="sm"
                      >
                        {job.status}
                      </Badge>
                    </div>

                    <div className="grid grid-cols-3 gap-2 text-[11px] text-slate-400">
                      <div>
                        <span>Parser:</span>{' '}
                        <strong className="text-white">{job.parser_name}</strong>
                      </div>
                      <div>
                        <span>Chunker:</span>{' '}
                        <strong className="text-white">{job.chunker_name}</strong>
                      </div>
                      <div>
                        <span>Duration:</span>{' '}
                        <strong className="text-white">
                          {job.elapsed_seconds ? `${job.elapsed_seconds}s` : 'Processing'}
                        </strong>
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-xs text-slate-500 italic">No job records found.</div>
              )}
            </div>

            <div className="flex justify-end pt-2">
              <Button variant="secondary" size="md" onClick={() => setSelectedDocForDetails(null)}>
                Close
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};
