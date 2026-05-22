import { useState } from 'react';
import { Maximize2, ZoomIn, ZoomOut, Download, FileText } from 'lucide-react';
import './ImageViewer.css';

export default function ImageViewer({ jobId, fileName }) {
  const [scale, setScale] = useState(1);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Determine if it's a PDF based on the file name
  const isPdf = fileName?.toLowerCase().endsWith('.pdf');
  const fileUrl = `/api/jobs/${jobId}/file`;

  const handleZoomIn = () => setScale(prev => Math.min(prev + 0.2, 3));
  const handleZoomOut = () => setScale(prev => Math.max(prev - 0.2, 0.5));
  const handleReset = () => setScale(1);

  const toggleFullscreen = () => {
    const elem = document.getElementById('image-viewer-container');
    if (!document.fullscreenElement) {
      elem.requestFullscreen().catch(err => {
        console.error(`Error attempting to enable fullscreen: ${err.message}`);
      });
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  return (
    <div id="image-viewer-container" className={`image-viewer-container glass-card ${isFullscreen ? 'fullscreen' : ''}`}>
      <div className="viewer-toolbar">
        <span className="viewer-filename">{fileName}</span>
        <div className="viewer-controls">
          {!isPdf && (
            <>
              <button onClick={handleZoomOut} className="control-btn" aria-label="Zoom out"><ZoomOut size={18} /></button>
              <button onClick={handleReset} className="control-btn scale-indicator">{Math.round(scale * 100)}%</button>
              <button onClick={handleZoomIn} className="control-btn" aria-label="Zoom in"><ZoomIn size={18} /></button>
            </>
          )}
          <a href={fileUrl} download className="control-btn" aria-label="Download"><Download size={18} /></a>
          <button onClick={toggleFullscreen} className="control-btn" aria-label="Fullscreen"><Maximize2 size={18} /></button>
        </div>
      </div>
      
      <div className="viewer-content">
        {isPdf ? (
          <div className="pdf-placeholder">
            <FileText size={64} color="var(--accent-primary)" />
            <h3>PDF Document</h3>
            <p>PDF documents are analyzed for text context.</p>
            <a href={fileUrl} target="_blank" rel="noopener noreferrer" className="btn btn-primary" style={{ marginTop: '1rem' }}>
              View Original PDF
            </a>
          </div>
        ) : (
          <div className="image-wrapper">
            <img 
              src={fileUrl} 
              alt="Medical scan" 
              className="medical-image"
              style={{ transform: `scale(${scale})` }}
              draggable="false"
            />
            {/* If we had bounding boxes, we would overlay them here as absolute divs */}
          </div>
        )}
      </div>
    </div>
  );
}
