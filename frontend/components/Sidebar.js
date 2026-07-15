'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, Upload, FolderOpen, Settings, HelpCircle, ChevronLeft, ChevronRight, Hexagon } from 'lucide-react';
import './Sidebar.css';

const navItems = [
  { href: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { href: '/upload', icon: Upload, label: 'New Analysis' },
  { href: '/', icon: FolderOpen, label: 'All Analyses', matchPrefix: '/job' },
];

const bottomItems = [
  { href: '#', icon: Settings, label: 'Settings' },
  { href: '#', icon: HelpCircle, label: 'Help' },
];

export default function Sidebar({ collapsed, onToggle }) {
  const pathname = usePathname();

  const isActive = (item) => {
    if (item.matchPrefix && pathname.startsWith(item.matchPrefix)) return true;
    return pathname === item.href;
  };

  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-header">
        <Link href="/" className="sidebar-brand">
          <div className="brand-icon">
            <Hexagon size={22} strokeWidth={2.5} />
          </div>
          {!collapsed && <span className="brand-name">LUMENIS AI</span>}
        </Link>
      </div>

      <nav className="sidebar-nav">
        <ul className="nav-list">
          {navItems.map((item) => (
            <li key={item.href + item.label}>
              <Link
                href={item.href}
                className={`nav-item ${isActive(item) ? 'active' : ''}`}
                title={collapsed ? item.label : undefined}
              >
                <item.icon size={20} strokeWidth={1.8} />
                {!collapsed && <span>{item.label}</span>}
              </Link>
            </li>
          ))}
        </ul>
      </nav>

      <div className="sidebar-footer">
        <ul className="nav-list">
          {bottomItems.map((item) => (
            <li key={item.label}>
              <Link href={item.href} className="nav-item" title={collapsed ? item.label : undefined}>
                <item.icon size={20} strokeWidth={1.8} />
                {!collapsed && <span>{item.label}</span>}
              </Link>
            </li>
          ))}
        </ul>
        <button className="collapse-btn" onClick={onToggle} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>
    </aside>
  );
}
