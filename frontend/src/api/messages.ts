import { apiClient } from './client';
import type { MessageResponse } from './types';

export const messagesApi = {
  async getMessages(sessionId: string, limit = 100, offset = 0): Promise<MessageResponse[]> {
    return apiClient.get<MessageResponse[]>(`/chat-sessions/${sessionId}/messages`, {
      limit,
      offset,
    });
  },

  async sendMessage(sessionId: string, content: string): Promise<MessageResponse> {
    return apiClient.post<MessageResponse>(`/chat-sessions/${sessionId}/messages`, {
      content,
    });
  },
};
