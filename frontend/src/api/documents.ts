import { apiClient } from './client';
import type { DocumentResponse, UploadDocumentResponse } from './types';

export const documentsApi = {
  async listDocuments(limit = 50, offset = 0): Promise<DocumentResponse[]> {
    return apiClient.get<DocumentResponse[]>('/documents', { limit, offset });
  },

  async uploadDocument(file: File): Promise<UploadDocumentResponse> {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.upload<UploadDocumentResponse>('/documents', formData);
  },

  async getDocument(documentId: string): Promise<DocumentResponse> {
    return apiClient.get<DocumentResponse>(`/documents/${documentId}`);
  },

  async deleteDocument(documentId: string): Promise<void> {
    return apiClient.delete<void>(`/documents/${documentId}`);
  },
};
