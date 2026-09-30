/**
 * TypeScript Data Models matching the FastAPI Multimodal RAG Backend
 */

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  created_at: string;
}

export interface WorkspaceInfo {
  id: string;
  name: string;
  slug: string;
  role: string;
  permissions: string[];
}

export interface UserMeResponse {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  created_at: string;
  active_workspace_id: string | null;
  workspaces: WorkspaceInfo[];
}

export interface AuthResponse {
  user: User;
  active_workspace_id: string | null;
  session_token: string;
  expires_at: string;
}

export interface RAGConfig {
  top_k: number;
  rerank: boolean;
  similarity_threshold?: number;
  hybrid_weight?: number;
}

export interface SessionResponse {
  id: string;
  workspace_id: string;
  user_id: string | null;
  title: string;
  rag_config: RAGConfig;
  attached_document_ids: string[];
  created_at: string | null;
  updated_at: string | null;
}

export interface CitationResponse {
  id: string;
  message_id: string;
  chunk_id: string;
  document_id: string;
  page_number: number;
  bbox: number[];
  quote: string | null;
  relevance_score: number | null;
}

export interface MessageResponse {
  id: string;
  session_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  prompt_tokens: number;
  completion_tokens: number;
  latency_ms: number | null;
  citations: CitationResponse[];
  created_at: string | null;
}

export interface IngestionJobResponse {
  id: string;
  document_id: string;
  status: string;
  retry_count: number;
  parser_name: string;
  chunker_name: string;
  elapsed_seconds: number | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface DocumentResponse {
  id: string;
  workspace_id: string;
  filename: string;
  content_hash: string;
  mime_type: string;
  file_size: number;
  status: 'READY' | 'PROCESSING' | 'FAILED' | string;
  error_code: string | null;
  error_message: string | null;
  page_count: number;
  metadata: Record<string, unknown>;
  jobs: IngestionJobResponse[];
  created_at: string | null;
  updated_at: string | null;
}

export interface UploadDocumentResponse {
  document: DocumentResponse;
  message: string;
}

export interface WorkspaceOverviewReportResponse {
  workspace_id: string;
  workspace_name: string;
  generated_at: string;
  members: {
    total_members: number;
  };
  documents: {
    total_documents: number;
    total_file_size_bytes: number;
    total_pages: number;
    ready_documents: number;
    failed_documents: number;
    processing_documents: number;
    total_chunks: number;
  };
  chat: {
    total_sessions: number;
    total_messages: number;
    user_messages: number;
    assistant_messages: number;
    total_prompt_tokens: number;
    total_completion_tokens: number;
    total_citations: number;
    average_latency_ms: number;
    total_feedbacks: number;
    positive_feedbacks: number;
    negative_feedbacks: number;
  };
}

export interface DailyActivityItemDTO {
  date: string;
  documents_uploaded: number;
  messages_sent: number;
  sessions_created: number;
}

export interface WorkspaceDailyActivityResponse {
  workspace_id: string;
  days: number;
  items: DailyActivityItemDTO[];
}

export interface HealthResponse {
  status: string;
  database?: string;
  vector_extension?: string;
  rabbitmq?: string;
  version?: string;
}
