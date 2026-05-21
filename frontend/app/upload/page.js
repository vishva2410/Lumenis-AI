import Dropzone from '@/components/Dropzone';
import { ShieldCheck } from 'lucide-react';

export default function UploadPage() {
  return (
    <div className="animate-fade-in" style={{ paddingTop: '2rem' }}>
      <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
        <h1 style={{ fontSize: '3rem', marginBottom: '1rem' }}>Start New Analysis</h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '1.2rem', maxWidth: '600px', margin: '0 auto' }}>
          Securely upload medical imaging or reports for AI-powered multimodal review and clinical recommendations.
        </p>
      </div>
      
      <Dropzone />
      
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.75rem', marginTop: '3rem', color: 'var(--text-muted)' }}>
        <ShieldCheck size={20} />
        <span style={{ fontSize: '0.9rem' }}>End-to-end encrypted. No data is used to train public models. HIPAA compliant architecture.</span>
      </div>
    </div>
  );
}
