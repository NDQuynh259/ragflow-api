/**
 * Core HTTP Client for RAG Platform API
 * Handles base URLs, session credentials, headers, error parsing
 */

const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

class ApiClient {
  private token: string | null = null;
  private workspaceId: string | null = null;

  constructor() {
    this.token = localStorage.getItem('rag_session_token');
    this.workspaceId = localStorage.getItem('rag_active_workspace_id');
  }

  setToken(token: string | null) {
    this.token = token;
    if (token) {
      localStorage.setItem('rag_session_token', token);
    } else {
      localStorage.removeItem('rag_session_token');
    }
  }

  getToken(): string | null {
    return this.token;
  }

  setWorkspaceId(workspaceId: string | null) {
    this.workspaceId = workspaceId;
    if (workspaceId) {
      localStorage.setItem('rag_active_workspace_id', workspaceId);
    } else {
      localStorage.removeItem('rag_active_workspace_id');
    }
  }

  getWorkspaceId(): string | null {
    return this.workspaceId;
  }

  private getHeaders(customHeaders: Record<string, string> = {}, isJson = true): HeadersInit {
    const headers: Record<string, string> = {
      ...customHeaders,
    };

    if (isJson) {
      headers['Content-Type'] = 'application/json';
    }

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    if (this.workspaceId) {
      headers['X-Workspace-Id'] = this.workspaceId;
    }

    return headers;
  }

  private async handleResponse<T>(res: Response): Promise<T> {
    if (!res.ok) {
      let errorMessage = `HTTP error ${res.status}: ${res.statusText}`;
      try {
        const errorData = await res.json();
        errorMessage = errorData.detail || errorData.message || errorMessage;
      } catch {
        // use fallback message
      }

      if (res.status === 401) {
        // Session expired or unauthenticated
        this.setToken(null);
        window.dispatchEvent(new CustomEvent('rag:unauthorized'));
      }

      throw new Error(errorMessage);
    }

    if (res.status === 204) {
      return null as T;
    }

    return await res.json();
  }

  async get<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
    const url = new URL(`${API_BASE}${path}`, window.location.origin);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined) {
          url.searchParams.append(key, String(value));
        }
      });
    }

    const res = await fetch(url.toString(), {
      method: 'GET',
      headers: this.getHeaders(),
      credentials: 'include',
    });
    return this.handleResponse<T>(res);
  }

  async post<T>(path: string, body?: unknown): Promise<T> {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: this.getHeaders(),
      credentials: 'include',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    return this.handleResponse<T>(res);
  }

  async delete<T>(path: string): Promise<T> {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'DELETE',
      headers: this.getHeaders(),
      credentials: 'include',
    });
    return this.handleResponse<T>(res);
  }

  async upload<T>(path: string, formData: FormData): Promise<T> {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: this.getHeaders({}, false),
      credentials: 'include',
      body: formData,
    });
    return this.handleResponse<T>(res);
  }
}

export const apiClient = new ApiClient();
