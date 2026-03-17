"use client";

import { useEffect } from "react";

interface ShortcutConfig {
  onNewChat?: () => void;
  onSearch?: () => void;
  onCloseModal?: () => void;
  onToggleSidebar?: () => void;
}

/**
 * Global keyboard shortcuts:
 * - Ctrl/Cmd+N: New chat
 * - Ctrl/Cmd+K: Search
 * - Escape: Close modals
 * - Ctrl/Cmd+B: Toggle sidebar
 */
export function useKeyboardShortcuts(config: ShortcutConfig) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;

      // Don't intercept when typing in inputs (except for Escape)
      const target = e.target as HTMLElement;
      const isInput = target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable;

      if (e.key === "Escape" && config.onCloseModal) {
        config.onCloseModal();
        return;
      }

      if (isInput && e.key !== "Escape") return;

      if (mod && e.key === "n") {
        e.preventDefault();
        config.onNewChat?.();
      } else if (mod && e.key === "k") {
        e.preventDefault();
        config.onSearch?.();
      } else if (mod && e.key === "b") {
        e.preventDefault();
        config.onToggleSidebar?.();
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [config]);
}
