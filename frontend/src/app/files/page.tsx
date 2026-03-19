"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useAuth } from "@/lib/auth-context";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";
const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";
const GOOGLE_API_KEY = process.env.NEXT_PUBLIC_GOOGLE_API_KEY || "";

interface FileItem {
  id: string;
  name: string;
  mime_type: string;
  size_bytes: number;
  status: string;
  chunk_count: number;
  created_at: string;
}

// Google Workspace MIME types that need export (can't be downloaded directly)
const EXPORT_MIME_MAP: Record<string, { mime: string; ext: string }> = {
  "application/vnd.google-apps.document": { mime: "application/pdf", ext: ".pdf" },
  "application/vnd.google-apps.spreadsheet": { mime: "text/csv", ext: ".csv" },
  "application/vnd.google-apps.presentation": { mime: "application/pdf", ext: ".pdf" },
};

/**
 * Download a file from Google Drive using the user's OAuth token.
 * Handles both regular files (binary download) and Google Workspace
 * native files (export as PDF/CSV).
 */
async function downloadDriveFile(
  fileId: string,
  mimeType: string,
  fileName: string,
  oauthToken: string,
): Promise<{ blob: Blob; finalName: string; finalMime: string }> {
  const exportInfo = EXPORT_MIME_MAP[mimeType];

  let url: string;
  let finalMime: string;
  let finalName: string;

  if (exportInfo) {
    // Google Workspace file: export to a real format
    url = `https://www.googleapis.com/drive/v3/files/${fileId}/export?mimeType=${encodeURIComponent(exportInfo.mime)}`;
    finalMime = exportInfo.mime;
    finalName = fileName.endsWith(exportInfo.ext) ? fileName : `${fileName}${exportInfo.ext}`;
  } else {
    // Regular file: direct download
    url = `https://www.googleapis.com/drive/v3/files/${fileId}?alt=media`;
    finalMime = mimeType;
    finalName = fileName;
  }

  const resp = await fetch(url, {
    headers: { Authorization: `Bearer ${oauthToken}` },
  });

  if (!resp.ok) {
    const err = await resp.text().catch(() => "Unknown error");
    throw new Error(`Drive download failed (${resp.status}): ${err}`);
  }

  const blob = await resp.blob();
  return { blob, finalName, finalMime };
}

