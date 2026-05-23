import Link from 'next/link';
import { Box } from 'lucide-react';
import './Navbar.css';

export default function Navbar() {
  return (
    <nav className="navbar">
      <div className="container navbar-container">
        <Link href="/" className="navbar-brand">
          <div className="logo-icon">
            <Box size={24} color="var(--accent-primary)" strokeWidth={2.5} />
          </div>
          <span className="brand-text">LUMENIS AI</span>
        </Link>
        <div className="navbar-links">
          <Link href="/" className="nav-link">Dashboard</Link>
          <Link href="/upload" className="btn btn-primary btn-sm">New Analysis</Link>
        </div>
      </div>
    </nav>
  );
}
