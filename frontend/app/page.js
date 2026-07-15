import Link from 'next/link';
import { fetchJobs } from '@/lib/api';
import {
  Activity,
  BarChart3,
  AlertTriangle,
  CheckCircle2,
  FileImage,
  ChevronRight,
  Clock,
  Shield,
  TrendingUp,
  Zap,
} from 'lucide-react';
import styles from './page.module.css';
import DashboardCharts from '@/components/DashboardChartsWrapper';

export const revalidate = 0;

/* ─── Helper: Status Badge ────────────────────────────── */

function StatusBadge({ status }) {
  const config = {
    completed: { text: 'Completed', className: styles.statusCompleted },
    processing: { text: 'Processing', className: styles.statusProcessing },
    failed: { text: 'Failed', className: styles.statusFailed },
    pending: { text: 'Pending', className: styles.statusPending },
  };

  const current = config[status] || config.pending;

  return (
    <span className={`${styles.statusBadge} ${current.className}`}>
      <span
        className={`status-dot ${
          status === 'completed'
            ? 'status-completed'
            : status === 'processing'
            ? 'status-processing'
            : status === 'failed'
            ? 'status-failed'
            : 'status-pending'
        }`}
      />
      {current.text}
    </span>
  );
}

/* ─── Helper: Severity Badge ──────────────────────────── */

function SeverityBadge({ severity }) {
  if (!severity) return null;

  const map = {
    low: { label: 'Low', className: styles.severityLow },
    moderate: { label: 'Moderate', className: styles.severityModerate },
    high: { label: 'High', className: styles.severityHigh },
    critical: { label: 'Critical', className: styles.severityCritical },
  };

  const config = map[severity] || map.low;

  return (
    <span className={`${styles.severityBadge} ${config.className}`}>
      <Shield size={10} />
      {config.label}
    </span>
  );
}

/* ─── Helper: Format relative time ────────────────────── */

function formatRelativeDate(dateStr) {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  });
}

/* ─── Helper: Format file type display ────────────────── */

function getFileType(filename) {
  if (!filename) return 'File';
  const ext = filename.split('.').pop()?.toLowerCase();
  const typeMap = {
    dcm: 'DICOM',
    dicom: 'DICOM',
    jpg: 'JPEG',
    jpeg: 'JPEG',
    png: 'PNG',
    nii: 'NIfTI',
    'nii.gz': 'NIfTI',
    pdf: 'PDF',
  };
  return typeMap[ext] || ext?.toUpperCase() || 'File';
}

/* ═══════════════════════════════════════════════════════
   DASHBOARD PAGE (Server Component)
   ═══════════════════════════════════════════════════════ */

