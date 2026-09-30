import React, { useState, useEffect, useCallback } from 'react';
import { Sidebar, type ActiveTab } from './components/layout/Sidebar';
import { Topbar } from './components/layout/Topbar';
import { ChatStudio } from './components/chat/ChatStudio';
import { DocumentsView } from './components/documents/DocumentsView';
import { ReportsView } from './components/reports/ReportsView';
import { AuthModal } from './components/auth/AuthModal';
import { healthApi } from './api/health';
import { ToastProvider } from './contexts/ToastContext';
import { AuthProvider } from './contexts/AuthContext';

const MainAppContent: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ActiveTab>('chat');
  const [systemHealth, setSystemHealth] = useState<'healthy' | 'degraded' | 'unhealthy'>('healthy');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);

  // Health probe
  const checkHealth = useCallback(async () => {
    try {
      const res = await healthApi.check();
      setSystemHealth(res.status);
    } catch {
      setSystemHealth('unhealthy');
    }
  }, []);

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 30000); // 30s probe
    return () => clearInterval(interval);
  }, [checkHealth]);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await checkHealth();
    setTimeout(() => setIsRefreshing(false), 500);
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-950 text-slate-100 bg-ambient-grid">
      {/* Left Navigation Sidebar */}
      <Sidebar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        systemHealth={systemHealth}
        onOpenAuth={() => setIsAuthModalOpen(true)}
      />

      {/* Main Workspace Area */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        <Topbar
          activeTab={activeTab}
          systemHealth={systemHealth}
          onRefresh={handleRefresh}
          isRefreshing={isRefreshing}
        />

        <main className="flex-1 overflow-hidden relative">
          {activeTab === 'chat' && <ChatStudio />}
          {activeTab === 'documents' && <DocumentsView />}
          {activeTab === 'reports' && <ReportsView />}
        </main>
      </div>

      {/* Auth Modal */}
      <AuthModal
        isOpen={isAuthModalOpen}
        onClose={() => setIsAuthModalOpen(false)}
      />
    </div>
  );
};

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <MainAppContent />
      </AuthProvider>
    </ToastProvider>
  );
}
