const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

export async function fetchJobs(skip = 0, limit = 10) {
  const res = await fetch(`${API_BASE}/analysis/jobs?skip=${skip}&limit=${limit}`, {
    cache: 'no-store'
  });
  if (!res.ok) throw new Error('Failed to fetch jobs');
  return res.json();
}

export async function fetchJob(id) {
  const res = await fetch(`${API_BASE}/analysis/jobs/${id}`, {
    cache: 'no-store'
  });
  if (!res.ok) throw new Error('Failed to fetch job');
  return res.json();
}

export async function fetchReport(id) {
  const res = await fetch(`${API_BASE}/analysis/jobs/${id}/report`, {
    cache: 'no-store'
  });
  if (!res.ok) {
    if (res.status === 404) return null;
    throw new Error('Failed to fetch report');
  }
  return res.json();
}

export async function uploadFile(file) {
  const formData = new FormData();
  formData.append('file', file);
  
  const res = await fetch(`${API_BASE}/upload`, {
    method: 'POST',
    body: formData,
  });
  
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || 'Upload failed');
  }
  return res.json();
}

// Helper to get raw file URL if we need to display the image
// Assumes backend serves files statically, or we can use a base64 from the backend if provided.
// In this project, we might need a route to get the file, or we handle it via object URLs on the frontend during upload.
// For now, we'll return a placeholder if not supported.
