import React, { useState } from 'react';
import { Mail, Lock, User as UserIcon, Sparkles, AlertCircle } from 'lucide-react';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';
import { useAuth } from '../../contexts/AuthContext';
import { useToast } from '../../contexts/ToastContext';

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AuthModal: React.FC<AuthModalProps> = ({ isOpen, onClose }) => {
  const { login, register, enableDemoMode } = useAuth();
  const toast = useToast();

  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setIsLoading(true);

    try {
      if (mode === 'login') {
        await login(email, password);
        toast.success('Signed in successfully');
      } else {
        await register(email, password, fullName);
        toast.success('Account registered & logged in');
      }
      onClose();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Authentication failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleDemo = () => {
    enableDemoMode();
    toast.info('Entered Demo Interactive Workspace');
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={mode === 'login' ? 'Sign In to RAG Platform' : 'Create Enterprise Account'}
      subtitle="Access private workspace knowledge collections and vector search"
      maxWidth="md"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Error Alert */}
        {errorMsg && (
          <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* Tab switch */}
        <div className="flex p-1 rounded-xl bg-slate-900 border border-white/5">
          <button
            type="button"
            onClick={() => setMode('login')}
            className={`flex-1 py-1.5 rounded-lg text-xs font-medium transition-all ${
              mode === 'login'
                ? 'bg-indigo-600 text-white shadow'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => setMode('register')}
            className={`flex-1 py-1.5 rounded-lg text-xs font-medium transition-all ${
              mode === 'register'
                ? 'bg-indigo-600 text-white shadow'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            Register
          </button>
        </div>

        {/* Full Name for register */}
        {mode === 'register' && (
          <div>
            <label className="text-xs font-medium text-slate-300 block mb-1">Full Name</label>
            <div className="relative">
              <UserIcon className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
              <input
                type="text"
                required
                placeholder="Nguyen Van A"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="w-full pl-9 pr-3 py-2 rounded-xl glass-input text-xs"
              />
            </div>
          </div>
        )}

        {/* Email */}
        <div>
          <label className="text-xs font-medium text-slate-300 block mb-1">Email Address</label>
          <div className="relative">
            <Mail className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
            <input
              type="email"
              required
              placeholder="user@enterprise.io"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full pl-9 pr-3 py-2 rounded-xl glass-input text-xs"
            />
          </div>
        </div>

        {/* Password */}
        <div>
          <label className="text-xs font-medium text-slate-300 block mb-1">Password</label>
          <div className="relative">
            <Lock className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
            <input
              type="password"
              required
              minLength={6}
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full pl-9 pr-3 py-2 rounded-xl glass-input text-xs"
            />
          </div>
        </div>

        {/* Submit Button */}
        <Button
          type="submit"
          variant="primary"
          size="md"
          isLoading={isLoading}
          className="w-full mt-2"
        >
          {mode === 'login' ? 'Sign In with Session' : 'Create Account'}
        </Button>

        {/* Demo Mode Button */}
        <div className="pt-3 border-t border-white/5 text-center">
          <button
            type="button"
            onClick={handleDemo}
            className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center justify-center gap-1.5 mx-auto font-medium transition-colors"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Or test immediately in Demo Mode</span>
          </button>
        </div>
      </form>
    </Modal>
  );
};
