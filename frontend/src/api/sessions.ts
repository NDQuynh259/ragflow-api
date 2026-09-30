import { apiClient } from './client';
import type { SessionResponse, RAGConfig, UploadDocumentResponse } from './types';

export interface CreateSessionPayload {
  title?: string;
  rag_config?: Partial<RAGConfig>;
}

export const sessionsApi = {
  async listSessions(limit = 50, offset = 0): Promise<SessionResponse[]> {
    return apiClient.get<SessionResponse[]>('/chat-sessions', { limit, offset });
  },

  async createSession(payload?: CreateSessionPayload): Promise<SessionResponse> {
    return apiClient.post<SessionResponse>('/chat-sessions', {
      title: payload?.title || 'New Chat Session',
      rag_config: {
        top_k: payload?.rag_config?.top_k ?? 5,
        rerank: payload?.rag_config?.rerank ?? true,
      },
    });
  },

  async getSession(sessionId: string): Promise<SessionResponse> {
    return apiClient.get<SessionResponse>(`/chat-sessions/${sessionId}`);
  },

  async deleteSession(sessionId: string): Promise<void> {
    return apiClient.delete<void>(`/chat-sessions/${sessionId}`);
  },

  async attachDocument(sessionId: string, documentId: string): Promise<SessionResponse> {
    return apiClient.post<SessionResponse>(`/chat-sessions/${sessionId}/documents/attach`, {
      document_id: documentId,
    });
  },

  async uploadAndAttachDocument(sessionId: string, file: File): Promise<UploadDocumentResponse> {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.upload<UploadDocumentResponse>(`/chat-sessions/${sessionId}/documents`, formData);
  },
};
