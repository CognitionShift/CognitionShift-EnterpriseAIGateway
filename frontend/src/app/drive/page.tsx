"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { saveTokens } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

interface DriveFile {
  id: string;
  name: string;
  mimeType: string;
  size?: string;
  modifiedTime?: string;
  iconLink?: string;
  webViewLink?: string;
}

interface ImportResult {
  id: string;
  name: string;
  status: string;
  chunk_count: number;
}

export default function DrivePage() {
  const { user, loading, refresh } = useAuth();
  const [connected, setConnected] = useState(false);
  const [googleEmail, setGoogleEmail] = useState("");
  const [files, setFiles] = useState<DriveFile[]>([]);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [importing, setImporting] = useState<Record<string, boolean>>({});
  const [importResults, setImportResults] = useState<Record<string, ImportResult>>({});
  const [error, setError] = useState("");
  const [statusLoading, setStatusLoading] = useState(true);
  const [nextPageToken, setNextPageToken] = useState<string | null>(null);

  // Handle OAuth callback tokens in URL
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const accessToken = params.get("access_token");
    const refreshToken = params.get("refresh_token");
    if (accessToken && refreshToken) {
      saveTokens({
        access_token: accessToken,
        refresh_token: refreshToken,
        token_type: "bearer",
        expires_in: 900,
      });
      // Clean URL
      window.history.replaceState({}, "", "/drive");
      refresh();
    }
  }, [refresh]);

  useEffect(() => {
    if (!loading && !user) window.location.href = "/login";
  }, [user, loading]);

  const getToken = () => localStorage.getItem("access_token");

  // Check connection status
  useEffect(() => {
    if (!user) return;
    checkStatus();
  }, [user]);

  const checkStatus = async () => {
    setStatusLoading(true);
    try {
      const resp = await fetch(`${API_URL}/api/v1/auth/google/status`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (resp.ok) {
        const json = await resp.json();
        setConnected(json.data.connected);
        setGoogleEmail(json.data.google_email || "");
        if (json.data.connected) {
          loadFiles();
        }
      }
    } catch {
      // ignore
    } finally {
      setStatusLoading(false);
    }
  };

  const loadFiles = async (pageToken?: string) => {
    setLoadingFiles(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (pageToken) params.set("page_token", pageToken);
      const resp = await fetch(`${API_URL}/api/v1/drive/files?${params}`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to load files");
      }
      const json = await resp.json();
      if (pageToken) {
        setFiles((prev) => [...prev, ...(json.data || [])]);
      } else {
        setFiles(json.data || []);
      }
      setNextPageToken(json.meta?.next_page_token || null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoadingFiles(false);
    }
  };

  const importFile = async (fileId: string) => {
    setImporting((prev) => ({ ...prev, [fileId]: true }));
    setError("");
    try {
      const resp = await fetch(`${API_URL}/api/v1/drive/import`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${getToken()}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ file_id: fileId }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || "Import failed");
      }
      const json = await resp.json();
      setImportResults((prev) => ({ ...prev, [fileId]: json.data }));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setImporting((prev) => ({ ...prev, [fileId]: false }));
    }
  };

  const disconnect = async () => {
    try {
      await fetch(`${API_URL}/api/v1/auth/google/disconnect`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      setConnected(false);
      setGoogleEmail("");
      setFiles([]);
      setImportResults({});
    } catch {
      setError("Failed to disconnect");
    }
  };

  const formatSize = (size?: string) => {
    if (!size) return "";
    const bytes = parseInt(size, 10);
    if (isNaN(bytes)) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatDate = (iso?: string) => {
    if (!iso) return "";
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  if (loading || statusLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p style={{ color: "var(--text-secondary)" }}>Loading...</p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">Google Drive</h1>

      {error && (
        <div
          className="mb-4 px-4 py-3 rounded-lg text-sm"
          style={{ backgroundColor: "#7f1d1d", color: "#fca5a5" }}
          role="alert"
        >
          {error}
        </div>
      )}

      {!connected ? (
        <div
          className="rounded-xl p-8 text-center"
          style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}
        >
          <div className="mb-4">
            <svg className="mx-auto h-16 w-16 mb-4" viewBox="0 0 87.3 78" xmlns="http://www.w3.org/2000/svg">
              <path d="m6.6 66.85 3.85 6.65c.8 1.4 1.95 2.5 3.3 3.3l13.75-23.8h-27.5c0 1.55.4 3.1 1.2 4.5z" fill="#0066da"/>
              <path d="m43.65 25-13.75-23.8c-1.35.8-2.5 1.9-3.3 3.3l-20.4 35.3c-.8 1.4-1.2 2.95-1.2 4.5h27.5z" fill="#00ac47"/>
              <path d="m73.55 76.8c1.35-.8 2.5-1.9 3.3-3.3l1.6-2.75 7.65-13.25c.8-1.4 1.2-2.95 1.2-4.5h-27.5l11.5 23.8z" fill="#ea4335"/>
              <path d="m43.65 25 13.75-23.8c-1.35-.8-2.9-1.2-4.5-1.2h-18.5c-1.6 0-3.15.45-4.5 1.2z" fill="#00832d"/>
              <path d="m59.8 53h-32.3l-13.75 23.8c1.35.8 2.9 1.2 4.5 1.2h50.8c1.6 0 3.15-.45 4.5-1.2z" fill="#2684fc"/>
              <path d="m73.4 26.5-10.2-17.65c-.8-1.4-1.95-2.5-3.3-3.3l-13.75 23.8 16.15 23.65h27.45c0-1.55-.4-3.1-1.2-4.5z" fill="#ffba00"/>
            </svg>
            <h2 className="text-xl font-semibold mb-2">Connect Google Drive</h2>
            <p style={{ color: "var(--text-secondary)" }} className="mb-6">
              Import files directly from your Google Drive into the AI Gateway for processing and analysis.
            </p>
          </div>
          <a
            href={`${API_URL}/api/v1/auth/google/redirect`}
            className="inline-block px-6 py-3 rounded-lg font-medium text-sm transition-colors"
            style={{ backgroundColor: "var(--accent)", color: "white" }}
          >
            Connect Google Drive
          </a>
        </div>
      ) : (
        <div>
          {/* Connection info */}
          <div
            className="rounded-lg px-4 py-3 mb-6 flex items-center justify-between"
            style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}
          >
            <div className="flex items-center gap-3">
              <div
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: "#22c55e" }}
              />
              <span className="text-sm">
                Connected as <strong>{googleEmail}</strong>
              </span>
            </div>
            <button
              onClick={disconnect}
              className="text-sm px-3 py-1.5 rounded-lg transition-colors"
              style={{ color: "#ef4444", border: "1px solid #ef4444" }}
            >
              Disconnect
            </button>
          </div>

          {/* File list */}
          <div
            className="rounded-xl overflow-hidden"
            style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}
          >
            <div className="px-4 py-3 flex items-center justify-between" style={{ borderBottom: "1px solid var(--border)" }}>
              <h2 className="font-semibold">Your Drive Files</h2>
              <button
                onClick={() => loadFiles()}
                disabled={loadingFiles}
                className="text-sm px-3 py-1.5 rounded-lg transition-colors"
                style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border)" }}
              >
                {loadingFiles ? "Loading..." : "Refresh"}
              </button>
            </div>

            {files.length === 0 && !loadingFiles ? (
              <div className="p-8 text-center" style={{ color: "var(--text-secondary)" }}>
                No files found. Files you create or share with your Google account will appear here.
              </div>
            ) : (
              <div>
                {files.map((file) => (
                  <div
                    key={file.id}
                    className="px-4 py-3 flex items-center justify-between hover:opacity-80 transition-opacity"
                    style={{ borderBottom: "1px solid var(--border)" }}
                  >
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      {file.iconLink && (
                        <img src={file.iconLink} alt="" className="w-5 h-5 flex-shrink-0" />
                      )}
                      <div className="min-w-0">
                        <div className="text-sm font-medium truncate">{file.name}</div>
                        <div className="text-xs" style={{ color: "var(--text-secondary)" }}>
                          {formatSize(file.size)} {file.size && file.modifiedTime && " · "} {formatDate(file.modifiedTime)}
                        </div>
                      </div>
                    </div>
                    <div className="flex-shrink-0 ml-4">
                      {importResults[file.id] ? (
                        <span className="text-xs px-2 py-1 rounded" style={{ backgroundColor: "#14532d", color: "#86efac" }}>
                          Imported ({importResults[file.id].chunk_count} chunks)
                        </span>
                      ) : (
                        <button
                          onClick={() => importFile(file.id)}
                          disabled={importing[file.id]}
                          className="text-sm px-3 py-1.5 rounded-lg font-medium transition-colors disabled:opacity-50"
                          style={{ backgroundColor: "var(--accent)", color: "white" }}
                        >
                          {importing[file.id] ? "Importing..." : "Import"}
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {nextPageToken && (
              <div className="p-4 text-center">
                <button
                  onClick={() => loadFiles(nextPageToken)}
                  disabled={loadingFiles}
                  className="text-sm px-4 py-2 rounded-lg transition-colors"
                  style={{ backgroundColor: "var(--bg-primary)", border: "1px solid var(--border)" }}
                >
                  {loadingFiles ? "Loading..." : "Load More"}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