export default function FilesPage() {
  const { user, loading } = useAuth();
  const [files, setFiles] = useState<FileItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const [driveImporting, setDriveImporting] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [pickerReady, setPickerReady] = useState(false);
  const [gapiLoaded, setGapiLoaded] = useState(false);
  const [gisLoaded, setGisLoaded] = useState(false);
  const [importStatus, setImportStatus] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const oauthTokenRef = useRef<string>("");
  const tokenClientRef = useRef<any>(null);
  const pickerCallbackRef = useRef<((files: any[]) => void) | null>(null);

  useEffect(() => {
    if (!loading && !user) window.location.href = "/login";
  }, [user, loading]);

  const getToken = () => localStorage.getItem("access_token");

  useEffect(() => {
    if (user) fetchFiles();
  }, [user]);

  // Load Google API scripts
  useEffect(() => {
    if (!GOOGLE_CLIENT_ID || !GOOGLE_API_KEY) return;

    // Load gapi (for Picker)
    const gapiScript = document.createElement("script");
    gapiScript.src = "https://apis.google.com/js/api.js";
    gapiScript.async = true;
    gapiScript.defer = true;
    gapiScript.onload = () => {
      window.gapi.load("picker", () => {
        setGapiLoaded(true);
      });
    };
    document.head.appendChild(gapiScript);

    // Load GIS (for OAuth token)
    const gisScript = document.createElement("script");
    gisScript.src = "https://accounts.google.com/gsi/client";
    gisScript.async = true;
    gisScript.defer = true;
    gisScript.onload = () => {
      setGisLoaded(true);
    };
    document.head.appendChild(gisScript);

    return () => {
      document.head.removeChild(gapiScript);
      document.head.removeChild(gisScript);
    };
  }, []);

  // Initialize token client when GIS is loaded
  useEffect(() => {
    if (!gisLoaded || !GOOGLE_CLIENT_ID) return;

    tokenClientRef.current = window.google.accounts.oauth2.initTokenClient({
      client_id: GOOGLE_CLIENT_ID,
      scope: "https://www.googleapis.com/auth/drive.file",
      callback: (response: any) => {
        if (response.error) {
          console.error("OAuth error:", response);
          setImportStatus("");
          return;
        }
        oauthTokenRef.current = response.access_token;
        // Now open the picker
        openPicker(response.access_token);
      },
    });
  }, [gisLoaded]);

  // Mark picker as ready when both scripts are loaded
  useEffect(() => {
    if (gapiLoaded && gisLoaded) setPickerReady(true);
  }, [gapiLoaded, gisLoaded]);

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
    await uploadFile(file);
  };

  const uploadFile = async (file: File | Blob, fileName?: string) => {
    setUploading(true);
    const formData = new FormData();
    formData.append("file", file, fileName || (file instanceof File ? file.name : "file"));

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
      const r = await fetch(
        `${API_URL}/api/v1/search?q=${encodeURIComponent(searchQuery)}`,
        { headers: { Authorization: `Bearer ${getToken()}` } },
      );
      if (r.ok) setSearchResults((await r.json()).data.results);
    } catch {}
  };

  const openPicker = useCallback(
    (accessToken: string) => {
      if (!window.google?.picker) return;

      const docsView = new window.google.picker.DocsView()
        .setIncludeFolders(true)
        .setSelectFolderEnabled(false);

      const picker = new window.google.picker.PickerBuilder()
        .enableFeature(window.google.picker.Feature.MULTISELECT_ENABLED)
        .addView(docsView)
        .addView(new window.google.picker.DocsView().setMimeTypes("application/pdf"))
        .setOAuthToken(accessToken)
        .setDeveloperKey(GOOGLE_API_KEY)
        .setCallback(handlePickerCallback)
        .setTitle("Select files to import")
        .build();

      picker.setVisible(true);
    },
    [],
  );

  const handlePickerCallback = useCallback(
    async (data: any) => {
      if (data.action !== "picked" || !data.docs?.length) {
        if (data.action === "cancel") setImportStatus("");
        return;
      }

      setDriveImporting(true);
      const token = oauthTokenRef.current;
      const totalFiles = data.docs.length;
      let imported = 0;
      let failed = 0;

      for (const doc of data.docs) {
        setImportStatus(`Importing ${imported + 1}/${totalFiles}: ${doc.name}...`);
        try {
          const { blob, finalName, finalMime } = await downloadDriveFile(
            doc.id,
            doc.mimeType,
            doc.name,
            token,
          );

          // Upload to our platform via the existing file endpoint
          const file = new File([blob], finalName, { type: finalMime });
          const formData = new FormData();
          formData.append("file", file);

          const r = await fetch(`${API_URL}/api/v1/files`, {
            method: "POST",
            headers: { Authorization: `Bearer ${getToken()}` },
            body: formData,
          });

          if (r.ok) {
            imported++;
          } else {
            failed++;
            const err = await r.json().catch(() => ({}));
            console.error(`Failed to import ${doc.name}:`, err.detail);
          }
        } catch (err) {
          failed++;
          console.error(`Failed to import ${doc.name}:`, err);
        }
      }

      setDriveImporting(false);
      if (failed > 0) {
        setImportStatus(`Done: ${imported} imported, ${failed} failed`);
      } else {
        setImportStatus(`${imported} file${imported !== 1 ? "s" : ""} imported from Drive`);
      }
      setTimeout(() => setImportStatus(""), 5000);
      fetchFiles();
    },
    [],
  );

  const handleDriveImport = () => {
    if (!pickerReady) return;

    // If we already have a token, open picker directly
    if (oauthTokenRef.current) {
      openPicker(oauthTokenRef.current);
      return;
    }

    // Request OAuth token (opens Google consent screen)
    setImportStatus("Connecting to Google Drive...");
    tokenClientRef.current?.requestAccessToken({ prompt: "consent" });
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  if (loading || !user) return null;

  const pickerAvailable = GOOGLE_CLIENT_ID && GOOGLE_API_KEY;

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
          <a
            href="/chat"
            className="px-4 py-2 rounded-lg text-sm"
            style={{
              backgroundColor: "var(--bg-secondary)",
              border: "1px solid var(--border)",
              color: "var(--text-secondary)",
            }}
          >
            ← Back to Chat
          </a>
        </div>

        {/* Upload + Search */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
          {/* Upload */}
          <div
            className="rounded-xl p-6"
            style={{
              backgroundColor: "var(--bg-secondary)",
              border: "1px solid var(--border)",
            }}
          >
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
              {uploading
                ? "⏳ Processing..."
                : "📎 Click to upload (TXT, CSV, PDF, DOCX, MD)"}
            </label>

            {/* Google Drive import */}
            {pickerAvailable && (
              <button
                onClick={handleDriveImport}
                disabled={!pickerReady || driveImporting}
                className="w-full mt-3 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                style={{
                  backgroundColor: "var(--bg-primary)",
                  border: "1px solid var(--border)",
                  color: "var(--text-primary)",
                }}
              >
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 87.3 78"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <path
                    d="m6.6 66.85 3.85 6.65c.8 1.4 1.95 2.5 3.3 3.3l13.75-23.8H0c0 1.55.4 3.1 1.2 4.5z"
                    fill="#0066DA"
                  />
                  <path
                    d="m43.65 25-13.75-23.8c-1.35.8-2.5 1.9-3.3 3.3l-25.4 44a9.06 9.06 0 0 0-1.2 4.5h27.5z"
                    fill="#00AC47"
                  />
                  <path
                    d="M73.55 76.8c1.35-.8 2.5-1.9 3.3-3.3l1.6-2.75 7.65-13.25c.8-1.4 1.2-2.95 1.2-4.5H59.8l5.85 9.75z"
                    fill="#EA4335"
                  />
                  <path
                    d="M43.65 25 57.4 1.2C56.05.4 54.5 0 52.85 0H34.45c-1.65 0-3.2.45-4.55 1.2z"
                    fill="#00832D"
                  />
                  <path
                    d="M59.8 53H27.5l-13.75 23.8c1.35.8 2.9 1.2 4.55 1.2h50.7c1.65 0 3.2-.45 4.55-1.2z"
                    fill="#2684FC"
                  />
                  <path
                    d="M73.4 26.5 60.65 4.5c-.8-1.4-1.95-2.5-3.3-3.3L43.6 25l16.15 28h27.5c0-1.55-.4-3.1-1.2-4.5z"
                    fill="#FFBA00"
                  />
                </svg>
                {driveImporting ? "Importing..." : "Import from Google Drive"}
              </button>
            )}

            {importStatus && (
              <p className="text-xs mt-2 text-center" style={{ color: "var(--text-secondary)" }}>
                {importStatus}
              </p>
            )}
          </div>

          {/* Search */}
          <div
            className="rounded-xl p-6"
            style={{
              backgroundColor: "var(--bg-secondary)",
              border: "1px solid var(--border)",
            }}
          >
            <h2 className="font-semibold mb-3">Search Documents</h2>
            <div className="flex gap-2">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                placeholder="Search across all files..."
                className="flex-1 px-3 py-2 rounded-lg text-sm"
                style={{
                  backgroundColor: "var(--bg-primary)",
                  border: "1px solid var(--border)",
                  color: "var(--text-primary)",
                }}
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
                  <div
                    key={i}
                    className="text-xs p-2 rounded"
                    style={{ backgroundColor: "var(--bg-primary)" }}
                  >
                    <span className="text-green-400">
                      Score: {r.score.toFixed(2)}
                    </span>
                    <p className="mt-1" style={{ color: "var(--text-secondary)" }}>
                      {r.content}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* File list */}
        <div
          className="rounded-xl overflow-hidden"
          style={{
            backgroundColor: "var(--bg-secondary)",
            border: "1px solid var(--border)",
          }}
        >
          <div
            className="px-4 py-3"
            style={{ borderBottom: "1px solid var(--border)" }}
          >
            <h2 className="font-semibold">Your Files ({files.length})</h2>
          </div>
          {files.length === 0 ? (
            <p
              className="text-center py-12"
              style={{ color: "var(--text-secondary)" }}
            >
              No files yet. Upload a document to get started.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr
                  style={{
                    borderBottom: "1px solid var(--border)",
                    color: "var(--text-secondary)",
                  }}
                >
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
                  <tr
                    key={f.id}
                    style={{ borderBottom: "1px solid var(--border)" }}
                  >
                    <td className="px-4 py-2 font-medium">{f.name}</td>
                    <td
                      className="px-4 py-2"
                      style={{ color: "var(--text-secondary)" }}
                    >
                      {f.mime_type.split("/")[1]}
                    </td>
                    <td className="px-4 py-2 text-right">
                      {formatSize(f.size_bytes)}
                    </td>
                    <td className="px-4 py-2 text-right">{f.chunk_count}</td>
                    <td className="px-4 py-2">
                      <span
                        className={`text-xs px-2 py-0.5 rounded ${
                          f.status === "ready"
                            ? "bg-green-900 text-green-300"
                            : "bg-yellow-900 text-yellow-300"
                        }`}
                      >
                        {f.status}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <button
                        onClick={() => handleDelete(f.id)}
                        className="text-xs"
                        style={{ color: "var(--error)" }}
                      >
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

// Type declarations for Google APIs loaded via script tags
declare global {
  interface Window {
    gapi: any;
    google: any;
  }
}
