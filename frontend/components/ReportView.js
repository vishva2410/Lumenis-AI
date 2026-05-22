import { useState } from 'react';
import { AlertCircle, FileText, CheckCircle, Info, ChevronDown, ChevronUp, BookOpen } from 'lucide-react';
import './ReportView.css';

export default function ReportView({ report }) {
  const [expandedFindings, setExpandedFindings] = useState(
    // Expand the first finding by default if exists
    report?.findings?.length > 0 ? { 0: true } : {}
  );

  const toggleFinding = (index) => {
    setExpandedFindings(prev => ({
      ...prev,
      [index]: !prev[index]
    }));
  };

  if (!report) {
    return (
      <div className="glass-card empty-report">
        <AlertCircle size={32} color="var(--text-muted)" />
        <p>Report data is currently unavailable.</p>
      </div>
    );
  }

  return (
    <div className="report-container">
      {/* Summary Section */}
      <div className="glass-card report-section summary-section" id="printable-report">
        <div className="section-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <FileText size={24} color="var(--accent-primary)" />
            <h2>Executive Summary</h2>
          </div>
          <button 
            className="btn btn-secondary" 
            onClick={() => window.print()}
            style={{ padding: '0.5rem 1rem', fontSize: '0.9rem' }}
          >
            Export PDF
          </button>
        </div>
        <p className="summary-text">{report.summary}</p>
        
        <div className="report-meta">
          <div className="meta-item">
            <span className="meta-label">Overall Severity</span>
            <span className={`severity-badge severity-${report.severity_overall || 'low'}`}>
              {report.severity_overall || 'LOW'}
            </span>
          </div>
          <div className="meta-item">
            <span className="meta-label">AI Confidence</span>
            <div className="confidence-bar-wrapper">
              <div 
                className="confidence-bar" 
                style={{ 
                  width: `${(report.confidence_score || 0) * 100}%`,
                  background: report.confidence_score > 0.8 ? 'var(--accent-success)' : 
                              report.confidence_score > 0.5 ? 'var(--accent-warning)' : 'var(--accent-danger)'
                }}
              ></div>
            </div>
            <span className="confidence-value">{((report.confidence_score || 0) * 100).toFixed(1)}%</span>
          </div>
        </div>
      </div>

      {/* Recommendations Section */}
      {report.recommendations && report.recommendations.length > 0 && (
        <div className="glass-card report-section recommendations-section">
          <div className="section-header">
            <AlertCircle size={24} color="var(--accent-warning)" />
            <h2>Clinical Recommendations</h2>
          </div>
          <ul className="recommendations-list">
            {report.recommendations.map((rec, idx) => (
              <li key={idx}>
                <div className="rec-bullet"></div>
                <span>{rec}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Findings Section */}
      <div className="glass-card report-section findings-section">
        <div className="section-header">
          <CheckCircle size={24} color="var(--accent-primary)" />
          <h2>Detailed Findings</h2>
        </div>
        
        {report.findings && report.findings.length > 0 ? (
          <div className="findings-accordion">
            {report.findings.map((item, idx) => (
              <div key={idx} className={`finding-item ${expandedFindings[idx] ? 'expanded' : ''}`}>
                <div 
                  className="finding-header"
                  onClick={() => toggleFinding(idx)}
                >
                  <div className="finding-header-main">
                    <span className={`severity-badge severity-${item.finding.severity}`}>
                      {item.finding.severity}
                    </span>
                    <h3 className="finding-name">{item.finding.name}</h3>
                  </div>
                  <div className="finding-header-right">
                    <span className="finding-region">{item.finding.region}</span>
                    {expandedFindings[idx] ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
                  </div>
                </div>
                
                {expandedFindings[idx] && (
                  <div className="finding-body animate-fade-in">
                    <div className="finding-detail-group">
                      <h4><Info size={16} /> Description</h4>
                      <p>{item.finding.description}</p>
                    </div>
                    
                    {item.explanation && (
                      <div className="finding-detail-group explanation">
                        <h4><BookOpen size={16} /> Clinical Context (RAG)</h4>
                        <p>{item.explanation}</p>
                      </div>
                    )}
                    
                    {item.citations && item.citations.length > 0 && (
                      <div className="finding-detail-group citations">
                        <h4>Literature Citations</h4>
                        <ul className="citations-list">
                          {item.citations.map((cit, cidx) => (
                            <li key={cidx}>
                              <span className="citation-source">[{cit.source_id}]</span>
                              <span className="citation-text">"{cit.source_text}"</span>
                              <span className="citation-score">Relevance: {(cit.relevance_score * 100).toFixed(0)}%</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="no-findings">No significant findings reported.</p>
        )}
      </div>
    </div>
  );
}
