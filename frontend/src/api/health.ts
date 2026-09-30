import { apiClient } from './client';

export interface ComponentHealth {
  status: 'healthy' | 'degraded' | 'unhealthy';
  details?: string;
}

export interface SystemHealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy';
  app_name?: string;
  version?: string;
  components?: {
    database?: ComponentHealth;
    message_broker?: ComponentHealth;
    storage?: ComponentHealth;
    ai_providers?: ComponentHealth;
    scheduler?: ComponentHealth;
  };
}

export const healthApi = {
  async check(): Promise<SystemHealthResponse> {
    try {
      return await apiClient.get<SystemHealthResponse>('/health');
    } catch {
      return { status: 'unhealthy' };
    }
  },
};
