import { apiClient } from './client';
import type { WorkspaceOverviewReportResponse, WorkspaceDailyActivityResponse } from './types';

export const reportsApi = {
  async getOverview(): Promise<WorkspaceOverviewReportResponse> {
    return apiClient.get<WorkspaceOverviewReportResponse>('/reports/overview');
  },

  async getActivity(days = 30): Promise<WorkspaceDailyActivityResponse> {
    return apiClient.get<WorkspaceDailyActivityResponse>('/reports/activity', { days });
  },
};
