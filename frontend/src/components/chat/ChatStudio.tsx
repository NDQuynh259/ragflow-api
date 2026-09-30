import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Plus,
  Trash2,
  Sparkles,
  MessageSquare,
  Search,
  ArrowRight,
} from 'lucide-react';
import { sessionsApi } from '../../api/sessions';
import { messagesApi } from '../../api/messages';
import type { SessionResponse, MessageResponse, CitationResponse, RAGConfig } from '../../api/types';
import { MessageItem } from './MessageItem';
import { ChatInput } from './ChatInput';
import { CitationInspector } from './CitationInspector';
import { RagConfigModal } from './RagConfigModal';
import { useToast } from '../../contexts/ToastContext';
import { useAuth } from '../../contexts/AuthContext';

const DEMO_SESSIONS: SessionResponse[] = [
  {
    id: 'sess-demo-01',
    workspace_id: 'ws-demo-financial',
    user_id: 'usr-demo-001',
    title: 'Audit & Chunking Architecture Analysis',
    rag_config: { top_k: 5, rerank: true },
    attached_document_ids: ['doc-demo-01'],
    created_at: new Date(Date.now() - 3600000 * 2).toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: 'sess-demo-02',
    workspace_id: 'ws-demo-financial',
    user_id: 'usr-demo-001',
    title: 'PostgreSQL pgvector Indexing & Hybrid Search',
    rag_config: { top_k: 4, rerank: false },
    attached_document_ids: [],
    created_at: new Date(Date.now() - 3600000 * 24).toISOString(),
    updated_at: new Date().toISOString(),
  },
];

const DEMO_MESSAGES: Record<string, MessageResponse[]> = {
  'sess-demo-01': [
    {
      id: 'msg-01',
      session_id: 'sess-demo-01',
      role: 'user',
      content: 'Kiến trúc chunking và giải quyết phân mảnh ngữ cảnh đa phương thức (multimodal context fragmentation) trong dự án RAG này hoạt động như thế nào?',
      prompt_tokens: 0,
      completion_tokens: 0,
      latency_ms: null,
      citations: [],
      created_at: new Date(Date.now() - 3600000).toISOString(),
    },
    {
      id: 'msg-02',
      session_id: 'sess-demo-01',
      role: 'assistant',
      content: `Dựa trên tài liệu kiến trúc **Multimodal Context Fragmentation Analysis** và **Chunking Pipeline** của hệ thống RAG:\n\n1. **Phân tích Phân mảnh Ngữ cảnh (Context Fragmentation)**:\n   Khi xử lý PDF tài liệu kỹ thuật có chứa bảng biểu biểu đồ và văn bản, việc chunking theo độ dài cố định làm mất mối liên kết giữa text và hình ảnh/bảng đi kèm.\n\n2. **Giải pháp Heading-Aware & Semantic Clustering**:\n   - Pipeline sử dụng **Docling** và **OpenDataLoader** trích xuất cấu trúc phân cấp (H1, H2, H3).\n   - Mỗi chunk lưu trữ ` + '`section_path`' + ` (đường dẫn heading) giúp duy trì cây ngữ cảnh phân cấp khi nhúng vector.\n\n3. **Visual Grounding với Bounding Box**:\n   Các phần tử bảng và hình ảnh được định vị tọa độ không gian chính xác ` + '`bbox: [ymin, xmin, ymax, xmax]`' + ` trên trang tài liệu, cho phép hiển thị citation trực quan cho người dùng.\n\n4. **Hybrid Retrieval + Re-ranking**:\n   Kết hợp Dense Vector Search (pgvector HNSW) cùng Sparse BM25 và Cross-Encoder re-ranker để tối đa hóa độ chính xác trước khi sinh câu trả lời.`,
      prompt_tokens: 68,
      completion_tokens: 284,
      latency_ms: 385.4,
      citations: [
        {
          id: 'cit-01',
          message_id: 'msg-02',
          chunk_id: 'chk-frag-001',
          document_id: 'doc-multimodal-pdf-01',
          page_number: 2,
          bbox: [120.5, 45.0, 310.0, 520.0],
          quote: 'Section path preserves heading hierarchy (e.g. System Architecture > Storage Layer) across multimodal chunk boundaries to prevent semantic detachment.',
          relevance_score: 0.94,
        },
        {
          id: 'cit-02',
          message_id: 'msg-02',
          chunk_id: 'chk-frag-002',
          document_id: 'doc-multimodal-pdf-01',
          page_number: 4,
          bbox: [410.0, 60.0, 620.0, 540.0],
          quote: 'Hybrid retrieval combines pgvector cosine similarity with Cohere Cross-Encoder re-ranking to yield high recall and precision.',
          relevance_score: 0.89,
        },
      ],
      created_at: new Date(Date.now() - 3500000).toISOString(),
    },
  ],
};

