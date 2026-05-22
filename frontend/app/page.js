import Link from 'next/link';
import { fetchJobs } from '@/lib/api';
import { FileImage, Activity, AlertTriangle, CheckCircle2, ChevronRight, BarChart2, CheckSquare, Clock } from 'lucide-react';
import styles from './page.module.css';

export const revalidate = 0;

function StatusBadge({ status }) {
  const config = {
    completed: { icon: CheckCircle2, text: 'Completed', class: 'status-completed' },
    processing: { icon: Activity, text: 'Processing', class: 'status-processing' },
    failed: { icon: AlertTriangle, text: 'Failed', class: 'status-failed' },
    pending: { icon: Clock, text: 'Pending', class: 'status-pending' }
  };
  
  const current = config[status] || config.pending;
  
  return (
    <div className={styles.statusBadge}>
      <span className={`status-dot ${current.class}`}></span>
      <span>{current.text}</span>
    </div>
  );
}

export default async function Dashboard() {
  let jobs = [];
  try {
    const data = await fetchJobs(0, 50);
    jobs = data.jobs || data.items || [];
  } catch (error) {
    console.error("Failed to load jobs:", error);
  }

  // Calculate Metrics
  const totalAnalyses = jobs.length;
  const completedAnalyses = jobs.filter(j => j.status === 'completed').length;
  const successRate = totalAnalyses > 0 ? Math.round((completedAnalyses / totalAnalyses) * 100) : 0;
  
  const criticalCount = jobs.filter(j => j.result?.severity_overall === 'critical').length;
  const highCount = jobs.filter(j => j.result?.severity_overall === 'high').length;

  return (
    <div className="animate-fade-in">
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>System Analytics</h1>
          <p className={styles.subtitle}>Organization-level performance and processing metrics</p>
        </div>
        <Link href="/upload" className="btn btn-primary">
          Run Analysis
        </Link>
      </div>

      <div className={styles.metricsGrid}>
        <div className={styles.metricCard}>
          <div className={styles.metricHeader}>
            <BarChart2 size={16} /> Total Processed
          </div>
          <div className={styles.metricValue}>{totalAnalyses}</div>
        </div>
        <div className={styles.metricCard}>
          <div className={styles.metricHeader}>
            <CheckSquare size={16} /> Processing Success Rate
          </div>
          <div className={styles.metricValue}>{successRate}%</div>
        </div>
        <div className={styles.metricCard}>
          <div className={styles.metricHeader}>
            <AlertTriangle size={16} /> High/Critical Findings
          </div>
          <div className={styles.metricValue}>{criticalCount + highCount}</div>
        </div>
      </div>
      
      <h2 className={styles.sectionTitle}>Recent Jobs</h2>
      
      {jobs.length === 0 ? (
        <div className={styles.emptyState}>
          <div className={styles.emptyIconWrapper}>
            <FileImage size={48} color="var(--text-muted)" strokeWidth={1.5} />
          </div>
          <h3>No Data Available</h3>
          <p>The system has not processed any files yet.</p>
          <Link href="/upload" className="btn btn-primary" style={{ marginTop: '1.5rem' }}>
            Initialize Upload
          </Link>
        </div>
      ) : (
        <div className={styles.jobGrid}>
          {jobs.slice(0, 12).map((job) => (
            <Link href={`/job/${job.id}`} key={job.id} style={{ textDecoration: 'none' }}>
              <div className={styles.jobCard}>
                <div className={styles.jobCardHeader}>
                  <div className={styles.jobFileName}>
                    <FileImage size={18} color="var(--text-secondary)" />
                    <span>{job.original_filename}</span>
                  </div>
                  <StatusBadge status={job.status} />
                </div>
                
                <div className={styles.jobCardBody}>
                  {job.status === 'completed' && job.result && (
                    <div className={styles.jobStats}>
                      <div className={styles.statBox}>
                        <span className={styles.statLabel}>Findings Detected</span>
                        <span className={styles.statValue}>{job.result.findings?.length || 0}</span>
                      </div>
                      <div className={styles.statBox}>
                        <span className={styles.statLabel}>System Priority</span>
                        <span className={`severity-badge severity-${job.result.severity_overall || 'low'}`}>
                          {job.result.severity_overall || 'low'}
                        </span>
                      </div>
                    </div>
                  )}
                  {job.status === 'processing' && (
                    <div className={styles.processingState}>
                      <span>Processing File...</span>
                    </div>
                  )}
                  {job.status === 'failed' && (
                    <div className={styles.failedState}>
                      <span className={styles.errorText}>System Error during pipeline execution.</span>
                    </div>
                  )}
                </div>
                
                <div className={styles.jobCardFooter}>
                  <span className={styles.dateText}>
                    {new Date(job.created_at).toLocaleDateString(undefined, { 
                      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                    })}
                  </span>
                  <ChevronRight size={18} color="var(--text-secondary)" />
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
