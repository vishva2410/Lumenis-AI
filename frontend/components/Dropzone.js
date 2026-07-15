'use client';

import { useState, useCallback, useRef, useId } from 'react';
import { useRouter } from 'next/navigation';
import {
  ImagePlus,
  FileText,
  X,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Upload,
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { uploadFile } from '@/lib/api';
import './Dropzone.css';

/* ── Format config by mode ────────────────────────────── */
const MODE_CONFIG = {
  imagery: {
    accept: '.dcm,.jpg,.jpeg,.png',
    validExtensions: ['.dcm', '.jpg', '.jpeg', '.png'],
    validMimeTypes: ['image/jpeg', 'image/png', 'image/dicom', 'application/dicom'],
    icon: ImagePlus,
    heading: 'Upload Medical Imagery',
    description: 'Drag and drop your DICOM or imaging file here, or',
    formats: ['DICOM', 'JPEG', 'PNG'],
    maxSizeMB: 100,
  },
  reports: {
    accept: '.pdf',
    validExtensions: ['.pdf'],
    validMimeTypes: ['application/pdf'],
    icon: FileText,
    heading: 'Upload Clinical Report',
    description: 'Drag and drop your PDF report here, or',
    formats: ['PDF'],
    maxSizeMB: 50,
  },
};

/**
 * Dropzone — Redesigned file upload component
 * @param {{ mode: 'imagery' | 'reports' }} props
 */
export default function Dropzone({ mode = 'imagery' }) {
  const router = useRouter();
  const inputId = useId();
  const fileInputRef = useRef(null);

  const [file, setFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [status, setStatus] = useState('idle'); // idle | uploading | success | error
  const [progress, setProgress] = useState(0);
  const [errorMsg, setErrorMsg] = useState('');

  const config = MODE_CONFIG[mode] || MODE_CONFIG.imagery;
  const IconComponent = config.icon;

  /* ── File Validation ──────────────────────────────── */
  const validateFile = useCallback(
    (selectedFile) => {
      const name = selectedFile.name.toLowerCase();
      const isValidExt = config.validExtensions.some((ext) => name.endsWith(ext));
      const isValidMime = config.validMimeTypes.includes(selectedFile.type);

      if (!isValidExt && !isValidMime) {
        return `Unsupported file type. Please upload: ${config.formats.join(', ')}`;
      }

      if (selectedFile.size > config.maxSizeMB * 1024 * 1024) {
        return `File too large. Maximum size is ${config.maxSizeMB}MB.`;
      }

      return null;
    },
    [config]
  );

  /* ── Event Handlers ───────────────────────────────── */
  const handleFileSelection = useCallback(
    (selectedFile) => {
      const error = validateFile(selectedFile);
      if (error) {
        setStatus('error');
        setErrorMsg(error);
        return;
      }
      setFile(selectedFile);
      setStatus('idle');
      setErrorMsg('');
      setProgress(0);
    },
    [validateFile]
  );

  const onDragOver = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const onDragLeave = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const onDrop = useCallback(
    (e) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        handleFileSelection(e.dataTransfer.files[0]);
      }
    },
    [handleFileSelection]
  );

  const onFileChange = useCallback(
    (e) => {
      if (e.target.files && e.target.files[0]) {
        handleFileSelection(e.target.files[0]);
      }
    },
    [handleFileSelection]
  );

  const openFilePicker = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  /* ── Upload ───────────────────────────────────────── */
  const handleUpload = async () => {
    if (!file || status === 'uploading') return;

    setStatus('uploading');
    setErrorMsg('');
    setProgress(0);

    // Simulate progress while waiting for the actual upload
    const progressInterval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 90) {
          clearInterval(progressInterval);
          return 90;
        }
        return prev + Math.random() * 12;
      });
    }, 300);

    try {
      const response = await uploadFile(file);
      clearInterval(progressInterval);
      setProgress(100);

      const jobId = response.id || response.job_id || response.uuid;
      if (!jobId) {
        throw new Error('Invalid response from server: missing Job ID');
      }

      setStatus('success');

      // Redirect after brief success feedback
      setTimeout(() => {
        router.push(`/job/${jobId}`);
      }, 1200);
    } catch (error) {
      clearInterval(progressInterval);
      setStatus('error');
      setProgress(0);
      setErrorMsg(error.message || 'Upload failed. Please try again.');
    }
  };

  /* ── Clear ────────────────────────────────────────── */
  const clearFile = useCallback(() => {
    setFile(null);
    setStatus('idle');
    setErrorMsg('');
    setProgress(0);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, []);

  /* ── Helpers ──────────────────────────────────────── */
  const formatFileSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const getFileExtension = (name) => {
    const parts = name.split('.');
    return parts.length > 1 ? parts.pop().toUpperCase() : 'FILE';
  };

  /* ── Render ───────────────────────────────────────── */
  return (
    <div className="dropzoneContainer">
      <AnimatePresence mode="wait">
        {!file ? (
          /* ── Dropzone Area ──────────────────────────── */
          <motion.div
            key="dropzone"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
          >
            <motion.div
              className={`dropzoneArea ${isDragging ? 'dragging' : ''}`}
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              onDrop={onDrop}
              onClick={openFilePicker}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
              transition={{ type: 'spring', stiffness: 400, damping: 25 }}
            >
              <div className="dropzoneContent">
                <motion.div
                  className="uploadIcon"
                  animate={
                    isDragging
                      ? { y: [0, -6, 0], scale: 1.08 }
                      : { y: 0, scale: 1 }
                  }
                  transition={
                    isDragging
                      ? { y: { repeat: Infinity, duration: 0.6, ease: 'easeInOut' }, scale: { duration: 0.2 } }
                      : { duration: 0.2 }
                  }
                >
                  <IconComponent size={32} />
                </motion.div>

                <h3 className="dropzoneHeading">{config.heading}</h3>
                <p className="dropzoneDescription">
                  {config.description}{' '}
                  <span className="browseLink">browse files</span>
                </p>

                <div className="formatBadges">
                  {config.formats.map((fmt) => (
                    <span key={fmt} className="formatBadge">
                      {fmt}
                    </span>
                  ))}
                </div>
                <span className="sizeLimit">
                  Max file size: {config.maxSizeMB}MB
                </span>
              </div>

              <input
                ref={fileInputRef}
                id={inputId}
                type="file"
                className="hiddenInput"
                accept={config.accept}
                onChange={onFileChange}
              />
            </motion.div>

            {/* Error displayed below dropzone if no file selected yet */}
            <AnimatePresence>
              {status === 'error' && !file && (
                <motion.div
                  className="uploadError"
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.2 }}
                  style={{ marginTop: 'var(--space-3)' }}
                >
                  <AlertCircle size={16} />
                  <span>{errorMsg}</span>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        ) : (
          /* ── File Preview ──────────────────────────── */
          <motion.div
            key="preview"
            className="filePreview"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
          >
            {/* File info row */}
            <div className="fileInfo">
              <div className="fileTypeIcon">
                {mode === 'reports' ? (
                  <FileText size={24} />
                ) : (
                  <ImagePlus size={24} />
                )}
              </div>
              <div className="fileDetails">
                <h4 className="fileName">{file.name}</h4>
                <p className="fileMeta">
                  <span>{formatFileSize(file.size)}</span>
                  <span className="dot" />
                  <span>{getFileExtension(file.name)}</span>
                </p>
              </div>
              {(status === 'idle' || status === 'error') && (
                <motion.button
                  className="clearBtn"
                  onClick={clearFile}
                  aria-label="Remove file"
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                >
                  <X size={18} />
                </motion.button>
              )}
            </div>

            {/* Progress bar */}
            <AnimatePresence>
              {status === 'uploading' && (
                <motion.div
                  className="progressSection"
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.25 }}
                >
                  <div className="progressHeader">
                    <span className="progressLabel">
                      <Loader2 size={14} className="spinner" />
                      Uploading & analyzing...
                    </span>
                    <span className="progressPercent">
                      {Math.round(progress)}%
                    </span>
                  </div>
                  <div className="progressTrack">
                    <motion.div
                      className="progressBar"
                      initial={{ width: 0 }}
                      animate={{ width: `${progress}%` }}
                      transition={{ duration: 0.3, ease: 'easeOut' }}
                    />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Error message */}
            <AnimatePresence>
              {status === 'error' && (
                <motion.div
                  className="uploadError"
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.2 }}
                >
                  <AlertCircle size={16} />
                  <span>{errorMsg}</span>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Action buttons */}
            {status === 'idle' || status === 'error' ? (
              <motion.button
                className="actionBtn actionBtnPrimary"
                onClick={handleUpload}
                whileHover={{ scale: 1.01 }}
                whileTap={{ scale: 0.98 }}
              >
                <Upload size={18} />
                Start Analysis
              </motion.button>
            ) : status === 'uploading' ? (
              <button className="actionBtn actionBtnPrimary" disabled>
                <Loader2 size={18} className="spinner" />
                Processing...
              </button>
            ) : (
              <motion.button
                className="actionBtn successState"
                disabled
                initial={{ scale: 0.95 }}
                animate={{ scale: 1 }}
                transition={{ type: 'spring', stiffness: 300, damping: 15 }}
              >
                <motion.span
                  initial={{ scale: 0, rotate: -90 }}
                  animate={{ scale: 1, rotate: 0 }}
                  transition={{
                    type: 'spring',
                    stiffness: 400,
                    damping: 12,
                    delay: 0.1,
                  }}
                  style={{ display: 'flex' }}
                >
                  <CheckCircle2 size={18} />
                </motion.span>
                Upload Complete — Redirecting...
              </motion.button>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