export default async function Dashboard() {
  let jobs = [];
  let total = 0;

  try {
    const data = await fetchJobs(0, 50);
    jobs = data.jobs || data.items || [];
    total = data.total || jobs.length;
  } catch (error) {
    console.error('Failed to load jobs:', error);
  }

  /* ─── Compute Metrics ──────────────────────────── */
  const totalAnalyses = jobs.length;
  const completedJobs = jobs.filter((j) => j.status === 'completed');
  const completedCount = completedJobs.length;
  const successRate =
    totalAnalyses > 0 ? Math.round((completedCount / totalAnalyses) * 100) : 0;

  // Average findings across completed jobs
  const totalFindings = completedJobs.reduce((sum, j) => {
    return sum + (j.result?.findings?.length || 0);
  }, 0);
  const avgFindings =
    completedCount > 0 ? (totalFindings / completedCount).toFixed(1) : '0';

  // Critical + High count
  const criticalHighCount = jobs.filter(
    (j) =>
      j.result?.severity_overall === 'critical' ||
      j.result?.severity_overall === 'high'
  ).length;

  /* ─── Recent jobs (up to 8) ────────────────────── */
  const recentJobs = jobs.slice(0, 8);

  return (
    <div>
      {/* ════ Page Header ════ */}
      <header className={styles.pageHeader}>
        <div className={styles.headerInfo}>
          <h1 className={styles.pageTitle}>Dashboard</h1>
          <p className={styles.pageSubtitle}>
            Overview of your medical imaging analyses and diagnostics
          </p>
        </div>
        <Link href="/upload" className={styles.newAnalysisBtn}>
          <Zap size={16} />
          New Analysis
        </Link>
      </header>

      {/* ════ Stats Grid ════ */}
      <section className={styles.statsGrid} aria-label="Key metrics">
        {/* Stat 1: Total Analyses */}
        <div className={styles.statCard}>
          <div className={styles.statCardHeader}>
            <span className={styles.statLabel}>Total Analyses</span>
            <div className={`${styles.statIconWrapper} ${styles.statIconBlue}`}>
              <BarChart3 size={18} />
            </div>
          </div>
          <div className={styles.statValue}>{totalAnalyses}</div>
        </div>

        {/* Stat 2: Success Rate */}
        <div className={styles.statCard}>
          <div className={styles.statCardHeader}>
            <span className={styles.statLabel}>Success Rate</span>
            <div className={`${styles.statIconWrapper} ${styles.statIconGreen}`}>
              <CheckCircle2 size={18} />
            </div>
          </div>
          <div className={styles.statValue}>{successRate}%</div>
          <span
            className={`${styles.statTrend} ${
              successRate >= 90
                ? styles.trendUp
                : successRate >= 70
                ? styles.trendNeutral
                : styles.trendDown
            }`}
          >
            <TrendingUp size={12} />
            {completedCount} of {totalAnalyses} completed
          </span>
        </div>


        {/* Stat 4: Critical/High */}
        <div className={styles.statCard}>
          <div className={styles.statCardHeader}>
            <span className={styles.statLabel}>Critical / High</span>
            <div className={`${styles.statIconWrapper} ${styles.statIconRed}`}>
              <AlertTriangle size={18} />
            </div>
          </div>
          <div className={styles.statValue}>{criticalHighCount}</div>
          <span
            className={`${styles.statTrend} ${
              criticalHighCount > 0 ? styles.trendDown : styles.trendUp
            }`}
          >
            <Shield size={12} />
            {criticalHighCount > 0
              ? 'Requires attention'
              : 'No urgent findings'}
          </span>
        </div>
      </section>

      {/* ════ Content Grid ════ */}
      {jobs.length === 0 ? (
        /* ──── Empty State ──── */
        <div className={styles.emptyState}>
          <div className={styles.emptyIconWrapper}>
            <FileImage size={36} color="var(--primary)" strokeWidth={1.5} />
          </div>
          <h2 className={styles.emptyTitle}>No analyses yet</h2>
          <p className={styles.emptyDescription}>
            Upload your first medical image to get started with AI-powered
            diagnostic analysis and clinical reporting.
          </p>
          <Link href="/upload" className={styles.emptyCta}>
            <Zap size={16} />
            Start Your First Analysis
          </Link>
        </div>
      ) : (
        <div className={styles.contentGrid}>
          {/* ──── Left: Charts ──── */}
          <div className={styles.chartSection}>
            <DashboardCharts jobs={jobs} />
          </div>

          {/* ──── Right: Recent Analyses ──── */}
          <section className={styles.jobsSection}>
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>Recent Analyses</h2>
              <Link href="/job" className={styles.viewAllLink}>
                View All
                <ChevronRight size={14} />
              </Link>
            </div>

            <div className={styles.jobsList}>
              {recentJobs.map((job) => {
                const findingsCount = job.result?.findings?.length || 0;
                const severity = job.result?.severity_overall;
                const fileType = getFileType(job.original_filename);

                return (
                  <Link
                    href={`/job/${job.id}`}
                    key={job.id}
                    className={styles.jobItem}
                  >
                    {/* File Icon */}
                    <div className={styles.jobFileIcon}>
                      <FileImage size={18} />
                    </div>

                    {/* Info */}
                    <div className={styles.jobInfo}>
                      <span className={styles.jobFileName}>
                        {job.original_filename || 'Untitled scan'}
                      </span>
                      <span className={styles.jobMeta}>
                        <Clock size={11} />
                        {formatRelativeDate(job.created_at)}
                        <span className={styles.metaDot} />
                        {fileType}
                      </span>
                    </div>

                    {/* Stats */}
                    <div className={styles.jobStats}>
                      {job.status === 'completed' && (
                        <>
                          <span className={styles.findingsCount}>
                            <Activity size={13} />
                            {findingsCount}{' '}
                            {findingsCount === 1 ? 'finding' : 'findings'}
                          </span>
                          <SeverityBadge severity={severity} />
                        </>
                      )}
                      <StatusBadge status={job.status} />
                    </div>

                    {/* Chevron */}
                    <ChevronRight
                      size={16}
                      className={styles.jobChevron}
                    />
                  </Link>
                );
              })}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   CHART PLACEHOLDER (Server-safe)
   Renders a simple summary when DashboardCharts isn't yet
   available — swap with the real client component import.
   ═══════════════════════════════════════════════════════ */

function DashboardChartsPlaceholder({ jobs }) {
  // Build a simple severity distribution for server rendering
  const severityCounts = { low: 0, moderate: 0, high: 0, critical: 0 };
  jobs.forEach((j) => {
    const sev = j.result?.severity_overall;
    if (sev && severityCounts[sev] !== undefined) {
      severityCounts[sev]++;
    }
  });

  const severityColors = {
    low: 'var(--success)',
    moderate: 'var(--warning)',
    high: 'var(--danger)',
    critical: 'var(--critical)',
  };

  const totalSev = Object.values(severityCounts).reduce((a, b) => a + b, 0);

  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-5)',
      }}
    >
      {/* Mini severity distribution bar */}
      <div>
        <div
          style={{
            fontSize: '0.8125rem',
            fontWeight: 500,
            color: 'var(--text-secondary)',
            marginBottom: 'var(--space-3)',
          }}
        >
          Severity Distribution
        </div>
        {totalSev > 0 ? (
          <div
            style={{
              display: 'flex',
              height: '8px',
              borderRadius: 'var(--radius-full)',
              overflow: 'hidden',
              background: 'var(--muted)',
            }}
          >
            {Object.entries(severityCounts).map(([sev, count]) =>
              count > 0 ? (
                <div
                  key={sev}
                  style={{
                    width: `${(count / totalSev) * 100}%`,
                    background: severityColors[sev],
                    transition: 'width 0.3s ease',
                  }}
                />
              ) : null
            )}
          </div>
        ) : (
          <div
            style={{
              height: '8px',
              borderRadius: 'var(--radius-full)',
              background: 'var(--muted)',
            }}
          />
        )}

        {/* Legend */}
        <div
          style={{
            display: 'flex',
            gap: 'var(--space-4)',
            marginTop: 'var(--space-3)',
            flexWrap: 'wrap',
          }}
        >
          {Object.entries(severityCounts).map(([sev, count]) => (
            <div
              key={sev}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--space-2)',
                fontSize: '0.75rem',
                color: 'var(--text-secondary)',
              }}
            >
              <span
                style={{
                  width: '8px',
                  height: '8px',
                  borderRadius: '50%',
                  background: severityColors[sev],
                  flexShrink: 0,
                }}
              />
              <span style={{ textTransform: 'capitalize' }}>{sev}</span>
              <span
                style={{
                  fontWeight: 600,
                  color: 'var(--text-primary)',
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {count}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Summary stats cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(2, 1fr)',
          gap: 'var(--space-3)',
          marginTop: 'auto',
        }}
      >
        <div
          style={{
            padding: 'var(--space-4)',
            background: 'var(--muted)',
            borderRadius: 'var(--radius-md)',
          }}
        >
          <div
            style={{
              fontSize: '0.75rem',
              color: 'var(--text-muted)',
              fontWeight: 500,
              marginBottom: 'var(--space-1)',
            }}
          >
            Total Findings
          </div>
          <div
            style={{
              fontSize: '1.5rem',
              fontWeight: 700,
              color: 'var(--text-primary)',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {jobs.reduce((s, j) => s + (j.result?.findings?.length || 0), 0)}
          </div>
        </div>
        <div
          style={{
            padding: 'var(--space-4)',
            background: 'var(--muted)',
            borderRadius: 'var(--radius-md)',
          }}
        >
          <div
            style={{
              fontSize: '0.75rem',
              color: 'var(--text-muted)',
              fontWeight: 500,
              marginBottom: 'var(--space-1)',
            }}
          >
            Avg Confidence
          </div>
          <div
            style={{
              fontSize: '1.5rem',
              fontWeight: 700,
              color: 'var(--text-primary)',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {jobs.length > 0
              ? (
                  jobs.reduce(
                    (s, j) => s + (j.result?.metadata?.quality_score || 0),
                    0
                  ) / jobs.length
                ).toFixed(0)
              : 0}
            %
          </div>
        </div>
      </div>
    </div>
  );
}