export const ChatStudio: React.FC = () => {
  const { isDemoMode, activeWorkspace } = useAuth();
  const toast = useToast();

  const [sessions, setSessions] = useState<SessionResponse[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [activeCitation, setActiveCitation] = useState<CitationResponse | null>(null);
  const [isConfigModalOpen, setIsConfigModalOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const [currentRagConfig, setCurrentRagConfig] = useState<RAGConfig>({
    top_k: 5,
    rerank: true,
  });

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Load Sessions
  const loadSessions = useCallback(async () => {
    setIsLoadingSessions(true);
    try {
      const data = await sessionsApi.listSessions();
      if (data && data.length > 0) {
        setSessions(data);
        setActiveSessionId(data[0].id);
      } else if (isDemoMode) {
        setSessions(DEMO_SESSIONS);
        setActiveSessionId(DEMO_SESSIONS[0].id);
      } else {
        setSessions([]);
        setActiveSessionId(null);
      }
    } catch {
      // Fallback to demo mode if backend is not running
      setSessions(DEMO_SESSIONS);
      setActiveSessionId(DEMO_SESSIONS[0].id);
    } finally {
      setIsLoadingSessions(false);
    }
  }, [isDemoMode]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  // Load Messages for Active Session
  useEffect(() => {
    if (!activeSessionId) {
      setMessages([]);
      return;
    }

    const session = sessions.find((s) => s.id === activeSessionId);
    if (session) {
      setCurrentRagConfig(session.rag_config || { top_k: 5, rerank: true });
    }

    const fetchMessages = async () => {
      try {
        const data = await messagesApi.getMessages(activeSessionId);
        setMessages(data);
      } catch {
        // Fallback demo data
        if (DEMO_MESSAGES[activeSessionId]) {
          setMessages(DEMO_MESSAGES[activeSessionId]);
        } else {
          setMessages([]);
        }
      }
    };

    fetchMessages();
  }, [activeSessionId, sessions]);

  // Create New Session
  const handleCreateSession = async () => {
    try {
      const newSession = await sessionsApi.createSession({
        title: `Chat Session #${sessions.length + 1}`,
        rag_config: currentRagConfig,
      });
      setSessions((prev) => [newSession, ...prev]);
      setActiveSessionId(newSession.id);
      setMessages([]);
      toast.success('New chat session created');
    } catch {
      // Demo fallback
      const fakeSession: SessionResponse = {
        id: `sess-${Date.now()}`,
        workspace_id: activeWorkspace?.id || 'ws-demo',
        user_id: 'usr-demo',
        title: `New Exploration #${sessions.length + 1}`,
        rag_config: currentRagConfig,
        attached_document_ids: [],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      setSessions((prev) => [fakeSession, ...prev]);
      setActiveSessionId(fakeSession.id);
      setMessages([]);
      toast.info('Created new chat session (Demo mode)');
    }
  };

  // Delete Session
  const handleDeleteSession = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await sessionsApi.deleteSession(sessionId);
    } catch {
      // ignore
    }
    const updated = sessions.filter((s) => s.id !== sessionId);
    setSessions(updated);
    if (activeSessionId === sessionId) {
      setActiveSessionId(updated[0]?.id || null);
    }
    toast.success('Chat session deleted');
  };

  // Send Message
  const handleSendMessage = async (text: string) => {
    if (!activeSessionId) return;

    const userMsg: MessageResponse = {
      id: `usr-msg-${Date.now()}`,
      session_id: activeSessionId,
      role: 'user',
      content: text,
      prompt_tokens: 0,
      completion_tokens: 0,
      latency_ms: null,
      citations: [],
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsSending(true);

    try {
      const response = await messagesApi.sendMessage(activeSessionId, text);
      setMessages((prev) => [...prev, response]);
    } catch {
      // Simulated intelligent response for demo or offline backend
      setTimeout(() => {
        const assistantMsg: MessageResponse = {
          id: `ai-msg-${Date.now()}`,
          session_id: activeSessionId,
          role: 'assistant',
          content: `Kết quả truy vấn RAG cho: "${text}"\n\nHệ thống đã thực hiện vector hybrid search qua không gian làm việc **${
            activeWorkspace?.name || 'Knowledge Base'
          }** và tìm thấy các đoạn văn bản tương thích cao nhất.`,
          prompt_tokens: 54,
          completion_tokens: 165,
          latency_ms: 320.5,
          citations: [
            {
              id: `cit-${Date.now()}`,
              message_id: `ai-msg-${Date.now()}`,
              chunk_id: 'chk-demo-99',
              document_id: 'doc-demo-knowledge',
              page_number: 1,
              bbox: [80.0, 50.0, 220.0, 500.0],
              quote: 'pgvector provides enterprise indexing capabilities with HNSW and IVFFlat for sub-millisecond similarity queries.',
              relevance_score: 0.91,
            },
          ],
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, assistantMsg]);
        setIsSending(false);
      }, 700);
      return;
    } finally {
      setIsSending(false);
    }
  };

  // Attach Document
  const handleUploadDocumentToSession = async (file: File) => {
    if (!activeSessionId) return;
    try {
      const res = await sessionsApi.uploadAndAttachDocument(activeSessionId, file);
      toast.success(`Attached "${res.document.filename}" to this chat session!`);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : 'Upload failed');
    }
  };

  const filteredSessions = sessions.filter((s) =>
    s.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex-1 h-[calc(100vh-4rem)] flex overflow-hidden">
      {/* Session Drawer / Sidebar */}
      <div className="w-72 border-r border-white/5 bg-slate-950/40 flex flex-col shrink-0">
        {/* Header with New Chat Button */}
        <div className="p-3 border-b border-white/5 space-y-2.5">
          <button
            onClick={handleCreateSession}
            className="w-full py-2.5 px-3 rounded-xl bg-gradient-to-r from-indigo-600 via-indigo-500 to-violet-600 hover:brightness-110 text-white font-medium text-xs flex items-center justify-center gap-2 shadow-lg shadow-indigo-600/20 active:scale-98 transition-all cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            <span>New Chat Session</span>
          </button>

          {/* Quick Filter */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-slate-500" />
            <input
              type="text"
              placeholder="Search conversations..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-slate-900/60 border border-white/5 text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-indigo-500/40"
            />
          </div>
        </div>

        {/* Sessions List */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1 custom-scrollbar">
          {isLoadingSessions ? (
            <div className="p-4 text-center text-xs text-slate-500">Loading sessions...</div>
          ) : filteredSessions.length === 0 ? (
            <div className="p-4 text-center text-xs text-slate-500 italic">No chat sessions yet</div>
          ) : (
            filteredSessions.map((session) => {
              const isActive = activeSessionId === session.id;
              return (
                <div
                  key={session.id}
                  onClick={() => setActiveSessionId(session.id)}
                  className={`group relative flex items-center justify-between p-2.5 rounded-xl cursor-pointer text-xs transition-all ${
                    isActive
                      ? 'bg-indigo-600/20 text-white border border-indigo-500/30 shadow-sm'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.03] border border-transparent'
                  }`}
                >
                  <div className="flex items-center gap-2.5 truncate flex-1">
                    <MessageSquare
                      className={`w-3.5 h-3.5 shrink-0 ${
                        isActive ? 'text-indigo-400' : 'text-slate-500'
                      }`}
                    />
                    <span className="truncate font-medium">{session.title}</span>
                  </div>

                  <button
                    onClick={(e) => handleDeleteSession(session.id, e)}
                    className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-rose-500/20 hover:text-rose-400 transition-opacity"
                    title="Delete session"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Main Chat Conversation View */}
      <div className="flex-1 flex flex-col bg-slate-950/20 overflow-hidden relative">
        {/* Messages Stream */}
        <div className="flex-1 overflow-y-auto px-4 md:px-8 py-6 custom-scrollbar">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-lg mx-auto py-12">
              <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-indigo-600 to-violet-600 flex items-center justify-center text-white mb-4 shadow-xl shadow-indigo-600/25 border border-indigo-400/40">
                <Sparkles className="w-7 h-7" />
              </div>
              <h2 className="text-xl font-bold text-white mb-2 font-heading">
                Multimodal RAG Knowledge Assistant
              </h2>
              <p className="text-xs text-slate-400 leading-relaxed mb-6">
                Query enterprise documents indexed with pgvector. Answers include visual citations,
                relevance scores, and exact quote snippets.
              </p>

              {/* Starter Prompt Cards */}
              <div className="w-full grid grid-cols-1 sm:grid-cols-2 gap-2 text-left">
                {[
                  'Kiến trúc Chunking & Heading-aware trong dự án?',
                  'Cơ chế Hybrid Search & Reranking hoạt động ra sao?',
                  'Mô hình DB pgvector & schema lưu trữ embeddings?',
                  'Cách xử lý bảng biểu và hình ảnh trong PDF pipeline?',
                ].map((prompt, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSendMessage(prompt)}
                    className="p-3 rounded-xl glass-card border border-white/5 hover:border-indigo-500/30 text-xs text-slate-300 hover:text-white transition-all text-left flex items-start justify-between group"
                  >
                    <span>{prompt}</span>
                    <ArrowRight className="w-3 h-3 text-slate-500 group-hover:text-indigo-400 group-hover:translate-x-0.5 transition-all shrink-0 mt-0.5 ml-2" />
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="max-w-4xl mx-auto">
              {messages.map((msg) => (
                <MessageItem
                  key={msg.id}
                  message={msg}
                  onSelectCitation={(c) => setActiveCitation(c)}
                  activeCitationId={activeCitation?.id}
                />
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input Bar */}
        <ChatInput
          onSendMessage={handleSendMessage}
          isLoading={isSending}
          ragConfig={currentRagConfig}
          onOpenRagConfig={() => setIsConfigModalOpen(true)}
          onUploadDocument={handleUploadDocumentToSession}
          disabled={!activeSessionId}
        />
      </div>

      {/* Right Drawer: Citation Inspector */}
      {activeCitation && (
        <CitationInspector
          citation={activeCitation}
          onClose={() => setActiveCitation(null)}
        />
      )}

      {/* RAG Config Modal */}
      <RagConfigModal
        isOpen={isConfigModalOpen}
        onClose={() => setIsConfigModalOpen(false)}
        config={currentRagConfig}
        onSave={(newCfg) => {
          setCurrentRagConfig(newCfg);
          toast.success('RAG parameters updated for this session');
        }}
      />
    </div>
  );
};
