"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

interface UsageData {
  period: string;
  period_start: string;
  usage: {
    tokens: { input: number; output: number; total: number };
    cost_usd: number;
    requests: number;
    active_users?: number;
  };
  scope?: string;
}

interface BreakdownEntry {
  model_id?: string;
  user_id?: string;
  date?: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  requests: number;
}

export default function DashboardPage() {
  const { user, loading, logout } = useAuth();
  const [period, setPeriod] = useState("daily");
  const [myUsage, setMyUsage] = useState<UsageData | null>(null);
  const [orgUsage, setOrgUsage] = useState<UsageData | null>(null);
  const [breakdown, setBreakdown] = useState<BreakdownEntry[]>([]);
  const [breakdownType, setBreakdownType] = useState("model");

  useEffect(() => {
    if (!loading && !user) window.location.href = "/login";
  }, [user, loading]);

  useEffect(() => {
    if (user) {
      fetchUsage();
      fetchBreakdown();
    }
  }, [user, period, breakdownType]);

  const getToken = () => localStorage.getItem("access_token");

  const fetchUsage = async () => {
    const token = getToken();
    const headers = { Authorization: `Bearer ${token}` };

    try {
      const [myResp, summaryResp] = await Promise.all([
        fetch(`${API_URL}/api/v1/usage/me?period=${period}`, { headers }),
        fetch(`${API_URL}/api/v1/usage/summary?period=${period}`, { headers }),
      ]);
      if (myResp.ok) {
        const d = await myResp.json();
        setMyUsage(d.data);
      }
      if (summaryResp.ok) {
        const d = await summaryResp.json();
        setOrgUsage(d.data);
      }
    } catch (err) {
      console.error("Failed to fetch usage:", err);
    }
  };

  const fetchBreakdown = async () => {
    const token = getToken();
    try {
      const resp = await fetch(
        `${API_URL}/api/v1/usage/breakdown?group_by=${breakdownType}&days=7`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (resp.ok) {
        const d = await resp.json();
        setBreakdown(d.data.breakdown);
      }
    } catch (err) {
      console.error("Failed to fetch breakdown:", err);
    }
  };

  if (loading || !user) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-pulse" style={{ color: "var(--text-secondary)" }}>
          Loading...
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen p-6" style={{ backgroundColor: "var(--bg-primary)" }}>
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold">⚡ Usage Dashboard</h1>
            <p className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>
              {user.name} • {user.role}
            </p>
          </div>
          <div className="flex gap-3">
            <a
              href="/chat"
              className="px-4 py-2 rounded-lg text-sm font-medium"
              style={{ backgroundColor: "var(--accent)", color: "white" }}
            >
              ← Back to Chat
            </a>
            <button
              onClick={logout}
              className="px-4 py-2 rounded-lg text-sm"
              style={{ backgroundColor: "var(--bg-secondary)", color: "var(--text-secondary)", border: "1px solid var(--border)" }}
            >
              Logout
            </button>
          </div>
        </div>

        {/* Period selector */}
        <div className="flex gap-2 mb-6">
          {["daily", "weekly", "monthly"].map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className="px-4 py-1.5 rounded-lg text-sm font-medium transition-colors capitalize"
              style={{
                backgroundColor: period === p ? "var(--accent)" : "var(--bg-secondary)",
                color: period === p ? "white" : "var(--text-secondary)",
                border: `1px solid ${period === p ? "var(--accent)" : "var(--border)"}`,
              }}
            >
              {p}
            </button>
          ))}
        </div>

        {/* Stats cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <StatCard
            label="My Tokens"
            value={myUsage?.usage.tokens.total?.toLocaleString() || "0"}
            sub={`${myUsage?.usage.tokens.input || 0} in / ${myUsage?.usage.tokens.output || 0} out`}
          />
          <StatCard
            label="My Cost"
            value={`$${myUsage?.usage.cost_usd?.toFixed(4) || "0.00"}`}
            sub={`${myUsage?.usage.requests || 0} requests`}
          />
          {orgUsage?.scope === "org" && (
            <>
              <StatCard
                label="Org Tokens"
                value={orgUsage?.usage.tokens.total?.toLocaleString() || "0"}
                sub={`${orgUsage?.usage.active_users || 0} active users`}
              />
              <StatCard
                label="Org Cost"
                value={`$${orgUsage?.usage.cost_usd?.toFixed(4) || "0.00"}`}
                sub={`${orgUsage?.usage.requests || 0} requests`}
              />
            </>
          )}
        </div>

        {/* Breakdown */}
        <div
          className="rounded-xl p-6"
          style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">Breakdown (Last 7 Days)</h2>
            <div className="flex gap-2">
              {["model", "day"].map((t) => (
                <button
                  key={t}
                  onClick={() => setBreakdownType(t)}
                  className="px-3 py-1 rounded text-sm capitalize"
                  style={{
                    backgroundColor: breakdownType === t ? "var(--accent)" : "var(--bg-tertiary)",
                    color: breakdownType === t ? "white" : "var(--text-secondary)",
                  }}
                >
                  By {t}
                </button>
              ))}
            </div>
          </div>

          {breakdown.length === 0 ? (
            <p className="text-center py-8" style={{ color: "var(--text-secondary)" }}>
              No usage data yet
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr style={{ color: "var(--text-secondary)", borderBottom: "1px solid var(--border)" }}>
                  <th className="text-left py-2">{breakdownType === "model" ? "Model" : "Date"}</th>
                  <th className="text-right py-2">Requests</th>
                  <th className="text-right py-2">Tokens</th>
                  <th className="text-right py-2">Cost</th>
                </tr>
              </thead>
              <tbody>
                {breakdown.map((entry, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td className="py-2">{entry.model_id || entry.date || entry.user_id}</td>
                    <td className="text-right py-2">{entry.requests}</td>
                    <td className="text-right py-2">{entry.total_tokens.toLocaleString()}</td>
                    <td className="text-right py-2">${entry.cost_usd.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div
      className="rounded-xl p-5"
      style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}
    >
      <p className="text-xs mb-1" style={{ color: "var(--text-secondary)" }}>
        {label}
      </p>
      <p className="text-2xl font-bold">{value}</p>
      <p className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
        {sub}
      </p>
    </div>
  );
}
