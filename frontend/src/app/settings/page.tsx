"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { listModels, ModelInfo, getMyUsage } from "@/lib/api";

export default function SettingsPage() {
  const { user, loading } = useAuth();
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [defaultModel, setDefaultModel] = useState("");
  const [theme, setTheme] = useState("system");
  const [usage, setUsage] = useState<any>(null);

  useEffect(() => {
    if (!loading && !user) window.location.href = "/login";
  }, [user, loading]);

  useEffect(() => {
    if (user) {
      listModels().then(setModels).catch(console.error);
      getMyUsage("daily").then(setUsage).catch(console.error);

      // Load saved preferences
      setDefaultModel(localStorage.getItem("default_model") || "");
      setTheme(localStorage.getItem("theme") || "system");
    }
  }, [user]);

  const saveDefaultModel = (id: string) => {
    setDefaultModel(id);
    localStorage.setItem("default_model", id);
  };

  const saveTheme = (t: string) => {
    setTheme(t);
    localStorage.setItem("theme", t);
    document.documentElement.setAttribute("data-theme", t === "system" ? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : t);
  };

  if (loading || !user) return null;

  return (
    <div className="min-h-screen p-6" style={{ backgroundColor: "var(--bg-primary)" }}>
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-2xl font-bold">⚙️ Settings</h1>
          <a href="/chat" className="px-4 py-2 rounded-lg text-sm" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
            ← Back to Chat
          </a>
        </div>

        {/* Profile */}
        <section className="mb-8 p-6 rounded-xl" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
          <h2 className="text-lg font-semibold mb-4">Profile</h2>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span style={{ color: "var(--text-secondary)" }}>Name</span>
              <span>{user.name}</span>
            </div>
            <div className="flex justify-between">
              <span style={{ color: "var(--text-secondary)" }}>Email</span>
              <span>{user.email}</span>
            </div>
            <div className="flex justify-between">
              <span style={{ color: "var(--text-secondary)" }}>Role</span>
              <span className="capitalize">{user.role}</span>
            </div>
          </div>
        </section>

        {/* Preferences */}
        <section className="mb-8 p-6 rounded-xl" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
          <h2 className="text-lg font-semibold mb-4">Preferences</h2>

          <div className="space-y-4">
            <div>
              <label className="block text-sm mb-1" style={{ color: "var(--text-secondary)" }}>Default Model</label>
              <select
                value={defaultModel}
                onChange={(e) => saveDefaultModel(e.target.value)}
                className="w-full px-3 py-2 rounded-lg text-sm"
                style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
              >
                <option value="">Auto (first available)</option>
                {models.map((m) => (
                  <option key={m.id} value={m.id}>{m.display_name} ({m.provider})</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm mb-1" style={{ color: "var(--text-secondary)" }}>Theme</label>
              <div className="flex gap-2">
                {["system", "dark", "light"].map((t) => (
                  <button
                    key={t}
                    onClick={() => saveTheme(t)}
                    className="px-4 py-2 rounded-lg text-sm capitalize transition-colors"
                    style={{
                      backgroundColor: theme === t ? "var(--accent)" : "var(--bg-primary)",
                      color: theme === t ? "white" : "var(--text-secondary)",
                      border: "1px solid var(--border)",
                    }}
                  >
                    {t === "system" ? "💻 System" : t === "dark" ? "🌙 Dark" : "☀️ Light"}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* Usage */}
        {usage && (
          <section className="mb-8 p-6 rounded-xl" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
            <h2 className="text-lg font-semibold mb-4">Usage (Today)</h2>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs" style={{ color: "var(--text-secondary)" }}>Tokens Used</p>
                <p className="text-xl font-bold">{(usage.usage?.tokens?.total || 0).toLocaleString()}</p>
              </div>
              <div>
                <p className="text-xs" style={{ color: "var(--text-secondary)" }}>Cost</p>
                <p className="text-xl font-bold">${(usage.usage?.cost_usd || 0).toFixed(4)}</p>
              </div>
              <div>
                <p className="text-xs" style={{ color: "var(--text-secondary)" }}>Requests</p>
                <p className="text-xl font-bold">{usage.usage?.requests || 0}</p>
              </div>
              {usage.quota && (
                <div>
                  <p className="text-xs" style={{ color: "var(--text-secondary)" }}>Remaining Tokens</p>
                  <p className="text-xl font-bold">{(usage.quota.remaining_tokens || 0).toLocaleString()}</p>
                </div>
              )}
            </div>
          </section>
        )}

        {/* Keyboard Shortcuts */}
        <section className="p-6 rounded-xl" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
          <h2 className="text-lg font-semibold mb-4">Keyboard Shortcuts</h2>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span style={{ color: "var(--text-secondary)" }}>New Chat</span>
              <kbd className="px-2 py-0.5 rounded" style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border)" }}>Ctrl+N</kbd>
            </div>
            <div className="flex justify-between">
              <span style={{ color: "var(--text-secondary)" }}>Search</span>
              <kbd className="px-2 py-0.5 rounded" style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border)" }}>Ctrl+K</kbd>
            </div>
            <div className="flex justify-between">
              <span style={{ color: "var(--text-secondary)" }}>Toggle Sidebar</span>
              <kbd className="px-2 py-0.5 rounded" style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border)" }}>Ctrl+B</kbd>
            </div>
            <div className="flex justify-between">
              <span style={{ color: "var(--text-secondary)" }}>Close Modal</span>
              <kbd className="px-2 py-0.5 rounded" style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border)" }}>Escape</kbd>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
