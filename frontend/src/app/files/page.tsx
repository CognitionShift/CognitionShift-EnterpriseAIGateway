"use client";

import { useEffect, useState, useRef } from "react";
import { useAuth } from "@/lib/auth-context";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

interface FileItem {
  id: string;
  name: string;
  mime_type: string;
  size_bytes: number;
  status: string;
  chunk_count: number;
  created_at: string;
}

export default function FilesPage() {
  const { user, loading } = useAuth();
  const [files, setFiles] = useState<FileItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!loading && !user) window.location.href = "/login";
  }, [user, loading]);

  const getToken = () => localStorage.getItem("access_token");

  useEffect(() => {
    if (user) fetchFiles();
  }, [user]);

  const fetchFiles = async () => {
    try {
      const r = await fetch(`${API_URL}/api/v1/files`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (r.ok) setFiles((await r.json()).data);
    } catch {}
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);

    try {
      const r = await fetch(`${API_URL}/api/v1/files`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
        body: formData,
      });
      if (r.ok) {
        fetchFiles();
      } else {
        const err = await r.json().catch(() => ({}));
        alert(err.detail || "Upload failed");
      }
    } catch {
      alert("Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDelete = async (id: string) => {
    await fetch(`${API_URL}/api/v1/files/${id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    fetchFiles();
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    try {
      const r = await fetch(`${API_URL}/api/v1/search?q=${encodeURIComponent(searchQuery)}`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (r.ok) setSearchResults((await r.json()).data.results);
    } catch {}
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  if (loading || !user) return null;

  return (
    <div className="min-h-screen p-6" style={{ backgroundColor: "var(--bg-primary)" }}>
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold">📁 Files & Knowledge</h1>
            <p className="text-sm mt-1" style={{ color: "var(--text-secondary)" }}>
              Upload documents for RAG-powered answers. Search across all your files.
            </p>
          </div>
          <a href="/chat" className="px-4 py-2 rounded-lg text-sm" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
            ← Back to Chat
          </a>
        </div>

        {/* Upload + Search */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
          {/* Upload */}
          <div className="rounded-xl p-6" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
            <h2 className="font-semibold mb-3">Upload Document</h2>
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleUpload}
              accept=".txt,.csv,.md,.pdf,.docx,.xlsx,.json"
              className="hidden"
              id="file-upload"
            />
            <label
              htmlFor="file-upload"
              className="flex items-center justify-center p-8 rounded-lg cursor-pointer transition-colors border-2 border-dashed"
              style={{ borderColor: "var(--border)", color: "var(--text-secondary)" }}
            >
              {uploading ? "⏳ Processing..." : "📎 Click to upload (TXT, CSV, PDF, DOCX, MD)"}
            </label>
          </div>

          {/* Search */}
          <div className="rounded-xl p-6" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
            <h2 className="font-semibold mb-3">Search Documents</h2>
            <div className="flex gap-2">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                placeholder="Search across all files..."
                className="flex-1 px-3 py-2 rounded-lg text-sm"
                style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
              />
              <button
                onClick={handleSearch}
                className="px-4 py-2 rounded-lg text-sm font-medium"
                style={{ backgroundColor: "var(--accent)", color: "white" }}
              >
                🔍
              </button>
            </div>
            {searchResults.length > 0 && (
              <div className="mt-3 space-y-2">
                {searchResults.map((r, i) => (
                  <div key={i} className="text-xs p-2 rounded" style={{ backgroundColor: "var(--bg-primary)" }}>
                    <span className="text-green-400">Score: {r.score.toFixed(2)}</span>
                    <p className="mt-1" style={{ color: "var(--text-secondary)" }}>{r.content}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* File list */}
        <div className="rounded-xl overflow-hidden" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
          <div className="px-4 py-3" style={{ borderBottom: "1px solid var(--border)" }}>
            <h2 className="font-semibold">Your Files ({files.length})</h2>
          </div>
          {files.length === 0 ? (
            <p className="text-center py-12" style={{ color: "var(--text-secondary)" }}>
              No files yet. Upload a document to get started.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                  <th className="text-left px-4 py-2">Name</th>
                  <th className="text-left px-4 py-2">Type</th>
                  <th className="text-right px-4 py-2">Size</th>
                  <th className="text-right px-4 py-2">Chunks</th>
                  <th className="text-left px-4 py-2">Status</th>
                  <th className="text-right px-4 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {files.map((f) => (
                  <tr key={f.id} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td className="px-4 py-2 font-medium">{f.name}</td>
                    <td className="px-4 py-2" style={{ color: "var(--text-secondary)" }}>{f.mime_type.split("/")[1]}</td>
                    <td className="px-4 py-2 text-right">{formatSize(f.size_bytes)}</td>
                    <td className="px-4 py-2 text-right">{f.chunk_count}</td>
                    <td className="px-4 py-2">
                      <span className={`text-xs px-2 py-0.5 rounded ${f.status === "ready" ? "bg-green-900 text-green-300" : "bg-yellow-900 text-yellow-300"}`}>
                        {f.status}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <button onClick={() => handleDelete(f.id)} className="text-xs" style={{ color: "var(--error)" }}>
                        Delete
                      </button>
                    </td>
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
