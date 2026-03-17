import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { ToastProvider } from "@/components/toast";
import { ErrorBoundary } from "@/components/error-boundary";

export const metadata: Metadata = {
  title: "CognitionShift AI Gateway",
  description: "Enterprise AI Gateway — Secure, governed access to frontier AI models",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark">
      <body className="antialiased">
        {/* Skip to content link for accessibility */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:z-[100] focus:top-2 focus:left-2 focus:px-4 focus:py-2 focus:rounded-lg focus:text-sm"
          style={{ backgroundColor: "var(--accent)", color: "white" }}
        >
          Skip to main content
        </a>
        <ErrorBoundary>
          <AuthProvider>
            <ToastProvider>
              <div id="main-content">
                {children}
              </div>
            </ToastProvider>
          </AuthProvider>
        </ErrorBoundary>
      </body>
    </html>
  );
}
