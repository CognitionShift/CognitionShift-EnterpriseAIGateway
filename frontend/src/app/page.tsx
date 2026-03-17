"use client";

import { useEffect } from "react";
import { useAuth } from "@/lib/auth-context";

export default function Home() {
  const { user, loading } = useAuth();

  useEffect(() => {
    if (!loading) {
      if (user) {
        window.location.href = "/chat";
      } else {
        window.location.href = "/login";
      }
    }
  }, [user, loading]);

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="animate-pulse text-lg" style={{ color: "var(--text-secondary)" }}>
        Loading...
      </div>
    </div>
  );
}
