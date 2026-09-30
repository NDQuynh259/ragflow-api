import { apiClient } from './client';
import type { AuthResponse, UserMeResponse, User } from './types';

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  full_name?: string;
}

export const authApi = {
  async login(payload: LoginPayload): Promise<AuthResponse> {
    const res = await apiClient.post<AuthResponse>('/auth/login', payload);
    if (res.session_token) {
      apiClient.setToken(res.session_token);
    }
    if (res.active_workspace_id) {
      apiClient.setWorkspaceId(res.active_workspace_id);
    }
    return res;
  },

  async register(payload: RegisterPayload): Promise<User> {
    return apiClient.post<User>('/auth/register', payload);
  },

  async logout(): Promise<void> {
    try {
      await apiClient.post<{ message: string }>('/auth/logout');
    } finally {
      apiClient.setToken(null);
      apiClient.setWorkspaceId(null);
    }
  },

  async getMe(): Promise<UserMeResponse> {
    const res = await apiClient.get<UserMeResponse>('/auth/me');
    if (res.active_workspace_id) {
      apiClient.setWorkspaceId(res.active_workspace_id);
    }
    return res;
  },

  async switchWorkspace(workspaceId: string): Promise<{ active_workspace_id: string; message: string }> {
    const res = await apiClient.post<{ active_workspace_id: string; message: string }>('/auth/switch-workspace', {
      workspace_id: workspaceId,
    });
    apiClient.setWorkspaceId(res.active_workspace_id);
    return res;
  },
};
