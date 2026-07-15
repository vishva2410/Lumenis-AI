import AppShell from '@/components/AppShell';
import './globals.css';

export const metadata = {
  title: 'Lumenis AI — Medical Imaging Intelligence',
  description: 'AI-powered multimodal medical image analysis, clinical reporting, and diagnostic intelligence platform.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <AppShell>
          {children}
        </AppShell>
      </body>
    </html>
  );
}
