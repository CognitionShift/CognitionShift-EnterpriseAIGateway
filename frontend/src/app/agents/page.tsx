"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

interface Template {
  id: string;
  name: string;
  slug: string;
  description: string;
  category: string;
  default_model: string;
  is_system: boolean;
}

interface Execution {
  id: string;
  template_name: string;
  status: string;
  total_tokens: number;
  duration_ms: number;
  created_at: string;
  output_preview: string | null;
}

export default function AgentsPage() {
  const { user, loading } = useAuth();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(null);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(null);

  useEffect(() => {
    if (!loading && !user) window.location.href = "/login";
  }, [user, loading]);

  const getToken = () => localStorage.getItem("access_token");
  const headers = () => ({ Authorization: `Bearer ${getToken()}`, "Content-Type": "application/json" });

  useEffect(() => {
    if (user) {
      fetchTemplates();
      fetchExecutions();
    }
  }, [user]);

  const fetchTemplates = async () => {
    try {
      const r = await fetch(`${API_URL}/api/v1/agents/templates`, { headers: headers() });
      if (r.ok) setTemplates((await r.json()).data);
    } catch {}
  };

  const fetchExecutions = async () => {
    try {
      const r = await fetch(`${API_URL}/api/v1/agents/executions?limit=10`, { headers: headers() });
      if (r.ok) setExecutions((await r.json()).data);
    } catch {}
  };

  const runAgent = async () => {
    if (!selectedTemplate || !input.trim()) return;
    setRunning(true);
    setResult(null);

    try {
      const r = await fetch(`${API_URL}/api/v1/agents/run/${selectedTemplate.slug}`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ input }),
      });
      if (r.ok) {
        const data = await r.json();
        setResult(data.data);
        fetchExecutions();
      } else {
        const err = await r.json().catch(() => ({ detail: "Unknown error" }));
        setResult({ error: err.detail || "Agent execution failed" });
      }
    } catch (err) {
      setResult({ error: "Network error" });
    } finally {
      setRunning(false);
    }
  };

  if (loading || !user) return null;

  const categoryIcons: Record<string, string> = {
    research: "🔬",
    writing: "✍️",
    development: "💻",
    analysis: "📊",
    general: "🤖",
  };

  return (
    <div className="min-h-screen p-6" style={{ backgroundColor: "var(--bg-primary)" }}>
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold">⚡ AI Agents</h1>
            <p className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>
              Run specialized AI agents for research, writing, code review, and more.
            </p>
          </div>
          <a href="/chat" className="px-4 py-2 rounded-lg text-sm" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
            ← Back to Chat
          </a>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Templates */}
          <div className="lg:col-span-1">
            <h2 className="text-lg font-semibold mb-4">Agent Templates</h2>
            <div className="space-y-3">
              {templates.map((t) => (
                <button
                  key={t.id}
                  onClick={() => { setSelectedTemplate(t); setResult(null); }}
                  className="w-full text-left rounded-xl p-4 transition-colors"
                  style={{
                    backgroundColor: selectedTemplate?.id === t.id ? "var(--accent)" : "var(--bg-secondary)",
                    color: selectedTemplate?.id === t.id ? "white" : "var(--text-primary)",
                    border: `1px solid ${selectedTemplate?.id === t.id ? "var(--accent)" : "var(--border)"}`,
                  }}
                >
                  <div className="flex items-center gap-2">
                    <span>{categoryIcons[t.category] || "🤖"}</span>
                    <span className="font-medium">{t.name}</span>
                  </div>
                  <p className="text-xs mt-1 opacity-80">{t.description}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Execution area */}
          <div className="lg:col-span-2">
            {selectedTemplate ? (
              <div>
                <h2 className="text-lg font-semibold mb-2">
                  {categoryIcons[selectedTemplate.category] || "🤖"} {selectedTemplate.name}
                </h2>
                <p className="text-sm mb-4" style={{ color: "var(--text-secondary)" }}>
                  {selectedTemplate.description}
                </p>

                {/* Input */}
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Enter your input for the agent..."
                  rows={4}
                  className="w-full px-4 py-3 rounded-xl text-sm resize-none mb-3"
                  style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
                  disabled={running}
                />

                <button
                  onClick={runAgent}
                  disabled={running || !input.trim()}
                  className="px-6 py-2.5 rounded-lg font-medium text-sm transition-colors disabled:opacity-50 mb-6"
                  style={{ backgroundColor: "var(--accent)", color: "white" }}
                >
                  {running ? "⏳ Running..." : "▶ Run Agent"}
                </button>

                {/* Result */}
                {result && (
                  <div className="rounded-xl p-6" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
                    {result.error ? (
                      <div style={{ color: "var(--error)" }}>⚠️ {result.error}</div>
                    ) : (
                      <>
                        <div className="flex items-center gap-4 mb-4 text-xs" style={{ color: "var(--text-secondary)" }}>
                          <span className={`px-2 py-0.5 rounded ${result.status === "completed" ? "bg-green-900 text-green-300" : "bg-red-900 text-red-300"}`}>
                            {result.status}
                          </span>
                          <span>{result.usage?.total_tokens} tokens</span>
                          <span>${result.usage?.total_cost_usd?.toFixed(4)}</span>
                          <span>{(result.usage?.duration_ms / 1000).toFixed(1)}s</span>
                        </div>
                        <div className="whitespace-pre-wrap text-sm leading-relaxed">
                          {result.output}
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-20" style={{ color: "var(--text-secondary)" }}>
                <p className="text-lg">← Select an agent template to get started</p>
              </div>
            )}

            {/* Recent executions */}
            {executions.length > 0 && (
              <div className="mt-8">
                <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--text-secondary)" }}>
                  Recent Executions
                </h3>
                <div className="space-y-2">
                  {executions.map((e) => (
                    <div
                      key={e.id}
                      className="flex items-center justify-between rounded-lg px-4 py-2 text-sm"
                      style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}
                    >
                      <div>
                        <span className="font-medium">{e.template_name}</span>
                        <span className="mx-2" style={{ color: "var(--text-secondary)" }}>•</span>
                        <span className={e.status === "completed" ? "text-green-400" : "text-red-400"}>
                          {e.status}
                        </span>
                      </div>
                      <div className="text-xs" style={{ color: "var(--text-secondary)" }}>
                        {e.total_tokens} tokens • {new Date(e.created_at).toLocaleTimeString()}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
