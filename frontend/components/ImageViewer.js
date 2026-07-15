'use client';

import { useState } from 'react';
import {
  Maximize2,
  Minimize2,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Download,
  FileText,
  ExternalLink,
} from 'lucide-react';
import './ImageViewer.css';

export default function ImageViewer({ jobId, fileName }) {
  const [scale, setScale] = useState(1);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const isPdf = fileName?.toLowerCase().endsWith('.pdf');
  const fileUrl = `/api/jobs/${jobId}/file`;

  const handleZoomIn = () => setScale((prev) => Math.min(prev + 0.25, 3));
  const handleZoomOut = () => setScale((prev) => Math.max(prev - 0.25, 0.25));
  const handleReset = () => setScale(1);

  const toggleFullscreen = () => {
    const elem = document.getElementById('image-viewer-container');
    if (!elem) return;

    if (!document.fullscreenElement) {
      elem.requestFullscreen().catch((err) => {
        console.error(`Fullscreen error: ${err.message}`);
      });
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  return (
    <div
      id="image-viewer-container"
      className={`image-viewer-container ${isFullscreen ? 'fullscreen' : ''}`}
    >
      {/* Toolbar */}
      <div className="viewer-toolbar">
        <span className="viewer-filename">{fileName || 'Unknown file'}</span>
        <div className="viewer-controls">
          {!isPdf && (
            <>
              <button
                onClick={handleZoomOut}
                className="control-btn"
                aria-label="Zoom out"
                title="Zoom out"
              >
                <ZoomOut size={16} />
              </button>
              <button
                onClick={handleReset}
                className="control-btn scale-indicator"
                title="Reset zoom"
              >
                {Math.round(scale * 100)}%
              </button>
              <button
                onClick={handleZoomIn}
                className="control-btn"
                aria-label="Zoom in"
                title="Zoom in"
              >
                <ZoomIn size={16} />
              </button>
              <div className="controls-divider" />
            </>
          )}
          <a
            href={fileUrl}
            download
            className="control-btn"
            aria-label="Download file"
            title="Download"
          >
            <Download size={16} />
          </a>
          <button
            onClick={toggleFullscreen}
            className="control-btn"
            aria-label={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
            title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          >
            {isFullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="viewer-content">
        {isPdf ? (
          <div className="pdf-placeholder">
            <div className="pdf-icon-ring">
              <FileText size={32} color="var(--primary)" />
            </div>
            <h3>PDF Document</h3>
            <p>PDF documents are analyzed for embedded medical data and text context.</p>
            <a
              href={fileUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="pdf-view-btn"
            >
              <ExternalLink size={14} />
              View Original PDF
            </a>
          </div>
        ) : (
          <div className="image-wrapper">
            <img
              src={fileUrl}
              alt={`Medical scan: ${fileName}`}
              className="medical-image"
              style={{ transform: `scale(${scale})` }}
              draggable="false"
            />
          </div>
        )}
      </div>
    </div>
  );
}
