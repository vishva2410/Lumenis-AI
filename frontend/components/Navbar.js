import Link from 'next/link';
import { Activity } from 'lucide-react';
import './Navbar.css';

export default function Navbar() {
  return (
    <nav className="navbar">
      <div className="container navbar-container">
        <Link href="/" className="navbar-brand">
          <div className="logo-icon">
            <Activity size={24} color="var(--accent-primary)" />
          </div>
          <span className="brand-text">Med<span className="text-gradient">Lens</span></span>
        </Link>
        <div className="navbar-links">
          <Link href="/" className="nav-link">Dashboard</Link>
          <Link href="/upload" className="btn btn-primary btn-sm">New Analysis</Link>
        </div>
      </div>
    </nav>
  );
}
