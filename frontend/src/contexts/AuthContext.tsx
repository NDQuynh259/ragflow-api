import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { authApi } from '../api/auth';
import { apiClient } from '../api/client';
import type { User, WorkspaceInfo } from '../api/types';

interface AuthContextType {
  user: User | null;
  workspaces: WorkspaceInfo[];
  activeWorkspaceId: string | null;
  activeWorkspace: WorkspaceInfo | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isDemoMode: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => Promise<void>;
  switchWorkspace: (workspaceId: string) => Promise<void>;
  enableDemoMode: () => void;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Demo data for instant testing without active database
const DEMO_USER: User = {
  id: 'usr-demo-001',
  email: 'admin@ragplatform.io',
  full_name: 'Quynh Nguyen',
  is_active: true,
  created_at: new Date().toISOString(),
};

const DEMO_WORKSPACES: WorkspaceInfo[] = [
  {
    id: 'ws-demo-financial',
    name: 'Financial Audit & Risk RAG',
    slug: 'financial-audit',
    role: 'owner',
    permissions: ['all'],
  },
  {
    id: 'ws-demo-technical',
    name: 'Technical Specs & Docs',
    slug: 'technical-specs',
    role: 'editor',
    permissions: ['session:read', 'session:create', 'document:read'],
  },
];

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [workspaces, setWorkspaces] = useState<WorkspaceInfo[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isDemoMode, setIsDemoMode] = useState(false);

  const activeWorkspace = workspaces.find((w) => w.id === activeWorkspaceId) || workspaces[0] || null;

  const refreshProfile = useCallback(async () => {
    if (isDemoMode) return;
    try {
      const me = await authApi.getMe();
      setUser({
        id: me.id,
        email: me.email,
        full_name: me.full_name,
        is_active: me.is_active,
        created_at: me.created_at,
      });
      setWorkspaces(me.workspaces || []);
      const activeId = me.active_workspace_id || (me.workspaces && me.workspaces[0]?.id) || null;
      setActiveWorkspaceId(activeId);
      if (activeId) {
        apiClient.setWorkspaceId(activeId);
      }
    } catch {
      // Not logged in or backend offline
      setUser(null);
      setWorkspaces([]);
      setActiveWorkspaceId(null);
    } finally {
      setIsLoading(false);
    }
  }, [isDemoMode]);

  useEffect(() => {
    const handleUnauthorized = () => {
      setUser(null);
      setActiveWorkspaceId(null);
    };

    window.addEventListener('rag:unauthorized', handleUnauthorized);
    refreshProfile();

    return () => {
      window.removeEventListener('rag:unauthorized', handleUnauthorized);
    };
  }, [refreshProfile]);

  const login = async (email: string, password: string) => {
    setIsLoading(true);
    try {
      const res = await authApi.login({ email, password });
      setUser(res.user);
      await refreshProfile();
    } finally {
      setIsLoading(false);
    }
  };

  const register = async (email: string, password: string, fullName?: string) => {
    setIsLoading(true);
    try {
      await authApi.register({ email, password, full_name: fullName });
      await login(email, password);
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    if (!isDemoMode) {
      await authApi.logout();
    }
    setUser(null);
    setWorkspaces([]);
    setActiveWorkspaceId(null);
    setIsDemoMode(false);
  };

  const switchWorkspace = async (workspaceId: string) => {
    if (isDemoMode) {
      setActiveWorkspaceId(workspaceId);
      return;
    }
    const res = await authApi.switchWorkspace(workspaceId);
    setActiveWorkspaceId(res.active_workspace_id);
    await refreshProfile();
  };

  const enableDemoMode = () => {
    setIsDemoMode(true);
    setUser(DEMO_USER);
    setWorkspaces(DEMO_WORKSPACES);
    setActiveWorkspaceId(DEMO_WORKSPACES[0].id);
    setIsLoading(false);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        workspaces,
        activeWorkspaceId,
        activeWorkspace,
        isAuthenticated: !!user,
        isLoading,
        isDemoMode,
        login,
        register,
        logout,
        switchWorkspace,
        enableDemoMode,
        refreshProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
