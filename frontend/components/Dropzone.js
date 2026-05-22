'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { UploadCloud, File as FileIcon, X, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import { uploadFile } from '@/lib/api';
import './Dropzone.css';

export default function Dropzone() {
  const router = useRouter();
  const [file, setFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [status, setStatus] = useState('idle'); // idle, uploading, success, error
  const [errorMsg, setErrorMsg] = useState('');

  const onDragOver = useCallback((e) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const onDragLeave = useCallback((e) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const onDrop = useCallback((e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelection(e.dataTransfer.files[0]);
    }
  }, []);

  const onFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFileSelection(e.target.files[0]);
    }
  };

  const handleFileSelection = (selectedFile) => {
    // Basic validation
    const validTypes = ['image/jpeg', 'image/png', 'image/dicom', 'application/dicom', 'application/pdf'];
    // For DICOMs which might not have standard mime types, we allow fallback by extension
    const name = selectedFile.name.toLowerCase();
    const isValidExt = name.endsWith('.dcm') || name.endsWith('.jpg') || name.endsWith('.png') || name.endsWith('.pdf');
    
    if (!validTypes.includes(selectedFile.type) && !isValidExt) {
      setStatus('error');
      setErrorMsg('Unsupported file type. Please upload a JPEG, PNG, DICOM, or PDF.');
      return;
    }
    
    if (selectedFile.size > 50 * 1024 * 1024) { // 50MB
      setStatus('error');
      setErrorMsg('File too large. Maximum size is 50MB.');
      return;
    }

    setFile(selectedFile);
    setStatus('idle');
    setErrorMsg('');
  };

  const handleUpload = async () => {
    if (!file) return;
    
    setStatus('uploading');
    try {
      const response = await uploadFile(file);
      console.log('Upload response:', response);
      const jobId = response.id || response.job_id || response.uuid;
      
      if (!jobId) {
        throw new Error("Invalid response from server: missing Job ID");
      }
      
      setStatus('success');
      // Redirect to the job page after a short delay for smooth UX
      setTimeout(() => {
        router.push(`/job/${jobId}`);
      }, 800);
    } catch (error) {
      setStatus('error');
      setErrorMsg(error.message || 'Upload failed. Please try again.');
    }
  };

  const clearFile = () => {
    setFile(null);
    setStatus('idle');
    setErrorMsg('');
  };

  return (
    <div className="dropzone-container">
      {!file ? (
        <div 
          className={`dropzone-area ${isDragging ? 'dragging' : ''}`}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          onClick={() => document.getElementById('fileUpload').click()}
        >
          <div className="dropzone-content">
            <div className="upload-icon-wrapper">
              <UploadCloud size={48} className="upload-icon" />
            </div>
            <h3>Upload Medical Image or Report</h3>
            <p>Drag and drop your file here, or click to browse</p>
            <div className="supported-formats">
              <span>DICOM</span> • <span>JPEG/PNG</span> • <span>PDF</span>
            </div>
            <input 
              id="fileUpload" 
              type="file" 
              className="hidden-input" 
              accept=".dcm,image/jpeg,image/png,application/pdf" 
              onChange={onFileChange} 
            />
          </div>
        </div>
      ) : (
        <div className="glass-panel file-preview-card">
          <div className="file-info">
            <div className="file-icon">
              <FileIcon size={32} color="var(--accent-primary)" />
            </div>
            <div className="file-details">
              <h4>{file.name}</h4>
              <p>{(file.size / (1024 * 1024)).toFixed(2)} MB</p>
            </div>
            {status === 'idle' && (
              <button className="clear-btn" onClick={clearFile} aria-label="Remove file">
                <X size={20} />
              </button>
            )}
          </div>
          
          {status === 'error' && (
            <div className="upload-error">
              <AlertCircle size={18} />
              <span>{errorMsg}</span>
            </div>
          )}
          
          <div className="upload-actions">
            {status === 'idle' || status === 'error' ? (
              <button className="btn btn-primary w-full" onClick={handleUpload}>
                Start AI Analysis
              </button>
            ) : status === 'uploading' ? (
              <button className="btn btn-primary w-full" disabled>
                <Loader2 size={20} className="spinner" />
                Uploading & Initializing...
              </button>
            ) : (
              <button className="btn btn-primary w-full success-state" disabled>
                <CheckCircle2 size={20} />
                Upload Complete! Redirecting...
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
