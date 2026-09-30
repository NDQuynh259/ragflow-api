import React from 'react';

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'error' | 'indigo' | 'cyan' | 'purple';
  size?: 'sm' | 'md';
  pulse?: boolean;
  className?: string;
  onClick?: () => void;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'default',
  size = 'md',
  pulse = false,
  className = '',
  onClick,
}) => {
  const variantStyles = {
    default: 'bg-slate-800 text-slate-300 border-slate-700/60',
    success: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    warning: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
    error: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
    indigo: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30',
    cyan: 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30',
    purple: 'bg-purple-500/15 text-purple-300 border-purple-500/30',
  };

  const sizeStyles = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-xs px-2.5 py-1',
  };

  return (
    <span
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 font-medium rounded-full border transition-all ${
        variantStyles[variant]
      } ${sizeStyles[size]} ${onClick ? 'cursor-pointer hover:brightness-125' : ''} ${className}`}
    >
      {pulse && (
        <span className="relative flex h-2 w-2">
          <span
            className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
              variant === 'success' ? 'bg-emerald-400' : variant === 'warning' ? 'bg-amber-400' : 'bg-indigo-400'
            }`}
          />
          <span
            className={`relative inline-flex rounded-full h-2 w-2 ${
              variant === 'success' ? 'bg-emerald-500' : variant === 'warning' ? 'bg-amber-500' : 'bg-indigo-500'
            }`}
          />
        </span>
      )}
      {children}
    </span>
  );
};
