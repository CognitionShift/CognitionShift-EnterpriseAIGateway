"use client";

import { useEffect, useRef } from "react";
import { Conversation } from "@/lib/api";
import { ConversationListSkeleton } from "@/components/skeleton";

interface SidebarProps {
  conversations: Conversation[];
  activeConvId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onDelete: (id: string) => void;
  isOpen: boolean;
  onToggle: () => void;
  user: { name: string; email: string; role: string };
  onLogout: () => void;
  loading?: boolean;
}

export function Sidebar({
  conversations,
  activeConvId,
  onSelect,
  onNewChat,
  onDelete,
  isOpen,
  onToggle,
  user,
  onLogout,
  loading = false,
}: SidebarProps) {
  const sidebarRef = useRef<HTMLElement>(null);

  // Close sidebar on mobile when clicking outside
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: MouseEvent) => {
      if (window.innerWidth >= 768) return; // Only on mobile
      if (sidebarRef.current && !sidebarRef.current.contains(e.target as Node)) {
        onToggle();
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [isOpen, onToggle]);

  // Focus management: when sidebar opens, focus the new chat button
  useEffect(() => {
    if (isOpen && sidebarRef.current) {
      const firstBtn = sidebarRef.current.querySelector("button");
      firstBtn?.focus();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSelect = (id: string) => {
    onSelect(id);
    // Close on mobile after selection
    if (window.innerWidth < 768) onToggle();
  };

  return (
    <>
      {/* Mobile overlay backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-30 md:hidden"
        onClick={onToggle}
        aria-hidden="true"
      />
      <aside
        ref={sidebarRef}
        className="w-72 flex flex-col shrink-0 h-full fixed md:relative z-40 md:z-auto"
        style={{ backgroundColor: "var(--bg-secondary)", borderRight: "1px solid var(--border)" }}
        role="navigation"
        aria-label="Conversation list"
      >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: "1px solid var(--border)" }}>
        <span className="text-sm font-bold">⚡ CognitionShift</span>
        <button
          onClick={onToggle}
          className="p-1 rounded hover:bg-[var(--bg-tertiary)] text-sm"
          aria-label="Close sidebar"
        >
          ✕
        </button>
      </div>

      {/* New Chat button */}
      <div className="px-3 py-3">
        <button
          onClick={onNewChat}
          className="w-full py-2 px-3 rounded-lg text-sm font-medium transition-colors"
          style={{ backgroundColor: "var(--accent)", color: "white" }}
        >
          + New Chat
        </button>
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto px-2">
        {loading ? (
          <ConversationListSkeleton />
        ) : conversations.length === 0 ? (
          <p className="text-center text-sm py-8" style={{ color: "var(--text-secondary)" }}>
            No conversations yet
          </p>
        ) : null}
        {!loading && conversations.map((conv) => (
          <div
            key={conv.id}
            className="group flex items-center gap-2 rounded-lg px-3 py-2 mb-0.5 cursor-pointer transition-colors"
            style={{
              backgroundColor: conv.id === activeConvId ? "var(--bg-tertiary)" : "transparent",
            }}
            onClick={() => handleSelect(conv.id)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === "Enter" && handleSelect(conv.id)}
            aria-current={conv.id === activeConvId ? "page" : undefined}
          >
            <span className="flex-1 text-sm truncate">
              {conv.title || "Untitled"}
            </span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete(conv.id);
              }}
              className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-[var(--bg-primary)] text-xs"
              style={{ color: "var(--text-secondary)" }}
              aria-label={`Delete conversation ${conv.title || "Untitled"}`}
            >
              🗑
            </button>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div style={{ borderTop: "1px solid var(--border)" }}>
        {/* Navigation links */}
        <a
          href="/agents"
          className="flex items-center gap-2 px-4 py-2 text-sm transition-colors hover:bg-[var(--bg-tertiary)]"
          style={{ color: "var(--text-secondary)" }}
        >
          🤖 AI Agents
        </a>
        <a
          href="/files"
          className="flex items-center gap-2 px-4 py-2 text-sm transition-colors hover:bg-[var(--bg-tertiary)]"
          style={{ color: "var(--text-secondary)" }}
        >
          📁 Files & Knowledge
        </a>
        <a
          href="/dashboard"
          className="flex items-center gap-2 px-4 py-2 text-sm transition-colors hover:bg-[var(--bg-tertiary)]"
          style={{ color: "var(--text-secondary)" }}
        >
          📊 Usage Dashboard
        </a>
        {user.role === "admin" && (
          <a
            href="/admin"
            className="flex items-center gap-2 px-4 py-2 text-sm transition-colors hover:bg-[var(--bg-tertiary)]"
            style={{ color: "var(--text-secondary)" }}
          >
            ⚙️ Admin Console
          </a>
        )}
        <a
          href="/settings"
          className="flex items-center gap-2 px-4 py-2 text-sm transition-colors hover:bg-[var(--bg-tertiary)]"
          style={{ color: "var(--text-secondary)" }}
        >
          🔧 Settings
        </a>

        {/* User info */}
        <div className="px-4 py-3 flex items-center justify-between">
          <div className="min-w-0">
            <p className="text-sm font-medium truncate">{user.name}</p>
            <p className="text-xs truncate" style={{ color: "var(--text-secondary)" }}>
              {user.email}
            </p>
          </div>
          <button
            onClick={onLogout}
            className="text-xs px-2 py-1 rounded hover:bg-[var(--bg-tertiary)]"
            style={{ color: "var(--text-secondary)" }}
          >
            Logout
          </button>
        </div>
      </div>
    </aside>
    </>
  );
}
