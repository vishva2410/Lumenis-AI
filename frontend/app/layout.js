import Navbar from '@/components/Navbar';
import './globals.css';

export const metadata = {
  title: 'MedLens by Lumenis AI',
  description: 'AI-powered multimodal medical imaging analysis',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <Navbar />
        <main className="page-wrapper container">
          {children}
        </main>
      </body>
    </html>
  );
}
