'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'motion/react';
import { fetchJob, fetchReport } from '@/lib/api';
import ReportView from '@/components/ReportView';
import ChatBox from '@/components/ChatBox';
import ImageViewer from '@/components/ImageViewer';
import AnalysisCharts from '@/components/AnalysisCharts';
import {
  Activity, AlertTriangle, FileImage, ArrowLeft, CheckCircle2,
  Clock, Shield, BarChart3, Target, ChevronRight, Loader2, RefreshCw,
} from 'lucide-react';
import './JobPage.css';

/* ── Animation presets ────────────────────────────────── */
const fadeIn = {
  initial: { opacity: 0, y: 16 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.4, ease: [0.16, 1, 0.3, 1] },
};

const stagger = {
  animate: { transition: { staggerChildren: 0.08 } },
};

/* ── Processing Steps ─────────────────────────────────── */
const PIPELINE_STEPS = [
  { id: 1, label: 'Image Pre-processing' },
  { id: 2, label: 'Feature Extraction' },
  { id: 3, label: 'RAG Clinical Grounding' },
  { id: 4, label: 'Self-Critique QA' },
  { id: 5, label: 'Report Synthesis' },
];

/* ── Helpers ──────────────────────────────────────────── */
function SeverityBadge({ severity }) {
  const map = {
    low: 'badge badge-success',
    moderate: 'badge badge-warning',
    high: 'badge badge-danger',
    critical: 'badge badge-critical',
  };
  return (
    <span className={map[severity] || 'badge badge-neutral'}>
      {severity || 'unknown'}
    </span>
  );
}

