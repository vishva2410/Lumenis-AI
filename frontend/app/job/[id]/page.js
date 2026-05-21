'use client';

import { useState, useEffect } from 'react';
import { fetchJob, fetchReport } from '@/lib/api';
import ReportView from '@/components/ReportView';
import ChatBox from '@/components/ChatBox';
import ImageViewer from '@/components/ImageViewer';
import { Activity, AlertTriangle, FileImage, LayoutPanelLeft } from 'lucide-react';
import './JobPage.css';

export default function JobPage({ params }) {
  const { id } = params;
  const [job, setJob] = useState(null);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [sseStatus, setSseStatus] = useState({ step: 1, message: "Initializing analysis..." });

  useEffect(() => {
    const loadData = async () => {
      try {
        const jobData = await fetchJob(id);
        setJob(jobData);
        
        if (jobData.status === 'completed') {
          const reportData = await fetchReport(id);
          setReport(reportData);
          setLoading(false);
        } else if (jobData.status === 'failed') {
          setLoading(false);
        }
      } catch (err) {
        console.error(err);
        setError('Failed to load job data.');
        setLoading(false);
      }
    };

    loadData();

    // Set up SSE for real-time status if not completed
    const sseUrl = `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api'}/analysis/jobs/${id}/stream`;
    const eventSource = new EventSource(sseUrl);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setSseStatus({ step: data.step, message: data.message });
        
        if (data.step === 6) { // Completed
          eventSource.close();
          loadData(); // Re-fetch to get the final report
        } else if (data.step === -1) { // Failed
          eventSource.close();
          loadData();
        }
      } catch (err) {
        // Just a keep-alive or malformed message
      }
    };

    eventSource.onerror = () => {
      // If we error out, close it. The fallback loadData will catch state.
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [id]);

  if (loading && !job) {
    return (
      <div className="job-loading-container">
        <Activity className="animate-pulse" size={48} color="var(--accent-primary)" />
        <h2>Loading Analysis...</h2>
      </div>
    );
  }

  if (error) {
    return (
      <div className="job-error-container glass-card">
        <AlertTriangle size={48} color="var(--accent-danger)" />
        <h2>Error Loading Job</h2>
        <p>{error}</p>
      </div>
    );
  }

  if (job?.status === 'processing' || job?.status === 'pending') {
    return (
      <div className="job-processing-container glass-panel">
        <div className="processing-icon-wrapper">
          <Activity size={48} color="var(--accent-warning)" />
        </div>
        <h2>AI Analysis in Progress</h2>
        <p className="processing-subtitle">MedLens is analyzing <strong>{job.file_name}</strong>...</p>
        
        <div className="processing-steps">
          <div className={`step ${sseStatus.step >= 1 ? 'active' : ''} ${sseStatus.step === 1 ? 'pulse' : ''}`}>
            <div className="step-dot"></div>
            <span>Image Pre-processing</span>
          </div>
          <div className={`step ${sseStatus.step >= 2 ? 'active' : ''} ${sseStatus.step === 2 ? 'pulse' : ''}`}>
            <div className="step-dot"></div>
            <span>Multimodal VLM Analysis</span>
          </div>
          <div className={`step ${sseStatus.step >= 3 ? 'active' : ''} ${sseStatus.step === 3 ? 'pulse' : ''}`}>
            <div className="step-dot"></div>
            <span>RAG Clinical Grounding</span>
          </div>
          <div className={`step ${sseStatus.step >= 4 ? 'active' : ''} ${sseStatus.step === 4 ? 'pulse' : ''}`}>
            <div className="step-dot"></div>
            <span>Self-Critique QA</span>
          </div>
          <div className={`step ${sseStatus.step >= 5 ? 'active' : ''} ${sseStatus.step === 5 ? 'pulse' : ''}`}>
            <div className="step-dot"></div>
            <span>Report Synthesis</span>
          </div>
        </div>
        
        <p className="sse-live-message" style={{ marginTop: '2rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
          {sseStatus.message}
        </p>
      </div>
    );
  }

  if (job?.status === 'failed') {
    return (
      <div className="job-error-container glass-card">
        <AlertTriangle size={48} color="var(--accent-danger)" />
        <h2>Analysis Failed</h2>
        <p className="error-detail">{job.error_message || 'An unknown error occurred during processing.'}</p>
      </div>
    );
  }

  // Completed State
  return (
    <div className="animate-fade-in job-results-page">
      <div className="job-header">
        <div>
          <h1 className="job-title">Analysis Results</h1>
          <div className="job-meta">
            <FileImage size={16} />
            <span>{job?.file_name}</span>
            <span className="meta-divider">•</span>
            <span>{new Date(job?.created_at).toLocaleString()}</span>
          </div>
        </div>
      </div>

      <div className="job-content-grid">
        <div className="main-content">
          <ImageViewer jobId={job.id} fileName={job.file_name} />
          <ReportView report={report} />
        </div>
        <div className="side-content">
          <ChatBox jobId={id} />
        </div>
      </div>
    </div>
  );
}
