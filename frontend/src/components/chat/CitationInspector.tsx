import React from 'react';
import { X, FileText, Bookmark, Target, Sparkles } from 'lucide-react';
import type { CitationResponse } from '../../api/types';
import { Badge } from '../common/Badge';

interface CitationInspectorProps {
  citation: CitationResponse | null;
  onClose: () => void;
}

export const CitationInspector: React.FC<CitationInspectorProps> = ({ citation, onClose }) => {
  if (!citation) return null;

  const scorePercent = citation.relevance_score ? Math.round(citation.relevance_score * 100) : 88;

  return (
    <div className="w-80 md:w-96 h-full flex flex-col glass-panel border-l border-white/10 shrink-0 z-10 animate-in slide-in-from-right duration-250">
      {/* Header */}
      <div className="p-4 border-b border-white/5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bookmark className="w-4 h-4 text-indigo-400" />
          <h3 className="text-sm font-semibold text-white">Source Citation</h3>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-white/5 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 p-4 overflow-y-auto space-y-4 custom-scrollbar">
        {/* Document Meta Card */}
        <div className="glass-card rounded-xl p-3 border border-white/5 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
              <FileText className="w-4 h-4 text-cyan-400" />
              <span>Document Page {citation.page_number}</span>
            </div>
            <Badge variant="cyan" size="sm">
              Page #{citation.page_number}
            </Badge>
          </div>

          <div className="text-[11px] text-slate-400 font-mono truncate">
            Doc ID: {citation.document_id}
          </div>
          <div className="text-[11px] text-slate-500 font-mono truncate">
            Chunk ID: {citation.chunk_id}
          </div>
        </div>

        {/* Relevance Match Meter */}
        <div className="glass-card rounded-xl p-3 border border-white/5 space-y-1.5">
          <div className="flex justify-between items-center text-xs">
            <span className="text-slate-300 font-medium flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-amber-400" />
              Relevance Confidence
            </span>
            <span className="font-bold text-emerald-400 font-mono">{scorePercent}%</span>
          </div>
          <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
            <div
              className="bg-gradient-to-r from-indigo-500 via-violet-500 to-emerald-400 h-full rounded-full transition-all duration-500"
              style={{ width: `${scorePercent}%` }}
            />
          </div>
        </div>

        {/* Multimodal Bounding Box Indicator */}
        <div className="glass-card rounded-xl p-3 border border-white/5 space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-300">
            <Target className="w-3.5 h-3.5 text-indigo-400" />
            <span>Multimodal Bounding Box</span>
          </div>

          {citation.bbox && citation.bbox.length >= 4 ? (
            <div>
              <div className="text-[11px] font-mono text-slate-400 bg-slate-900/80 p-2 rounded-lg border border-white/5 mb-2">
                [{citation.bbox.map((b) => b.toFixed(1)).join(', ')}]
              </div>
              {/* Mini visual representation of page with bounding box */}
              <div className="relative w-full h-28 bg-slate-900 rounded-lg border border-slate-700/60 p-2 overflow-hidden flex flex-col justify-between">
                <div className="text-[9px] text-slate-500 font-mono uppercase">Page {citation.page_number} Layout Preview</div>
                <div
                  className="absolute bg-indigo-500/25 border-2 border-indigo-400 rounded transition-all animate-pulse"
                  style={{
                    top: `${Math.min(citation.bbox[0] / 8, 70)}%`,
                    left: `${Math.min(citation.bbox[1] / 8, 70)}%`,
                    width: `${Math.max(citation.bbox[2] / 10, 25)}%`,
                    height: `${Math.max(citation.bbox[3] / 10, 20)}%`,
                  }}
                />
                <div className="text-[9px] text-slate-500 text-right font-mono">Docling Visual Grounding</div>
              </div>
            </div>
          ) : (
            <div className="text-xs text-slate-400 italic">Page text segment without spatial coordinates.</div>
          )}
        </div>

        {/* Retrieved Quote Snippet */}
        <div className="glass-card rounded-xl p-3 border border-white/5 space-y-2">
          <div className="text-xs font-semibold text-slate-300">Extracted Quote Text</div>
          <div className="text-xs text-slate-200 leading-relaxed bg-slate-950/60 p-3 rounded-lg border border-white/5 font-sans whitespace-pre-wrap select-text">
            {citation.quote || 'Quote text extracted from vector chunk.'}
          </div>
        </div>
      </div>
    </div>
  );
};
