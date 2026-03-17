"use client";

import { useState } from "react";
import { login, register } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

export default function LoginPage() {
  const { refresh } = useAuth();
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      if (isRegister) {
        await register(email, password, name);
      } else {
        await login(email, password);
      }
      await refresh();
      window.location.href = "/chat";
    } catch (err: any) {
      setError(err.message || "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen p-4">
      <div
        className="w-full max-w-md rounded-xl p-8"
        style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}
      >
        {/* Logo */}
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold mb-1">⚡ CognitionShift</h1>
          <p style={{ color: "var(--text-secondary)" }}>Enterprise AI Gateway</p>
        </div>

        {/* Tabs */}
        <div className="flex mb-6 rounded-lg overflow-hidden" style={{ backgroundColor: "var(--bg-primary)" }}>
          <button
            onClick={() => setIsRegister(false)}
            className="flex-1 py-2 text-sm font-medium transition-colors"
            style={{
              backgroundColor: !isRegister ? "var(--accent)" : "transparent",
              color: !isRegister ? "white" : "var(--text-secondary)",
            }}
            aria-pressed={!isRegister}
          >
            Sign In
          </button>
          <button
            onClick={() => setIsRegister(true)}
            className="flex-1 py-2 text-sm font-medium transition-colors"
            style={{
              backgroundColor: isRegister ? "var(--accent)" : "transparent",
              color: isRegister ? "white" : "var(--text-secondary)",
            }}
            aria-pressed={isRegister}
          >
            Register
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {isRegister && (
            <div>
              <label htmlFor="name" className="block text-sm font-medium mb-1">
                Full Name
              </label>
              <input
                id="name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required={isRegister}
                className="w-full px-3 py-2 rounded-lg text-sm"
                style={{
                  backgroundColor: "var(--bg-primary)",
                  border: "1px solid var(--border)",
                  color: "var(--text-primary)",
                }}
                placeholder="Eric Whyne"
              />
            </div>
          )}

          <div>
            <label htmlFor="email" className="block text-sm font-medium mb-1">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full px-3 py-2 rounded-lg text-sm"
              style={{
                backgroundColor: "var(--bg-primary)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
              }}
              placeholder="you@company.com"
              autoComplete="email"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium mb-1">
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              className="w-full px-3 py-2 rounded-lg text-sm"
              style={{
                backgroundColor: "var(--bg-primary)",
                border: "1px solid var(--border)",
                color: "var(--text-primary)",
              }}
              placeholder="Min 8 characters"
              autoComplete={isRegister ? "new-password" : "current-password"}
            />
          </div>

          {error && (
            <div className="text-sm px-3 py-2 rounded-lg" style={{ backgroundColor: "#7f1d1d", color: "#fca5a5" }} role="alert">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 rounded-lg font-medium text-sm transition-colors disabled:opacity-50"
            style={{ backgroundColor: "var(--accent)", color: "white" }}
          >
            {loading ? "..." : isRegister ? "Create Account" : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}
