import React, { useState } from 'react';
import { Check } from 'lucide-react';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';
import type { RAGConfig } from '../../api/types';

interface RagConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  config: RAGConfig;
  onSave: (newConfig: RAGConfig) => void;
}

export const RagConfigModal: React.FC<RagConfigModalProps> = ({
  isOpen,
  onClose,
  config,
  onSave,
}) => {
  const [topK, setTopK] = useState(config.top_k || 5);
  const [rerank, setRerank] = useState(config.rerank ?? true);
  const [similarityThreshold, setSimilarityThreshold] = useState(
    config.similarity_threshold ?? 0.65
  );

  const handleSave = () => {
    onSave({
      top_k: topK,
      rerank,
      similarity_threshold: similarityThreshold,
    });
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="RAG Retrieval Engine Settings"
      subtitle="Tune pgvector hybrid retrieval, reranking, and chunk sampling"
    >
      <div className="space-y-5">
        {/* Top-K Selection */}
        <div>
          <div className="flex justify-between items-center mb-1.5">
            <label className="text-xs font-semibold text-slate-300">Top-K Retrieved Chunks</label>
            <span className="text-xs font-mono font-bold text-indigo-400 px-2 py-0.5 rounded bg-indigo-500/10 border border-indigo-500/20">
              {topK} chunks
            </span>
          </div>
          <input
            type="range"
            min={1}
            max={20}
            step={1}
            value={topK}
            onChange={(e) => setTopK(Number(e.target.value))}
            className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
          />
          <p className="text-[11px] text-slate-500 mt-1">
            Number of top vector chunks passed to the LLM context window.
          </p>
        </div>

        {/* Cross-Encoder Reranker Toggle */}
        <div className="flex items-center justify-between p-3 rounded-xl bg-slate-900/60 border border-white/5">
          <div>
            <div className="text-xs font-semibold text-white">Cross-Encoder Re-ranking</div>
            <div className="text-[11px] text-slate-400">
              Score candidate chunks with Cohere / BGE-Reranker for maximum precision
            </div>
          </div>
          <button
            type="button"
            onClick={() => setRerank(!rerank)}
            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
              rerank ? 'bg-indigo-600' : 'bg-slate-700'
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                rerank ? 'translate-x-5' : 'translate-x-0'
              }`}
            />
          </button>
        </div>

        {/* Similarity Threshold */}
        <div>
          <div className="flex justify-between items-center mb-1.5">
            <label className="text-xs font-semibold text-slate-300">Minimum Cosine Similarity</label>
            <span className="text-xs font-mono font-bold text-cyan-400 px-2 py-0.5 rounded bg-cyan-500/10 border border-cyan-500/20">
              {(similarityThreshold * 100).toFixed(0)}%
            </span>
          </div>
          <input
            type="range"
            min={0.3}
            max={0.95}
            step={0.05}
            value={similarityThreshold}
            onChange={(e) => setSimilarityThreshold(Number(e.target.value))}
            className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-500"
          />
          <p className="text-[11px] text-slate-500 mt-1">
            Prunes low-relevance chunks before generative reasoning.
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex justify-end gap-2.5 pt-3 border-t border-white/5">
          <Button variant="secondary" size="md" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" size="md" icon={<Check className="w-4 h-4" />} onClick={handleSave}>
            Apply Settings
          </Button>
        </div>
      </div>
    </Modal>
  );
};
