import { useEffect, useState } from 'react';
import { App as AntApp } from 'antd';
import LayoutShell, { getAllowedPages, PageKey } from './components/LayoutShell';
import { client } from './api/client';
import type { HealthStatus } from './types';
import Dashboard from './pages/Dashboard';
import ModelGeneration1 from './pages/ModelGeneration1';
import AgentWorkbench from './pages/AgentWorkbench';
import SimulationMock from './pages/SimulationMock';
import AuthExperience, { getDemoUserSession, type DemoRole, type DemoUserSession } from './pages/AuthExperience';

export default function App() {
  const [session, setSession] = useState<DemoUserSession | null>(null);
  const [page, setPage] = useState<PageKey>('dashboard');
  const [health, setHealth] = useState<HealthStatus | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const nextHealth = await client.health();
        if (syncBackendSession(nextHealth.backend_session_id)) {
          setSession(null);
          setPage('dashboard');
        }
        setHealth(nextHealth);
      } catch {
        setHealth(null);
      }
    };
    load();
    const timer = window.setInterval(load, 10000);
    return () => window.clearInterval(timer);
  }, []);

  const handleLogin = (role: DemoRole) => {
    const nextSession = getDemoUserSession(role);
    setSession(nextSession);
    setPage(role === 'admin' ? 'dashboard' : 'agent');
  };

  const handleLogout = () => {
    setSession(null);
    setPage('dashboard');
  };

  if (!session) {
    return (
      <AntApp>
        <AuthExperience onLogin={handleLogin} />
      </AntApp>
    );
  }

  const allowedPages = getAllowedPages(session.role);
  const activePage = allowedPages.includes(page) ? page : allowedPages[0];
  const pageMap: Record<PageKey, JSX.Element> = {
    dashboard: <Dashboard />,
    model1: <ModelGeneration1 />,
    agent: <AgentWorkbench sessionRole={session.role} workspace={session.workspace} />,
    simulation: <SimulationMock />,
  };

  return (
    <AntApp>
      <LayoutShell
        activePage={activePage}
        onPageChange={setPage}
        health={health}
        role={session.role}
        userName={session.name}
        workspace={session.workspace}
        onLogout={handleLogout}
      >
        {pageMap[activePage]}
      </LayoutShell>
    </AntApp>
  );
}

const backendSessionStorageKey = 'ai-mbse-backend-session-id';
const workbenchStoragePrefix = 'ai-mbse-agent-workbench:';

function syncBackendSession(backendSessionId?: string) {
  if (!backendSessionId || typeof window === 'undefined') return false;
  const previousSessionId = window.localStorage.getItem(backendSessionStorageKey);
  window.localStorage.setItem(backendSessionStorageKey, backendSessionId);
  if (!previousSessionId) {
    if (!hasStoredWorkbenchState()) return false;
    clearStoredWorkbenchState();
    return true;
  }
  if (previousSessionId === backendSessionId) return false;
  clearStoredWorkbenchState();
  return true;
}

function hasStoredWorkbenchState() {
  return Object.keys(window.localStorage).some((key) => key.startsWith(workbenchStoragePrefix));
}

function clearStoredWorkbenchState() {
  Object.keys(window.localStorage)
    .filter((key) => key.startsWith(workbenchStoragePrefix))
    .forEach((key) => window.localStorage.removeItem(key));
}
