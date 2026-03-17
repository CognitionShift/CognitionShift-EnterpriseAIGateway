"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Overview {
  period: string;
  users: { total: number; active: number };
  conversations: number;
  messages: number;
  usage: { tokens: number; cost_usd: number; requests: number };
  safety_events: number;
}

interface UserItem {
  id: string;
  email: string;
  name: string;
  role: string;
  last_login_at: string | null;
  created_at: string;
}

export default function AdminPage() {
  const { user, loading, logout } = useAuth();
  const [tab, setTab] = useState<"overview" | "users" | "models" | "safety" | "audit">("overview");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [users, setUsers] = useState<UserItem[]>([]);
  const [models, setModels] = useState<any[]>([]);
  const [auditEvents, setAuditEvents] = useState<any[]>([]);
  const [contentPolicy, setContentPolicy] = useState<any>(null);

  useEffect(() => {
    if (!loading && !user) window.location.href = "/login";
    if (!loading && user && user.role !== "admin") window.location.href = "/chat";
  }, [user, loading]);

  const getToken = () => localStorage.getItem("access_token");
  const headers = () => ({ Authorization: `Bearer ${getToken()}`, "Content-Type": "application/json" });

  useEffect(() => {
    if (!user || user.role !== "admin") return;
    fetchOverview();
    fetchUsers();
    fetchModels();
    fetchContentPolicy();
    fetchAudit();
  }, [user]);

  const fetchOverview = async () => {
    try {
      const r = await fetch(`${API_URL}/api/v1/admin/analytics/overview`, { headers: headers() });
      if (r.ok) setOverview((await r.json()).data);
    } catch {}
  };

  const fetchUsers = async () => {
    try {
      const r = await fetch(`${API_URL}/api/v1/admin/users`, { headers: headers() });
      if (r.ok) setUsers((await r.json()).data);
    } catch {}
  };

  const fetchModels = async () => {
    try {
      const r = await fetch(`${API_URL}/api/v1/admin/models`, { headers: headers() });
      if (r.ok) setModels((await r.json()).data);
    } catch {}
  };

  const fetchContentPolicy = async () => {
    try {
      const r = await fetch(`${API_URL}/api/v1/admin/content-policy`, { headers: headers() });
      if (r.ok) setContentPolicy((await r.json()).data);
    } catch {}
  };

  const fetchAudit = async () => {
    try {
      const r = await fetch(`${API_URL}/api/v1/admin/audit?limit=20`, { headers: headers() });
      if (r.ok) setAuditEvents((await r.json()).data);
    } catch {}
  };

  const updateUserRole = async (userId: string, role: string) => {
    await fetch(`${API_URL}/api/v1/admin/users/${userId}`, {
      method: "PATCH",
      headers: headers(),
      body: JSON.stringify({ role }),
    });
    fetchUsers();
  };

  if (loading || !user) return null;

  const tabs = [
    { key: "overview", label: "📊 Overview" },
    { key: "users", label: "👥 Users" },
    { key: "models", label: "🤖 Models" },
    { key: "safety", label: "🛡️ Safety" },
    { key: "audit", label: "📋 Audit" },
  ];

  return (
    <div className="min-h-screen p-6" style={{ backgroundColor: "var(--bg-primary)" }}>
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">⚡ Admin Console</h1>
            <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
              {user.name} • Organization Admin
            </p>
          </div>
          <div className="flex gap-3">
            <a href="/chat" className="px-4 py-2 rounded-lg text-sm" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
              ← Chat
            </a>
            <a href="/dashboard" className="px-4 py-2 rounded-lg text-sm" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
              📊 Usage
            </a>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-6 overflow-x-auto" style={{ borderBottom: "1px solid var(--border)" }}>
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key as any)}
              className="px-4 py-2 text-sm font-medium whitespace-nowrap transition-colors"
              style={{
                borderBottom: tab === t.key ? "2px solid var(--accent)" : "2px solid transparent",
                color: tab === t.key ? "var(--text-primary)" : "var(--text-secondary)",
              }}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {tab === "overview" && overview && (
          <div>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-8">
              <Card label="Total Users" value={String(overview.users.total)} />
              <Card label="Active (7d)" value={String(overview.users.active)} />
              <Card label="Conversations" value={String(overview.conversations)} />
              <Card label="Messages" value={String(overview.messages)} />
              <Card label="Cost (7d)" value={`$${overview.usage.cost_usd.toFixed(2)}`} />
              <Card label="Safety Events" value={String(overview.safety_events)} accent={overview.safety_events > 0} />
            </div>
          </div>
        )}

        {tab === "users" && (
          <div className="rounded-xl overflow-hidden" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                  <th className="text-left px-4 py-3">Name</th>
                  <th className="text-left px-4 py-3">Email</th>
                  <th className="text-left px-4 py-3">Role</th>
                  <th className="text-left px-4 py-3">Last Login</th>
                  <th className="text-left px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.slice(0, 20).map((u) => (
                  <tr key={u.id} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td className="px-4 py-2">{u.name}</td>
                    <td className="px-4 py-2" style={{ color: "var(--text-secondary)" }}>{u.email}</td>
                    <td className="px-4 py-2">
                      <select
                        value={u.role}
                        onChange={(e) => updateUserRole(u.id, e.target.value)}
                        className="text-xs rounded px-2 py-1"
                        style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
                      >
                        <option value="admin">Admin</option>
                        <option value="manager">Manager</option>
                        <option value="member">Member</option>
                        <option value="viewer">Viewer</option>
                      </select>
                    </td>
                    <td className="px-4 py-2 text-xs" style={{ color: "var(--text-secondary)" }}>
                      {u.last_login_at ? new Date(u.last_login_at).toLocaleDateString() : "Never"}
                    </td>
                    <td className="px-4 py-2">
                      {u.id !== user.id && (
                        <button className="text-xs px-2 py-1 rounded" style={{ color: "var(--error)" }}>
                          Deactivate
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {tab === "models" && (
          <div className="grid gap-4">
            {models.map((m: any) => (
              <div
                key={m.id}
                className="rounded-xl p-4 flex items-center justify-between"
                style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}
              >
                <div>
                  <h3 className="font-medium">{m.display_name}</h3>
                  <p className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
                    {m.provider} • {m.id} • {m.max_context_tokens?.toLocaleString()} ctx
                  </p>
                </div>
                <div className="text-right text-sm">
                  <p>${m.input_cost_per_1k}/1k in</p>
                  <p>${m.output_cost_per_1k}/1k out</p>
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === "safety" && contentPolicy && (
          <div className="rounded-xl p-6" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
            <h2 className="text-lg font-semibold mb-4">Content Safety Policy</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <PolicyRow label="PII Action" value={contentPolicy.pii_action} />
              <PolicyRow label="Injection Action" value={contentPolicy.injection_action} />
              <PolicyRow label="DLP Engine" value={contentPolicy.dlp_enabled ? "Enabled" : "Disabled"} />
              <PolicyRow label="Outbound Scan" value={contentPolicy.outbound_scan ? "Enabled" : "Disabled"} />
            </div>
            <p className="text-xs mt-4" style={{ color: "var(--text-secondary)" }}>
              Edit via API: PUT /api/v1/admin/content-policy
            </p>
          </div>
        )}

        {tab === "audit" && (
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-lg font-semibold">Recent Audit Events</h2>
              <a
                href={`${API_URL}/api/v1/admin/audit/export?days=30`}
                className="text-xs px-3 py-1 rounded-lg"
                style={{ backgroundColor: "var(--accent)", color: "white" }}
                target="_blank"
              >
                Export CSV
              </a>
            </div>
            {auditEvents.length === 0 ? (
              <p style={{ color: "var(--text-secondary)" }}>No audit events yet</p>
            ) : (
              <div className="rounded-xl overflow-hidden" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
                <table className="w-full text-sm">
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                      <th className="text-left px-4 py-2">Time</th>
                      <th className="text-left px-4 py-2">Action</th>
                      <th className="text-left px-4 py-2">Resource</th>
                      <th className="text-left px-4 py-2">Safety</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditEvents.map((e: any) => (
                      <tr key={e.id} style={{ borderBottom: "1px solid var(--border)" }}>
                        <td className="px-4 py-2 text-xs">{new Date(e.created_at).toLocaleString()}</td>
                        <td className="px-4 py-2">{e.action}</td>
                        <td className="px-4 py-2" style={{ color: "var(--text-secondary)" }}>{e.resource_type}</td>
                        <td className="px-4 py-2">{e.safety_event ? "⚠️" : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Card({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="rounded-xl p-4" style={{ backgroundColor: "var(--bg-secondary)", border: `1px solid ${accent ? "var(--error)" : "var(--border)"}` }}>
      <p className="text-xs" style={{ color: "var(--text-secondary)" }}>{label}</p>
      <p className="text-xl font-bold mt-1">{value}</p>
    </div>
  );
}

function PolicyRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-2" style={{ borderBottom: "1px solid var(--border)" }}>
      <span style={{ color: "var(--text-secondary)" }}>{label}</span>
      <span className="font-medium capitalize">{value}</span>
    </div>
  );
}
