import Link from 'next/link';
import { fetchJobs } from '@/lib/api';
import { FileImage, Activity, Clock, AlertTriangle, CheckCircle2, ChevronRight } from 'lucide-react';
import styles from './page.module.css';

export const revalidate = 0; // Disable caching to always show latest jobs

function StatusBadge({ status }) {
  const config = {
    completed: { icon: CheckCircle2, class: 'status-completed', text: 'Completed' },
    processing: { icon: Activity, class: 'status-processing', text: 'Processing' },
    failed: { icon: AlertTriangle, class: 'status-failed', text: 'Failed' },
    pending: { icon: Clock, class: 'status-pending', text: 'Pending' }
  };
  
  const current = config[status] || config.pending;
  const Icon = current.icon;
  
  return (
    <div className={styles.statusBadge}>
      <span className={`status-dot ${current.class}`}></span>
      <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', fontWeight: 500 }}>
        {current.text}
      </span>
    </div>
  );
}

export default async function Dashboard() {
  let jobs = [];
  try {
    const data = await fetchJobs(0, 20);
    jobs = data.items || [];
  } catch (error) {
    console.error("Failed to load jobs:", error);
  }

  return (
    <div className="animate-fade-in">
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Recent Analyses</h1>
          <p className={styles.subtitle}>Overview of your medical imaging analysis jobs</p>
        </div>
        <Link href="/upload" className="btn btn-primary">
          New Analysis
        </Link>
      </div>
      
      {jobs.length === 0 ? (
        <div className={`glass-panel ${styles.emptyState}`}>
          <div className={styles.emptyIconWrapper}>
            <FileImage size={48} color="var(--accent-primary)" />
          </div>
          <h3>No analyses yet</h3>
          <p>Upload a DICOM, JPEG, PNG, or PDF report to begin.</p>
          <Link href="/upload" className="btn btn-primary" style={{ marginTop: '1rem' }}>
            Upload First Image
          </Link>
        </div>
      ) : (
        <div className={styles.jobGrid}>
          {jobs.map((job) => (
            <Link href={`/job/${job.id}`} key={job.id} className="glass-card" style={{ display: 'block', textDecoration: 'none' }}>
              <div className={styles.jobCard}>
                <div className={styles.jobCardHeader}>
                  <div className={styles.jobFileName}>
                    <FileImage size={18} color="var(--text-muted)" />
                    <span>{job.file_name}</span>
                  </div>
                  <StatusBadge status={job.status} />
                </div>
                
                <div className={styles.jobCardBody}>
                  {job.status === 'completed' && job.result && (
                    <div className={styles.jobStats}>
                      <div className={styles.statBox}>
                        <span className={styles.statLabel}>Findings</span>
                        <span className={styles.statValue}>{job.result.findings?.length || 0}</span>
                      </div>
                      <div className={styles.statBox}>
                        <span className={styles.statLabel}>Severity</span>
                        <span className={`severity-badge severity-${job.result.severity_overall || 'low'}`}>
                          {job.result.severity_overall || 'low'}
                        </span>
                      </div>
                    </div>
                  )}
                  {job.status === 'processing' && (
                    <div className={styles.processingState}>
                      <Activity className="animate-pulse" size={24} color="var(--accent-warning)" />
                      <span>AI is analyzing...</span>
                    </div>
                  )}
                  {job.status === 'failed' && (
                    <div className={styles.failedState}>
                      <span className={styles.errorText}>Analysis failed. Click to view details.</span>
                    </div>
                  )}
                </div>
                
                <div className={styles.jobCardFooter}>
                  <span className={styles.dateText}>
                    {new Date(job.created_at).toLocaleDateString(undefined, { 
                      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                    })}
                  </span>
                  <ChevronRight size={18} color="var(--text-muted)" />
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