function ConfidenceGauge({ value }) {
  const pct = Math.round((value || 0) * 100);
  const color = pct >= 85 ? 'var(--success)' : pct >= 60 ? 'var(--warning)' : 'var(--danger)';
  const label = pct >= 85 ? 'High' : pct >= 60 ? 'Moderate' : 'Low';

  return (
    <div className="confidence-gauge">
      <svg viewBox="0 0 36 36" className="gauge-svg">
        <path
          d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
          fill="none"
          stroke="var(--border)"
          strokeWidth="3"
        />
        <path
          d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
          fill="none"
          stroke={color}
          strokeWidth="3"
          strokeDasharray={`${pct}, 100`}
          strokeLinecap="round"
          style={{ transition: 'stroke-dasharray 1s ease-out' }}
        />
      </svg>
      <div className="gauge-center">
        <span className="gauge-value tabular-nums">{pct}%</span>
      </div>
      <span className="gauge-label" style={{ color }}>{label} Confidence</span>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   MAIN PAGE COMPONENT
   ═══════════════════════════════════════════════════════ */

export default function JobPage() {
  const params = useParams();
  const router = useRouter();
  const id = params?.id;
  const [job, setJob] = useState(null);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sseStatus, setSseStatus] = useState({ step: 0, message: 'Initializing analysis...' });

  useEffect(() => {
    if (!id || id === 'undefined') return;

    const loadData = async () => {
      try {
        const jobData = await fetchJob(id);
        setJob(jobData);
        setLoading(false);

        if (jobData.status === 'completed') {
          try {
            const reportData = await fetchReport(id);
            setReport(reportData);
          } catch {
            /* report may not exist yet */
          }
        }
      } catch (err) {
        console.error(err);
        setError('Failed to load analysis data.');
        setLoading(false);
      }
    };

    loadData();

    /* ── SSE for real-time processing status ──────────── */
    const sseUrl = `/api/jobs/${id}/stream`;
    const eventSource = new EventSource(sseUrl);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setSseStatus({ step: data.step, message: data.message });

        if (data.step === 6 || data.step === -1) {
          eventSource.close();
          loadData();
        }
      } catch { /* heartbeat */ }
    };

    eventSource.onerror = () => eventSource.close();

    return () => eventSource.close();
  }, [id]);

  /* ── Loading State ──────────────────────────────────── */
  if (loading && !job) {
    return (
      <div className="job-page">
        <div className="skeleton-header">
          <div className="skeleton" style={{ width: 200, height: 24 }} />
          <div className="skeleton" style={{ width: 300, height: 16, marginTop: 8 }} />
        </div>
        <div className="skeleton-grid">
          <div className="skeleton" style={{ height: 300 }} />
          <div className="skeleton" style={{ height: 300 }} />
        </div>
      </div>
    );
  }

  /* ── Error State ────────────────────────────────────── */
  if (error) {
    return (
      <motion.div className="job-state-card error-state" {...fadeIn}>
        <AlertTriangle size={48} color="var(--danger)" />
        <h2>Error Loading Analysis</h2>
        <p>{error}</p>
        <button className="btn btn-primary" onClick={() => router.push('/')}>
          Back to Dashboard
        </button>
      </motion.div>
    );
  }

  /* ── Processing / Pending State ─────────────────────── */
  if (job?.status === 'processing' || job?.status === 'pending') {
    return (
      <motion.div className="job-page" {...fadeIn}>
        <div className="processing-card card">
          <div className="card-body" style={{ textAlign: 'center', padding: 'var(--space-10)' }}>
            <div className="processing-icon">
              <Activity size={40} color="var(--primary)" />
            </div>
            <h2 style={{ marginTop: 'var(--space-4)' }}>Analyzing Your Scan</h2>
            <p style={{ color: 'var(--text-secondary)', marginTop: 'var(--space-2)' }}>
              Processing <strong>{job.original_filename}</strong>
            </p>

            <div className="timeline">
              {PIPELINE_STEPS.map((step) => {
                const isComplete = sseStatus.step > step.id;
                const isActive = sseStatus.step === step.id;
                return (
                  <div
                    key={step.id}
                    className={`timeline-step ${isComplete ? 'complete' : ''} ${isActive ? 'active' : ''}`}
                  >
                    <div className="timeline-line" />
                    <div className="timeline-dot">
                      {isComplete ? (
                        <CheckCircle2 size={16} color="var(--success)" />
                      ) : isActive ? (
                        <Loader2 size={16} className="spinner" color="var(--primary)" />
                      ) : (
                        <div className="dot-empty" />
                      )}
                    </div>
                    <span className="timeline-label">{step.label}</span>
                  </div>
                );
              })}
            </div>

            <p style={{ marginTop: 'var(--space-6)', color: 'var(--text-muted)', fontStyle: 'italic', fontSize: '0.8125rem' }}>
              {sseStatus.message}
            </p>
          </div>
        </div>
      </motion.div>
    );
  }

  /* ── Failed State ───────────────────────────────────── */
  if (job?.status === 'failed') {
    return (
      <motion.div className="job-state-card error-state" {...fadeIn}>
        <AlertTriangle size={48} color="var(--danger)" />
        <h2>Analysis Failed</h2>
        <p className="error-detail">{job.error_message || 'An unknown error occurred during processing.'}</p>
        <div style={{ display: 'flex', gap: 'var(--space-3)', marginTop: 'var(--space-4)' }}>
          <button className="btn btn-secondary" onClick={() => router.push('/')}>
            <ArrowLeft size={16} /> Dashboard
          </button>
          <button className="btn btn-primary" onClick={() => router.push('/upload')}>
            <RefreshCw size={16} /> Try Again
          </button>
        </div>
      </motion.div>
    );
  }

  /* ═══════════════════════════════════════════════════════
     COMPLETED STATE — Rich Analysis Display
     ═══════════════════════════════════════════════════════ */
  const findings = report?.findings || [];
  const severityOverall = report?.severity_overall || job?.result?.severity_overall || 'low';
  const confidence = report?.confidence_score || 0;
  const summary = report?.summary || job?.result?.report_summary || 'Analysis complete.';
  const recommendations = report?.recommendations || job?.result?.recommendations || [];

  return (
    <motion.div className="job-page" {...fadeIn}>
      {/* ── Header ──────────────────────────────────────── */}
      <div className="job-header">
        <button className="btn btn-ghost btn-sm" onClick={() => router.push('/')}>
          <ArrowLeft size={16} /> Dashboard
        </button>
        <div className="job-header-info">
          <h1>Analysis Results</h1>
          <div className="job-meta">
            <FileImage size={14} />
            <span>{job?.original_filename}</span>
            <span className="meta-sep">•</span>
            <Clock size={14} />
            <span>{new Date(job?.created_at).toLocaleString()}</span>
            <span className="meta-sep">•</span>
            <span className="badge badge-success">Completed</span>
          </div>
        </div>
      </div>

      {/* ── Content Grid ────────────────────────────────── */}
      <motion.div className="results-grid" variants={stagger} initial="initial" animate="animate">

        {/* LEFT COLUMN */}
        <div className="results-main">

          {/* Executive Summary */}
          <motion.div className="card summary-card" variants={fadeIn}>
            <div className="card-header">
              <h2><Shield size={18} /> Executive Summary</h2>
            </div>
            <div className="card-body">
              <p className="summary-text">{summary}</p>
              <div className="summary-stats">
                <div className="summary-stat">
                  <span className="stat-label">Severity</span>
                  <SeverityBadge severity={severityOverall} />
                </div>
                <div className="summary-stat">
                  <ConfidenceGauge value={confidence} />
                </div>
                <div className="summary-stat">
                  <span className="stat-label">Findings</span>
                  <span className="stat-value tabular-nums">{findings.length}</span>
                </div>
              </div>
            </div>
          </motion.div>

          {/* Analysis Charts */}
          {findings.length > 0 && (
            <motion.div variants={fadeIn}>
              <AnalysisCharts report={report} />
            </motion.div>
          )}

          {/* Findings */}
          <motion.div variants={fadeIn}>
            <h2 className="section-title">
              <BarChart3 size={18} /> Detailed Findings
              <span className="findings-count">{findings.length}</span>
            </h2>
            {findings.length > 0 ? (
              <ReportView report={report} />
            ) : (
              <div className="card" style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--text-muted)' }}>
                No specific findings were detected.
              </div>
            )}
          </motion.div>

          {/* Recommendations */}
          {recommendations.length > 0 && (
            <motion.div variants={fadeIn}>
              <h2 className="section-title">
                <Target size={18} /> Recommendations
              </h2>
              <div className="recommendations-list">
                {recommendations.map((rec, i) => (
                  <div key={i} className="recommendation-item card">
                    <div className="rec-number">{i + 1}</div>
                    <p>{rec}</p>
                  </div>
                ))}
              </div>
            </motion.div>
          )}

          {/* Disclaimer */}
          <div className="disclaimer">
            <Shield size={14} />
            <span>
              {report?.disclaimer || 'This analysis is for informational purposes only and does not constitute a medical diagnosis. Always consult a qualified healthcare professional.'}
            </span>
          </div>
        </div>

        {/* RIGHT COLUMN (sticky) */}
        <div className="results-sidebar">
          <motion.div variants={fadeIn}>
            <ImageViewer jobId={job?.id} fileName={job?.original_filename} />
          </motion.div>
          <motion.div variants={fadeIn}>
            <ChatBox jobId={id} />
          </motion.div>
        </div>
      </motion.div>
    </motion.div>
  );
}
