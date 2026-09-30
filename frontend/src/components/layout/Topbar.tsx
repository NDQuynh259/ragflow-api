import React from 'react';
import { ExternalLink, RefreshCw, Cpu, Database } from 'lucide-react';
import type { ActiveTab } from './Sidebar';
import { Badge } from '../common/Badge';

interface TopbarProps {
  activeTab: ActiveTab;
  systemHealth: 'healthy' | 'degraded' | 'unhealthy';
  onRefresh: () => void;
  isRefreshing: boolean;
}

export const Topbar: React.FC<TopbarProps> = ({
  activeTab,
  systemHealth,
  onRefresh,
  isRefreshing,
}) => {
  const titles: Record<ActiveTab, { title: string; subtitle: string }> = {
    chat: {
      title: 'Multimodal RAG Chat Studio',
      subtitle: 'Ask questions with citation grounded references, vector similarity & re-ranking',
    },
    documents: {
      title: 'Knowledge Base & Ingestion Pipeline',
      subtitle: 'Upload PDFs, inspect Docling/OpenData parsers, chunking strategies & pgvector indexing',
    },
    reports: {
      title: 'Platform Analytics & Metrics',
      subtitle: 'Workspace usage overview, token consumption, query latency & daily trends',
    },
  };

  const current = titles[activeTab];

  return (
    <header className="h-16 px-6 border-b border-white/5 bg-slate-950/60 backdrop-blur-md flex items-center justify-between shrink-0 z-10">
      <div>
        <h1 className="text-base font-semibold text-white tracking-tight font-heading flex items-center gap-2">
          {current.title}
        </h1>
        <p className="text-xs text-slate-400 hidden sm:block">{current.subtitle}</p>
      </div>

      <div className="flex items-center gap-3">
        {/* Backend FastApi Link */}
        <a
          href="http://127.0.0.1:8000/docs"
          target="_blank"
          rel="noreferrer"
          className="text-xs text-slate-400 hover:text-indigo-300 flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/5 hover:border-indigo-500/30 bg-white/[0.02] transition-colors"
          title="Open FastAPI Swagger Interactive Docs"
        >
          <Cpu className="w-3.5 h-3.5 text-indigo-400" />
          <span className="hidden md:inline">FastAPI Swagger</span>
          <ExternalLink className="w-3 h-3 text-slate-500" />
        </a>

        {/* Database & Vector Status */}
        <div className="hidden lg:flex items-center gap-2 px-3 py-1.5 rounded-lg border border-white/5 bg-white/[0.02] text-xs text-slate-400">
          <Database className="w-3.5 h-3.5 text-cyan-400" />
          <span>pgvector 16</span>
          <Badge variant={systemHealth === 'healthy' ? 'success' : 'error'} size="sm">
            {systemHealth === 'healthy' ? 'READY' : 'OFFLINE'}
          </Badge>
        </div>

        {/* Refresh Button */}
        <button
          onClick={onRefresh}
          disabled={isRefreshing}
          className="p-2 rounded-xl border border-white/10 hover:border-indigo-500/40 text-slate-400 hover:text-white hover:bg-white/5 transition-colors disabled:opacity-50"
          title="Refresh Workspace Data"
        >
          <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin text-indigo-400' : ''}`} />
        </button>
      </div>
    </header>
  );
};
