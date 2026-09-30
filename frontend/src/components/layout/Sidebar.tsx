import React, { useState } from 'react';
import {
  MessageSquare,
  FileText,
  BarChart3,
  Layers,
  ChevronDown,
  LogOut,
  Sparkles,
  Shield,
  Activity,
  UserCheck,
} from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { Badge } from '../common/Badge';

export type ActiveTab = 'chat' | 'documents' | 'reports';

interface SidebarProps {
  activeTab: ActiveTab;
  onTabChange: (tab: ActiveTab) => void;
  systemHealth: 'healthy' | 'degraded' | 'unhealthy';
  onOpenAuth: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onTabChange,
  systemHealth,
  onOpenAuth,
}) => {
  const { user, workspaces, activeWorkspace, switchWorkspace, logout, isAuthenticated, isDemoMode } =
    useAuth();
  const [showWorkspaceMenu, setShowWorkspaceMenu] = useState(false);

  const navItems = [
    {
      id: 'chat' as ActiveTab,
      label: 'RAG Chat Studio',
      icon: MessageSquare,
      desc: 'Multimodal Vector Retrieval',
    },
    {
      id: 'documents' as ActiveTab,
      label: 'Knowledge Documents',
      icon: FileText,
      desc: 'Ingestion & Chunk Pipeline',
    },
    {
      id: 'reports' as ActiveTab,
      label: 'Analytics & KPIs',
      icon: BarChart3,
      desc: 'Multi-table metrics & trends',
    },
  ];

  return (
    <aside className="w-72 h-screen flex flex-col bg-slate-950/80 border-r border-white/5 backdrop-blur-xl shrink-0 select-none z-20">
      {/* Brand & Logo */}
      <div className="p-5 border-b border-white/5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="relative w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/25 border border-indigo-400/40">
            <Sparkles className="w-5 h-5 text-white" />
            <div className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-emerald-400 border-2 border-slate-950" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-bold text-white text-base tracking-tight font-heading">RAG Platform</span>
            </div>
            <span className="text-[10px] text-slate-400 font-mono tracking-wider uppercase">Enterprise Edition</span>
          </div>
        </div>

        <Badge
          variant={systemHealth === 'healthy' ? 'success' : systemHealth === 'degraded' ? 'warning' : 'error'}
          size="sm"
          pulse={systemHealth !== 'unhealthy'}
        >
          {systemHealth}
        </Badge>
      </div>

      {/* Workspace Switcher */}
      <div className="p-4 border-b border-white/5">
        <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
          <Layers className="w-3.5 h-3.5 text-indigo-400" />
          <span>Active Workspace</span>
        </div>

        <div className="relative">
          <button
            onClick={() => setShowWorkspaceMenu(!showWorkspaceMenu)}
            className="w-full flex items-center justify-between p-2.5 rounded-xl glass-input hover:border-indigo-500/40 text-left transition-colors"
          >
            <div className="truncate pr-2">
              <div className="text-sm font-medium text-white truncate">
                {activeWorkspace?.name || 'Default Workspace'}
              </div>
              <div className="text-[11px] text-slate-400 flex items-center gap-1 mt-0.5">
                <Shield className="w-3 h-3 text-indigo-400" />
                <span className="capitalize">{activeWorkspace?.role || 'member'}</span>
              </div>
            </div>
            <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />
          </button>

          {/* Workspace Dropdown */}
          {showWorkspaceMenu && (
            <div className="absolute top-full left-0 right-0 mt-1.5 glass-card rounded-xl border border-white/10 p-1.5 shadow-2xl z-30 animate-in fade-in zoom-in-95">
              <div className="text-[10px] font-semibold text-slate-400 px-2 py-1 uppercase">Switch Context</div>
              {workspaces.length === 0 ? (
                <div className="px-2 py-2 text-xs text-slate-400 italic">No workspaces found</div>
              ) : (
                workspaces.map((ws) => (
                  <button
                    key={ws.id}
                    onClick={() => {
                      switchWorkspace(ws.id);
                      setShowWorkspaceMenu(false);
                    }}
                    className={`w-full text-left px-2.5 py-2 rounded-lg text-xs flex items-center justify-between transition-colors ${
                      ws.id === activeWorkspace?.id
                        ? 'bg-indigo-600/20 text-indigo-300 font-medium'
                        : 'text-slate-300 hover:bg-white/5'
                    }`}
                  >
                    <span className="truncate">{ws.name}</span>
                    <span className="text-[10px] text-slate-400 uppercase px-1.5 py-0.5 rounded bg-slate-800">
                      {ws.role}
                    </span>
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      </div>

      {/* Main Navigation */}
      <nav className="flex-1 p-3 space-y-1.5 overflow-y-auto custom-scrollbar">
        <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider px-3 py-1">
          Navigation
        </div>
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onTabChange(item.id)}
              className={`w-full flex items-center gap-3.5 px-3 py-3 rounded-xl text-left transition-all duration-200 group ${
                isActive
                  ? 'bg-gradient-to-r from-indigo-600/25 to-violet-600/10 border border-indigo-500/30 text-white shadow-lg shadow-indigo-900/10'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.03] border border-transparent'
              }`}
            >
              <div
                className={`p-2 rounded-lg transition-colors ${
                  isActive
                    ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30'
                    : 'bg-slate-900 text-slate-400 group-hover:text-white group-hover:bg-slate-800'
                }`}
              >
                <Icon className="w-4 h-4" />
              </div>
              <div className="flex-1 truncate">
                <div className={`text-sm font-medium ${isActive ? 'text-white' : 'text-slate-300'}`}>
                  {item.label}
                </div>
                <div className="text-[11px] text-slate-400 truncate">{item.desc}</div>
              </div>
            </button>
          );
        })}
      </nav>

      {/* Demo Mode Notice */}
      {isDemoMode && (
        <div className="mx-3 my-2 p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs flex items-center gap-2">
          <Activity className="w-4 h-4 shrink-0 text-amber-400" />
          <span>Demo Interactive Mode Active</span>
        </div>
      )}

      {/* User & Auth Footer */}
      <div className="p-3 border-t border-white/5 bg-slate-950/40">
        {isAuthenticated ? (
          <div className="flex items-center justify-between p-2 rounded-xl bg-white/[0.02] border border-white/5">
            <div className="flex items-center gap-2.5 truncate">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white text-xs font-bold uppercase shadow">
                {user?.full_name ? user.full_name[0] : user?.email[0]}
              </div>
              <div className="truncate">
                <div className="text-xs font-semibold text-white truncate">
                  {user?.full_name || user?.email.split('@')[0]}
                </div>
                <div className="text-[10px] text-slate-400 truncate">{user?.email}</div>
              </div>
            </div>
            <button
              onClick={logout}
              title="Log Out"
              className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        ) : (
          <button
            onClick={onOpenAuth}
            className="w-full py-2.5 px-3 rounded-xl bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-500/30 text-indigo-300 hover:text-white text-xs font-medium flex items-center justify-center gap-2 transition-colors"
          >
            <UserCheck className="w-4 h-4" />
            <span>Sign In / Connect API</span>
          </button>
        )}
      </div>
    </aside>
  );
};
