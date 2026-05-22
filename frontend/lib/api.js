const isServer = typeof window === 'undefined';
// When fetching from Server Components (SSR), we must use an absolute URL.
// We point directly to the backend container.
// On the client, we use relative /api to go through Next.js rewrite proxy.
const API_BASE = isServer 
  ? (process.env.INTERNAL_API_URL || 'http://backend:8000') + '/api' 
  : '/api';

export async function fetchJobs(skip = 0, limit = 10) {
  const res = await fetch(`${API_BASE}/jobs?skip=${skip}&limit=${limit}`, {
    cache: 'no-store'
  });
  if (!res.ok) throw new Error('Failed to fetch jobs');
  return res.json();
}

export async function fetchJob(id) {
  const res = await fetch(`${API_BASE}/jobs/${id}`, {
    cache: 'no-store'
  });
  if (!res.ok) throw new Error('Failed to fetch job');
  return res.json();
}

export async function fetchReport(id) {
  const res = await fetch(`${API_BASE}/jobs/${id}/report`, {
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
    let detail = 'Upload failed';
    try {
      const err = await res.json();
      detail = err.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

export async function sendChatMessage(jobId, message) {
  const res = await fetch(`${API_BASE}/chat/${jobId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error('Chat request failed');
  return res.json();
}
