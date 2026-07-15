'use client';

import { useState } from 'react';
import {
  AlertCircle,
  ChevronDown,
  BookOpen,
  MapPin,
  FileText,
  ShieldCheck,
  Quote,
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import './ReportView.css';

/**
 * Map a severity string to the badge class from globals.css.
 */
const severityBadgeClass = (severity) => {
  const map = {
    low: 'badge badge-success',
    moderate: 'badge badge-warning',
    high: 'badge badge-danger',
    critical: 'badge badge-critical',
  };
  return map[(severity || '').toLowerCase()] || 'badge badge-neutral';
};

/**
 * Map a severity string to a CSS class suffix for the left-border color.
 */
const severityCardClass = (severity) => {
  const s = (severity || '').toLowerCase();
  if (['low', 'moderate', 'high', 'critical'].includes(s)) return `severity-${s}`;
  return 'severity-low';
};

/**
 * Return a color for the confidence bar fill.
 */
const confidenceColor = (score) => {
  if (score >= 0.8) return 'var(--success)';
  if (score >= 0.5) return 'var(--warning)';
  return 'var(--danger)';
};

/**
 * ReportView — renders medical report findings as expandable, severity-coded cards.
 *
 * @param {{ report: import('@/lib/api').FullReport | null }} props
 */
export default function ReportView({ report }) {
  // Track which finding cards are expanded (by index)
  const [expanded, setExpanded] = useState(() => {
    // Expand the first finding by default
    if (report?.findings?.length > 0) return { 0: true };
    return {};
  });

  const toggle = (index) => {
    setExpanded((prev) => ({ ...prev, [index]: !prev[index] }));
  };

  /* ── Empty state ──────────────────────────────────── */
  if (!report || !report.findings || report.findings.length === 0) {
    return (
      <div className="reportEmpty">
        <AlertCircle size={28} strokeWidth={1.5} />
        <p className="reportEmptyTitle">No Findings Available</p>
        <p className="reportEmptyDesc">
          The report has not been generated yet or contains no significant findings.
        </p>
      </div>
    );
  }

  /* ── Findings list ────────────────────────────────── */
  return (
    <div className="findingsContainer">
      {report.findings.map((item, idx) => {
        const finding = item.finding || {};
        const isOpen = !!expanded[idx];
        const confidence = finding.confidence ?? 0;

        return (
          <motion.div
            key={idx}
            className={`findingCard ${severityCardClass(finding.severity)}`}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: idx * 0.06 }}
          >
            {/* ── Finding header (click to toggle) ── */}
            <button
              type="button"
              className="findingHeader"
              onClick={() => toggle(idx)}
              aria-expanded={isOpen}
            >
              <div className="findingTitleRow">
                <span className={severityBadgeClass(finding.severity)}>
                  {(finding.severity || 'unknown').toUpperCase()}
                </span>

                <h4 className="findingName">{finding.name || 'Unnamed Finding'}</h4>

                {finding.region && (
                  <span className="regionTag">
                    <MapPin size={11} />
                    {finding.region}
                  </span>
                )}
              </div>

              <div className="findingHeaderRight">
                {/* Confidence pill */}
                <div className="confidencePill">
                  <div className="confidenceBar">
                    <div
                      className="confidenceBarFill"
                      style={{
                        width: `${(confidence * 100).toFixed(0)}%`,
                        background: confidenceColor(confidence),
                      }}
                    />
                  </div>
                  <span className="confidenceValue">{(confidence * 100).toFixed(0)}%</span>
                </div>

                <motion.span
                  className="expandChevron"
                  animate={{ rotate: isOpen ? 180 : 0 }}
                  transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
                >
                  <ChevronDown size={18} />
                </motion.span>
              </div>
            </button>

            {/* ── Finding body (expandable) ── */}
            <AnimatePresence initial={false}>
              {isOpen && (
                <motion.div
                  className="findingBody"
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                  style={{ overflow: 'hidden' }}
                >
                  <div className="findingBodyInner">
                    {/* Description */}
                    {finding.description && (
                      <div className="findingDetailGroup">
                        <div className="detailLabel">
                          <FileText size={14} />
                          <span>Description</span>
                        </div>
                        <p className="detailText">{finding.description}</p>
                      </div>
                    )}

                    {/* Explanation (RAG context) */}
                    {item.explanation && (
                      <div className="findingDetailGroup explanationGroup">
                        <div className="detailLabel">
                          <BookOpen size={14} />
                          <span>Clinical Context</span>
                          {item.verified && (
                            <span className="verifiedBadge">
                              <ShieldCheck size={12} />
                              Verified
                            </span>
                          )}
                        </div>
                        <p className="detailText">{item.explanation}</p>
                      </div>
                    )}

                    {/* Citations */}
                    {item.citations && item.citations.length > 0 && (
                      <div className="findingDetailGroup">
                        <div className="detailLabel">
                          <Quote size={14} />
                          <span>Citations</span>
                        </div>
                        <ul className="citationsList">
                          {item.citations.map((cit, cidx) => (
                            <li key={cidx} className="citationItem">
                              <div className="citationHeader">
                                <span className="citationSource">[{cit.source_id}]</span>
                                <span className="citationRelevance">
                                  Relevance: {(cit.relevance_score * 100).toFixed(0)}%
                                </span>
                              </div>
                              <p className="citationText">&ldquo;{cit.source_text}&rdquo;</p>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        );
      })}
    </div>
  );
}
