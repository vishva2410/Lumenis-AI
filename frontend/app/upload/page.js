'use client';

import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { ImagePlus, FileText, ShieldCheck } from 'lucide-react';
import Dropzone from '@/components/Dropzone';
import styles from './upload.module.css';

const TABS = [
  {
    key: 'imagery',
    label: 'Medical Imagery',
    icon: ImagePlus,
    formats: ['.dcm', '.jpg', '.jpeg', '.png'],
  },
  {
    key: 'reports',
    label: 'Clinical Reports',
    icon: FileText,
    formats: ['.pdf'],
  },
];

export default function UploadPage() {
  const [activeTab, setActiveTab] = useState('imagery');
  const tabRefs = useRef({});
  const [highlightStyle, setHighlightStyle] = useState({});

  /* ── Animate highlight pill to the active tab ──────── */
  useEffect(() => {
    const activeEl = tabRefs.current[activeTab];
    if (activeEl) {
      setHighlightStyle({
        left: activeEl.offsetLeft,
        width: activeEl.offsetWidth,
      });
    }
  }, [activeTab]);

  return (
    <div className={styles.uploadPage}>
      {/* ── Page Header ─────────────────────────────────── */}
      <div className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>New Analysis</h1>
        <p className={styles.pageSubtitle}>
          Upload medical imagery or clinical reports for AI-powered diagnostic
          analysis
        </p>
      </div>

      {/* ── Tab Bar ──────────────────────────────────────── */}
      <div className={styles.tabBar}>
        {/* Animated highlight pill */}
        <motion.div
          className={styles.tabHighlight}
          animate={highlightStyle}
          transition={{ type: 'spring', stiffness: 350, damping: 30 }}
        />

        {TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              ref={(el) => {
                tabRefs.current[tab.key] = el;
              }}
              className={`${styles.tab} ${isActive ? styles.tabActive : ''}`}
              onClick={() => setActiveTab(tab.key)}
              aria-selected={isActive}
              role="tab"
            >
              <Icon size={16} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* ── Tab Content (animated) ─────────────────────── */}
      <div className={styles.tabContent}>
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, x: activeTab === 'imagery' ? -20 : 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: activeTab === 'imagery' ? 20 : -20 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            style={{ width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center' }}
          >
            <Dropzone mode={activeTab} />
          </motion.div>
        </AnimatePresence>
      </div>

      {/* ── Security Footer ─────────────────────────────── */}
      <div className={styles.securityFooter}>
        <ShieldCheck size={18} />
        <span className={styles.securityText}>
          End-to-end encrypted · HIPAA compliant · No data used for training
        </span>
      </div>
    </div>
  );
}
