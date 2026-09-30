import React, { useState, useRef, useEffect } from 'react';
import { Send, Paperclip, Sliders, Loader2 } from 'lucide-react';
import type { RAGConfig } from '../../api/types';

interface ChatInputProps {
  onSendMessage: (content: string) => void;
  isLoading: boolean;
  ragConfig: RAGConfig;
  onOpenRagConfig: () => void;
  onUploadDocument: (file: File) => void;
  disabled?: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({
  onSendMessage,
  isLoading,
  ragConfig,
  onOpenRagConfig,
  onUploadDocument,
  disabled = false,
}) => {
  const [content, setContent] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  }, [content]);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!content.trim() || isLoading || disabled) return;
    onSendMessage(content.trim());
    setContent('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      onUploadDocument(file);
      e.target.value = '';
    }
  };

  return (
    <div className="p-4 border-t border-white/5 bg-slate-950/80 backdrop-blur-xl">
      <form onSubmit={handleSubmit} className="max-w-4xl mx-auto">
        <div className="relative glass-card rounded-2xl border border-white/10 p-2 focus-within:border-indigo-500/50 focus-within:ring-2 focus-within:ring-indigo-500/20 transition-all shadow-xl">
          {/* Text Area */}
          <textarea
            ref={textareaRef}
            rows={1}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled || isLoading}
            placeholder={
              disabled
                ? 'Select or create a chat session to start asking questions...'
                : 'Ask anything grounded in your documents... (Press Enter to send, Shift+Enter for newline)'
            }
            className="w-full bg-transparent px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none resize-none max-h-44 custom-scrollbar"
          />

          {/* Action Row */}
          <div className="flex items-center justify-between pt-2 px-1 border-t border-white/5 mt-1">
            <div className="flex items-center gap-2">
              {/* File Attachment Hidden Input */}
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.txt"
                onChange={handleFileChange}
                className="hidden"
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={disabled || isLoading}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/5 transition-colors flex items-center gap-1.5 text-xs"
                title="Upload & attach PDF document to this session"
              >
                <Paperclip className="w-4 h-4" />
                <span className="hidden sm:inline">Attach Doc</span>
              </button>

              {/* RAG Config Trigger */}
              <button
                type="button"
                onClick={onOpenRagConfig}
                className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-300 hover:bg-white/5 transition-colors flex items-center gap-1.5 text-xs font-mono"
                title="Configure Retrieval Parameters"
              >
                <Sliders className="w-3.5 h-3.5 text-indigo-400" />
                <span>
                  Top-{ragConfig.top_k} • {ragConfig.rerank ? 'Rerank ON' : 'Standard'}
                </span>
              </button>
            </div>

            {/* Send Button */}
            <button
              type="submit"
              disabled={!content.trim() || isLoading || disabled}
              className="px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 text-white font-medium text-xs flex items-center gap-1.5 shadow-md shadow-indigo-500/25 hover:brightness-110 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Thinking...</span>
                </>
              ) : (
                <>
                  <span>Send</span>
                  <Send className="w-3.5 h-3.5" />
                </>
              )}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};
