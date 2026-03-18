"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

interface ModelVersion {
  id: string;
  version: string;
  status: string;
  release_notes: string | null;
  training_data: any;
  intended_use: string | null;
  limitations: string | null;
  license: string | null;
  architecture: any;
  eval_results: any;
  artifact_uri: string | null;
  artifact_size_bytes: number | null;
  gateway_config: any;
  published_at: string | null;
  created_at: string;
}

interface Model {
  id: string;
  name: string;
  display_name: string | null;
  description: string | null;
  visibility: string;
  department_id: string | null;
  tags: string[];
  created_by: string;
  created_at: string;
  updated_at: string;
  version_count: number;
  latest_version: { version: string; status: string; published_at: string | null } | null;
  versions?: ModelVersion[];
}

type Tab = "browse" | "mine" | "create";
type DetailTab = "overview" | "versions" | "card" | "access";

export default function ModelRegistryPage() {
  const { user, loading } = useAuth();
  const [tab, setTab] = useState<Tab>("browse");
  const [models, setModels] = useState<Model[]>([]);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Model | null>(null);
  const [detailTab, setDetailTab] = useState<DetailTab>("overview");
  const [creating, setCreating] = useState(false);
  const [creatingVersion, setCreatingVersion] = useState(false);

  // Create model form
  const [newModel, setNewModel] = useState({ name: "", display_name: "", description: "", visibility: "private", tags: "" });

  // Create version form
  const [newVersion, setNewVersion] = useState({
    version: "", release_notes: "", intended_use: "", limitations: "", license: "",
    architecture: "", eval_results: "", artifact_uri: "",
  });

  useEffect(() => {
    if (!loading && !user) window.location.href = "/login";
  }, [user, loading]);

  const getToken = () => localStorage.getItem("access_token");
  const headers = () => ({ Authorization: `Bearer ${getToken()}`, "Content-Type": "application/json" });

  const fetchModels = async () => {
    try {
      const params = new URLSearchParams();
      if (search) params.set("q", search);
      const r = await fetch(`${API_URL}/api/v1/registry?${params}`, { headers: headers() });
      if (r.ok) setModels((await r.json()).data);
    } catch {}
  };

  const fetchModel = async (id: string) => {
    try {
      const r = await fetch(`${API_URL}/api/v1/registry/${id}`, { headers: headers() });
      if (r.ok) {
        const data = (await r.json()).data;
        setSelected(data);
      }
    } catch {}
  };

  useEffect(() => {
    if (user) fetchModels();
  }, [user, search]);

  const createModel = async () => {
    setCreating(true);
    try {
      const body = {
        name: newModel.name,
        display_name: newModel.display_name || newModel.name,
        description: newModel.description,
        visibility: newModel.visibility,
        tags: newModel.tags ? newModel.tags.split(",").map((t) => t.trim()).filter(Boolean) : [],
      };
      const r = await fetch(`${API_URL}/api/v1/registry`, { method: "POST", headers: headers(), body: JSON.stringify(body) });
      if (r.ok) {
        const data = (await r.json()).data;
        setNewModel({ name: "", display_name: "", description: "", visibility: "private", tags: "" });
        setTab("browse");
        fetchModels();
        fetchModel(data.id);
      }
    } catch {}
    setCreating(false);
  };

  const createVersion = async () => {
    if (!selected) return;
    setCreatingVersion(true);
    try {
      const body: any = {
        version: newVersion.version,
        release_notes: newVersion.release_notes || null,
        intended_use: newVersion.intended_use || null,
        limitations: newVersion.limitations || null,
        license: newVersion.license || null,
        artifact_uri: newVersion.artifact_uri || null,
      };
      if (newVersion.architecture) {
        try { body.architecture = JSON.parse(newVersion.architecture); } catch {}
      }
      if (newVersion.eval_results) {
        try { body.eval_results = JSON.parse(newVersion.eval_results); } catch {}
      }
      const r = await fetch(`${API_URL}/api/v1/registry/${selected.id}/versions`, {
        method: "POST", headers: headers(), body: JSON.stringify(body),
      });
      if (r.ok) {
        setNewVersion({ version: "", release_notes: "", intended_use: "", limitations: "", license: "", architecture: "", eval_results: "", artifact_uri: "" });
        fetchModel(selected.id);
      }
    } catch {}
    setCreatingVersion(false);
  };

  const publishVersion = async (versionId: string) => {
    if (!selected) return;
    try {
      const r = await fetch(`${API_URL}/api/v1/registry/${selected.id}/versions/${versionId}/publish`, {
        method: "POST", headers: headers(),
      });
      if (r.ok) fetchModel(selected.id);
    } catch {}
  };

  const deleteModel = async () => {
    if (!selected || !confirm("Archive this model?")) return;
    try {
      await fetch(`${API_URL}/api/v1/registry/${selected.id}`, { method: "DELETE", headers: headers() });
      setSelected(null);
      fetchModels();
    } catch {}
  };

  if (loading || !user) return null;

  const visibilityBadge = (v: string) => {
    const colors: Record<string, string> = {
      private: "bg-gray-700 text-gray-300",
      department: "bg-blue-900 text-blue-300",
      organization: "bg-green-900 text-green-300",
    };
    return <span className={`px-2 py-0.5 rounded text-xs ${colors[v] || ""}`}>{v}</span>;
  };

  const statusBadge = (s: string) => {
    const colors: Record<string, string> = {
      draft: "bg-yellow-900 text-yellow-300",
      published: "bg-green-900 text-green-300",
      deprecated: "bg-red-900 text-red-300",
    };
    return <span className={`px-2 py-0.5 rounded text-xs ${colors[s] || ""}`}>{s}</span>;
  };

  const inputStyle = {
    backgroundColor: "var(--bg-primary)",
    border: "1px solid var(--border)",
    color: "var(--text-primary)",
  };

  return (
    <div className="min-h-screen p-6" style={{ backgroundColor: "var(--bg-primary)" }}>
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">📦 Model Registry</h1>
            <p className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>
              Catalog, version, and share institutional AI models.
            </p>
          </div>
          <a href="/chat" className="px-4 py-2 rounded-lg text-sm" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
            ← Back to Chat
          </a>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-6 rounded-lg p-1" style={{ backgroundColor: "var(--bg-secondary)" }}>
          {(["browse", "mine", "create"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => { setTab(t); if (t !== "create") setSelected(null); }}
              className="px-4 py-2 rounded-md text-sm font-medium transition-colors capitalize"
              style={{
                backgroundColor: tab === t ? "var(--accent)" : "transparent",
                color: tab === t ? "white" : "var(--text-secondary)",
              }}
            >
              {t === "browse" ? "Browse All" : t === "mine" ? "My Models" : "+ Register Model"}
            </button>
          ))}
        </div>

        {/* Create form */}
        {tab === "create" && (
          <div className="rounded-xl p-6 mb-6" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
            <h2 className="text-lg font-semibold mb-4">Register a New Model</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium mb-1" style={{ color: "var(--text-secondary)" }}>Name (slug)</label>
                <input value={newModel.name} onChange={(e) => setNewModel({ ...newModel, name: e.target.value })} placeholder="my-custom-model" className="w-full px-3 py-2 rounded-lg text-sm" style={inputStyle} />
              </div>
              <div>
                <label className="block text-xs font-medium mb-1" style={{ color: "var(--text-secondary)" }}>Display Name</label>
                <input value={newModel.display_name} onChange={(e) => setNewModel({ ...newModel, display_name: e.target.value })} placeholder="My Custom Model" className="w-full px-3 py-2 rounded-lg text-sm" style={inputStyle} />
              </div>
              <div className="md:col-span-2">
                <label className="block text-xs font-medium mb-1" style={{ color: "var(--text-secondary)" }}>Description</label>
                <textarea value={newModel.description} onChange={(e) => setNewModel({ ...newModel, description: e.target.value })} placeholder="What does this model do?" rows={2} className="w-full px-3 py-2 rounded-lg text-sm resize-none" style={inputStyle} />
              </div>
              <div>
                <label className="block text-xs font-medium mb-1" style={{ color: "var(--text-secondary)" }}>Visibility</label>
                <select value={newModel.visibility} onChange={(e) => setNewModel({ ...newModel, visibility: e.target.value })} className="w-full px-3 py-2 rounded-lg text-sm" style={inputStyle}>
                  <option value="private">Private</option>
                  <option value="department">Department</option>
                  <option value="organization">Organization-wide</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium mb-1" style={{ color: "var(--text-secondary)" }}>Tags (comma-separated)</label>
                <input value={newModel.tags} onChange={(e) => setNewModel({ ...newModel, tags: e.target.value })} placeholder="nlp, healthcare, summarization" className="w-full px-3 py-2 rounded-lg text-sm" style={inputStyle} />
              </div>
            </div>
            <button onClick={createModel} disabled={creating || !newModel.name.trim()} className="mt-4 px-6 py-2.5 rounded-lg font-medium text-sm disabled:opacity-50" style={{ backgroundColor: "var(--accent)", color: "white" }}>
              {creating ? "Creating..." : "Register Model"}
            </button>
          </div>
        )}

        {/* Browse / My Models */}
        {tab !== "create" && !selected && (
          <>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search models..."
              className="w-full px-4 py-2.5 rounded-xl text-sm mb-4"
              style={inputStyle}
            />
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {models.filter((m) => tab === "browse" || m.created_by === (user as any)?.id).map((m) => (
                <button
                  key={m.id}
                  onClick={() => fetchModel(m.id)}
                  className="text-left rounded-xl p-5 transition-all hover:scale-[1.01]"
                  style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}
                >
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="font-semibold text-sm truncate">{m.display_name || m.name}</h3>
                    {visibilityBadge(m.visibility)}
                  </div>
                  <p className="text-xs mb-3 line-clamp-2" style={{ color: "var(--text-secondary)" }}>
                    {m.description || "No description"}
                  </p>
                  <div className="flex items-center gap-2 flex-wrap">
                    {(m.tags || []).slice(0, 3).map((tag) => (
                      <span key={tag} className="px-2 py-0.5 rounded text-xs" style={{ backgroundColor: "var(--bg-primary)", color: "var(--text-secondary)" }}>
                        {tag}
                      </span>
                    ))}
                  </div>
                  <div className="flex items-center justify-between mt-3 text-xs" style={{ color: "var(--text-secondary)" }}>
                    <span>{m.version_count} version{m.version_count !== 1 ? "s" : ""}</span>
                    <span>{m.latest_version ? `v${m.latest_version.version}` : "no release"}</span>
                  </div>
                </button>
              ))}
              {models.length === 0 && (
                <div className="col-span-full text-center py-16" style={{ color: "var(--text-secondary)" }}>
                  <p className="text-4xl mb-3">📦</p>
                  <p>No models registered yet.</p>
                  <button onClick={() => setTab("create")} className="mt-3 text-sm underline" style={{ color: "var(--accent)" }}>
                    Register your first model
                  </button>
                </div>
              )}
            </div>
          </>
        )}

        {/* Model Detail */}
        {selected && tab !== "create" && (
          <div>
            <button onClick={() => setSelected(null)} className="text-sm mb-4 flex items-center gap-1" style={{ color: "var(--text-secondary)" }}>
              ← Back to list
            </button>

            <div className="rounded-xl p-6 mb-4" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
              <div className="flex items-start justify-between">
                <div>
                  <h2 className="text-xl font-bold">{selected.display_name || selected.name}</h2>
                  <p className="text-sm mt-1 font-mono" style={{ color: "var(--text-secondary)" }}>{selected.name}</p>
                </div>
                <div className="flex items-center gap-2">
                  {visibilityBadge(selected.visibility)}
                  <button onClick={deleteModel} className="px-3 py-1 rounded text-xs" style={{ color: "var(--error)" }}>Archive</button>
                </div>
              </div>
              {selected.description && <p className="mt-3 text-sm" style={{ color: "var(--text-secondary)" }}>{selected.description}</p>}
              {(selected.tags || []).length > 0 && (
                <div className="flex gap-2 mt-3 flex-wrap">
                  {selected.tags.map((tag) => (
                    <span key={tag} className="px-2 py-0.5 rounded text-xs" style={{ backgroundColor: "var(--bg-primary)", color: "var(--text-secondary)" }}>{tag}</span>
                  ))}
                </div>
              )}
            </div>

            {/* Detail tabs */}
            <div className="flex gap-1 mb-4 rounded-lg p-1" style={{ backgroundColor: "var(--bg-secondary)" }}>
              {(["overview", "versions", "card"] as DetailTab[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setDetailTab(t)}
                  className="px-4 py-2 rounded-md text-sm font-medium transition-colors capitalize"
                  style={{
                    backgroundColor: detailTab === t ? "var(--accent)" : "transparent",
                    color: detailTab === t ? "white" : "var(--text-secondary)",
                  }}
                >
                  {t === "card" ? "Model Card" : t}
                </button>
              ))}
            </div>

            {/* Versions tab */}
            {detailTab === "versions" && (
              <div>
                {/* New version form */}
                <div className="rounded-xl p-5 mb-4" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
                  <h3 className="text-sm font-semibold mb-3">Create New Version</h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div>
                      <label className="block text-xs mb-1" style={{ color: "var(--text-secondary)" }}>Version</label>
                      <input value={newVersion.version} onChange={(e) => setNewVersion({ ...newVersion, version: e.target.value })} placeholder="1.0.0" className="w-full px-3 py-2 rounded-lg text-sm" style={inputStyle} />
                    </div>
                    <div>
                      <label className="block text-xs mb-1" style={{ color: "var(--text-secondary)" }}>License</label>
                      <input value={newVersion.license} onChange={(e) => setNewVersion({ ...newVersion, license: e.target.value })} placeholder="Apache-2.0" className="w-full px-3 py-2 rounded-lg text-sm" style={inputStyle} />
                    </div>
                    <div>
                      <label className="block text-xs mb-1" style={{ color: "var(--text-secondary)" }}>Artifact URI</label>
                      <input value={newVersion.artifact_uri} onChange={(e) => setNewVersion({ ...newVersion, artifact_uri: e.target.value })} placeholder="s3://models/..." className="w-full px-3 py-2 rounded-lg text-sm" style={inputStyle} />
                    </div>
                    <div className="md:col-span-3">
                      <label className="block text-xs mb-1" style={{ color: "var(--text-secondary)" }}>Release Notes</label>
                      <textarea value={newVersion.release_notes} onChange={(e) => setNewVersion({ ...newVersion, release_notes: e.target.value })} placeholder="What changed..." rows={2} className="w-full px-3 py-2 rounded-lg text-sm resize-none" style={inputStyle} />
                    </div>
                    <div className="md:col-span-3">
                      <label className="block text-xs mb-1" style={{ color: "var(--text-secondary)" }}>Intended Use</label>
                      <textarea value={newVersion.intended_use} onChange={(e) => setNewVersion({ ...newVersion, intended_use: e.target.value })} placeholder="What this model is designed for..." rows={2} className="w-full px-3 py-2 rounded-lg text-sm resize-none" style={inputStyle} />
                    </div>
                    <div className="md:col-span-3">
                      <label className="block text-xs mb-1" style={{ color: "var(--text-secondary)" }}>Known Limitations</label>
                      <textarea value={newVersion.limitations} onChange={(e) => setNewVersion({ ...newVersion, limitations: e.target.value })} placeholder="Known failure modes, biases, edge cases..." rows={2} className="w-full px-3 py-2 rounded-lg text-sm resize-none" style={inputStyle} />
                    </div>
                    <div>
                      <label className="block text-xs mb-1" style={{ color: "var(--text-secondary)" }}>Architecture (JSON)</label>
                      <input value={newVersion.architecture} onChange={(e) => setNewVersion({ ...newVersion, architecture: e.target.value })} placeholder='{"base":"llama-3-8b","method":"LoRA"}' className="w-full px-3 py-2 rounded-lg text-sm" style={inputStyle} />
                    </div>
                    <div className="md:col-span-2">
                      <label className="block text-xs mb-1" style={{ color: "var(--text-secondary)" }}>Eval Results (JSON)</label>
                      <input value={newVersion.eval_results} onChange={(e) => setNewVersion({ ...newVersion, eval_results: e.target.value })} placeholder='{"mmlu":0.72,"human_eval":0.65}' className="w-full px-3 py-2 rounded-lg text-sm" style={inputStyle} />
                    </div>
                  </div>
                  <button onClick={createVersion} disabled={creatingVersion || !newVersion.version.trim()} className="mt-3 px-5 py-2 rounded-lg font-medium text-sm disabled:opacity-50" style={{ backgroundColor: "var(--accent)", color: "white" }}>
                    {creatingVersion ? "Creating..." : "Create Draft Version"}
                  </button>
                </div>

                {/* Version list */}
                <div className="space-y-3">
                  {(selected.versions || []).map((v) => (
                    <div key={v.id} className="rounded-xl p-5" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-3">
                          <span className="font-mono font-semibold">v{v.version}</span>
                          {statusBadge(v.status)}
                        </div>
                        <div className="flex items-center gap-2">
                          {v.status === "draft" && (
                            <button onClick={() => publishVersion(v.id)} className="px-3 py-1 rounded text-xs font-medium" style={{ backgroundColor: "var(--accent)", color: "white" }}>
                              Publish
                            </button>
                          )}
                          <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
                            {v.published_at ? `Published ${new Date(v.published_at).toLocaleDateString()}` : `Created ${new Date(v.created_at).toLocaleDateString()}`}
                          </span>
                        </div>
                      </div>
                      {v.release_notes && <p className="text-sm mb-2" style={{ color: "var(--text-secondary)" }}>{v.release_notes}</p>}
                      <div className="flex gap-4 text-xs" style={{ color: "var(--text-secondary)" }}>
                        {v.license && <span>📄 {v.license}</span>}
                        {v.artifact_uri && <span>📁 {v.artifact_uri}</span>}
                        {v.architecture && <span>🏗️ {v.architecture.base || "custom"}</span>}
                        {v.gateway_config && <span>🔌 Gateway-connected</span>}
                      </div>
                    </div>
                  ))}
                  {(selected.versions || []).length === 0 && (
                    <div className="text-center py-8" style={{ color: "var(--text-secondary)" }}>
                      No versions yet. Create the first one above.
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Overview tab */}
            {detailTab === "overview" && (
              <div className="rounded-xl p-6" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-xs font-medium block mb-1" style={{ color: "var(--text-secondary)" }}>Versions</span>
                    <span className="text-lg font-bold">{selected.version_count}</span>
                  </div>
                  <div>
                    <span className="text-xs font-medium block mb-1" style={{ color: "var(--text-secondary)" }}>Latest Release</span>
                    <span className="text-lg font-bold">{selected.latest_version ? `v${selected.latest_version.version}` : "—"}</span>
                  </div>
                  <div>
                    <span className="text-xs font-medium block mb-1" style={{ color: "var(--text-secondary)" }}>Created</span>
                    <span>{new Date(selected.created_at).toLocaleDateString()}</span>
                  </div>
                  <div>
                    <span className="text-xs font-medium block mb-1" style={{ color: "var(--text-secondary)" }}>Updated</span>
                    <span>{new Date(selected.updated_at).toLocaleDateString()}</span>
                  </div>
                </div>
              </div>
            )}

            {/* Model Card tab */}
            {detailTab === "card" && (
              <div className="space-y-4">
                {selected.versions && selected.versions.length > 0 ? (
                  (() => {
                    const v = selected.versions.find((v) => v.status === "published") || selected.versions[0];
                    return (
                      <>
                        <div className="rounded-xl p-6" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
                          <h3 className="font-semibold mb-1">Model Card — v{v.version}</h3>
                          <p className="text-xs mb-4" style={{ color: "var(--text-secondary)" }}>{statusBadge(v.status)}</p>

                          {v.intended_use && (
                            <div className="mb-4">
                              <h4 className="text-xs font-semibold uppercase tracking-wide mb-1" style={{ color: "var(--text-secondary)" }}>Intended Use</h4>
                              <p className="text-sm whitespace-pre-wrap">{v.intended_use}</p>
                            </div>
                          )}

                          {v.limitations && (
                            <div className="mb-4">
                              <h4 className="text-xs font-semibold uppercase tracking-wide mb-1" style={{ color: "var(--text-secondary)" }}>Known Limitations</h4>
                              <p className="text-sm whitespace-pre-wrap">{v.limitations}</p>
                            </div>
                          )}

                          {v.training_data && (
                            <div className="mb-4">
                              <h4 className="text-xs font-semibold uppercase tracking-wide mb-1" style={{ color: "var(--text-secondary)" }}>Training Data</h4>
                              <pre className="text-xs p-3 rounded-lg overflow-auto" style={{ backgroundColor: "var(--bg-primary)" }}>
                                {JSON.stringify(v.training_data, null, 2)}
                              </pre>
                            </div>
                          )}

                          {v.architecture && (
                            <div className="mb-4">
                              <h4 className="text-xs font-semibold uppercase tracking-wide mb-1" style={{ color: "var(--text-secondary)" }}>Architecture</h4>
                              <pre className="text-xs p-3 rounded-lg overflow-auto" style={{ backgroundColor: "var(--bg-primary)" }}>
                                {JSON.stringify(v.architecture, null, 2)}
                              </pre>
                            </div>
                          )}

                          {v.eval_results && (
                            <div className="mb-4">
                              <h4 className="text-xs font-semibold uppercase tracking-wide mb-1" style={{ color: "var(--text-secondary)" }}>Evaluation Results</h4>
                              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                                {Object.entries(v.eval_results).map(([k, val]) => (
                                  <div key={k} className="p-3 rounded-lg text-center" style={{ backgroundColor: "var(--bg-primary)" }}>
                                    <div className="text-lg font-bold">{typeof val === "number" ? (val * 100).toFixed(1) + "%" : String(val)}</div>
                                    <div className="text-xs" style={{ color: "var(--text-secondary)" }}>{k}</div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          <div className="flex gap-4 text-xs pt-2" style={{ color: "var(--text-secondary)", borderTop: "1px solid var(--border)" }}>
                            {v.license && <span>📄 License: {v.license}</span>}
                            {v.artifact_uri && <span>📁 Artifact: {v.artifact_uri}</span>}
                            {v.artifact_size_bytes && <span>💾 {(v.artifact_size_bytes / 1e9).toFixed(1)} GB</span>}
                          </div>
                        </div>
                      </>
                    );
                  })()
                ) : (
                  <div className="text-center py-12 rounded-xl" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                    No versions yet — create a version to generate a model card.
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
