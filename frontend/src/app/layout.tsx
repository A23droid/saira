import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/contexts/auth-context";
import { Toaster } from "react-hot-toast";

export const metadata: Metadata = {
  title: "SAIRA — Smart AI Research Assistant",
  description:
    "SAIRA helps researchers search, organize, compare, and synthesize academic papers with AI assistance.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col font-sans">
        <AuthProvider>{children}</AuthProvider>
        <Toaster position="top-center" toastOptions={{
          style: {
            background: 'var(--surface)',
            color: 'var(--ink)',
            border: '1px solid var(--line)',
            boxShadow: '0 4px 12px rgba(0, 0, 0, 0.05)',
            fontSize: '14px',
            borderRadius: '12px',
          },
          success: {
            iconTheme: {
              primary: '#0d9488', // teal-600
              secondary: '#fff',
            },
          },
        }} />
      </body>
    </html>
  );
}
