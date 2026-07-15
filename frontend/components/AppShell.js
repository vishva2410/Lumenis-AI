'use client';

import { useState } from 'react';
import { usePathname } from 'next/navigation';
import Sidebar from '@/components/Sidebar';
import { Menu, Bell, Activity } from 'lucide-react';

/** Map pathname prefixes to human-readable page names */
function usePageTitle() {
  const pathname = usePathname();
  if (pathname === '/') return 'Dashboard';
  if (pathname === '/upload') return 'New Analysis';
  if (pathname.startsWith('/job/')) return 'Analysis Results';
  if (pathname === '/job') return 'All Analyses';
  return 'Lumenis AI';
}

export default function AppShell({ children }) {
  const [collapsed, setCollapsed] = useState(false);
  const pageTitle = usePageTitle();

  return (
    <div className="app-shell">
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />
      <div className={`main-area ${collapsed ? 'collapsed' : ''}`}>
        <header className="top-header">
          <div className="header-breadcrumb">
            <button
              className="btn-icon btn-ghost sm"
              onClick={() => setCollapsed(!collapsed)}
              aria-label="Toggle menu"
            >
              <Menu size={18} />
            </button>
            <span style={{ color: 'var(--border)', userSelect: 'none' }}>/</span>
            <span>{pageTitle}</span>
          </div>
          <div className="header-actions">
            {/* Live system status pill */}
            <div style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '4px 10px',
              background: 'var(--success-bg)',
              border: '1px solid var(--success-border)',
              borderRadius: 'var(--radius-full)',
              fontSize: '0.75rem',
              fontWeight: 600,
              color: 'var(--success)',
              letterSpacing: '0.02em',
            }}>
              <span className="status-dot status-completed pulse-glow" style={{ width: 7, height: 7 }} />
              System Operational
            </div>

            <button className="btn-icon btn-ghost sm" aria-label="Notifications">
              <Bell size={18} />
            </button>

            {/* User avatar */}
            <div style={{
              width: 32, height: 32,
              borderRadius: 'var(--radius-full)',
              background: 'var(--gradient-primary)',
              color: 'white',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '0.6875rem', fontWeight: 700,
              letterSpacing: '0.04em',
              boxShadow: '0 2px 6px rgba(37, 99, 235, 0.35)',
              flexShrink: 0,
            }}>
              LA
            </div>
          </div>
        </header>
        <main className="page-content fade-in-up">
          {children}
        </main>
      </div>
    </div>
  );
}
