import React from 'react';
import { Bot, User as UserIcon, Zap, FileText } from 'lucide-react';
import type { MessageResponse, CitationResponse } from '../../api/types';
import { Badge } from '../common/Badge';

interface MessageItemProps {
  message: MessageResponse;
  onSelectCitation: (citation: CitationResponse) => void;
  activeCitationId?: string;
}

export const MessageItem: React.FC<MessageItemProps> = ({
  message,
  onSelectCitation,
  activeCitationId,
}) => {
  const isAssistant = message.role === 'assistant';

  return (
    <div
      className={`flex gap-3.5 my-4 px-4 py-2 rounded-2xl transition-colors ${
        isAssistant ? 'bg-white/[0.015]' : 'justify-end'
      }`}
    >
      {/* Assistant Avatar */}
      {isAssistant && (
        <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-violet-500 flex items-center justify-center text-white shrink-0 shadow-md shadow-indigo-500/20 border border-indigo-400/40 mt-1">
          <Bot className="w-4 h-4" />
        </div>
      )}

      {/* Message Content Container */}
      <div
        className={`max-w-2xl flex flex-col space-y-2 ${
          isAssistant ? 'items-start flex-1' : 'items-end'
        }`}
      >
        {/* Message Bubble */}
        <div
          className={`p-4 rounded-2xl text-sm leading-relaxed ${
            isAssistant
              ? 'glass-card border border-white/5 text-slate-100 shadow-lg w-full'
              : 'bg-gradient-to-br from-indigo-600 to-violet-600 text-white shadow-md shadow-indigo-600/20 rounded-br-none border border-indigo-400/30'
          }`}
        >
          <div className="whitespace-pre-wrap font-sans">{message.content}</div>

          {/* Citations Tag List (if assistant response has citations) */}
          {isAssistant && message.citations && message.citations.length > 0 && (
            <div className="mt-4 pt-3 border-t border-white/5 flex flex-wrap gap-2 items-center">
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1">
                <FileText className="w-3 h-3 text-indigo-400" />
                Citations ({message.citations.length}):
              </span>
              {message.citations.map((c, index) => {
                const isSelected = activeCitationId === c.id;
                const score = c.relevance_score ? Math.round(c.relevance_score * 100) : 90;
                return (
                  <button
                    key={c.id || index}
                    onClick={() => onSelectCitation(c)}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border transition-all cursor-pointer ${
                      isSelected
                        ? 'bg-indigo-600/30 border-indigo-400 text-indigo-200 shadow-md shadow-indigo-500/20'
                        : 'bg-slate-900/80 border-slate-700/80 text-slate-300 hover:border-indigo-400/50 hover:bg-slate-800'
                    }`}
                  >
                    <span className="w-4 h-4 rounded bg-indigo-500/20 text-indigo-300 text-[10px] flex items-center justify-center font-bold">
                      {index + 1}
                    </span>
                    <span>Page {c.page_number}</span>
                    <span className="text-[10px] text-emerald-400 font-mono">({score}%)</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Message Metrics Footer */}
        {isAssistant && (
          <div className="flex items-center gap-2 text-[11px] text-slate-500 px-1 font-mono">
            {message.latency_ms && (
              <Badge variant="default" size="sm" className="font-mono">
                <Zap className="w-3 h-3 text-amber-400" />
                {Math.round(message.latency_ms)}ms
              </Badge>
            )}
            {(message.prompt_tokens > 0 || message.completion_tokens > 0) && (
              <span className="text-slate-500">
                Tokens: {message.prompt_tokens} in / {message.completion_tokens} out
              </span>
            )}
          </div>
        )}
      </div>

      {/* User Avatar */}
      {!isAssistant && (
        <div className="w-8 h-8 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 shrink-0 mt-1">
          <UserIcon className="w-4 h-4" />
        </div>
      )}
    </div>
  );
};
