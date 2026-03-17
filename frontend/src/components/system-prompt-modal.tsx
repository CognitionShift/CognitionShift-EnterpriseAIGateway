"use client";

import { useState } from "react";

interface SystemPromptModalProps {
  isOpen: boolean;
  initialPrompt: string;
  onSave: (prompt: string) => void;
  onClose: () => void;
}

export function SystemPromptModal({ isOpen, initialPrompt, onSave, onClose }: SystemPromptModalProps) {
  const [prompt, setPrompt] = useState(initialPrompt);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 flex items-center justify-center z-50"
      style={{ backgroundColor: "rgba(0,0,0,0.6)" }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
      role="dialog"
      aria-modal="true"
      aria-label="System Prompt"
    >
      <div
        className="w-full max-w-lg rounded-xl p-6"
        style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}
      >
        <h3 className="text-lg font-semibold mb-4">System Prompt</h3>
        <p className="text-sm mb-3" style={{ color: "var(--text-secondary)" }}>
          Set instructions for the AI. This prompt is sent with every message in the conversation.
        </p>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={6}
          className="w-full px-3 py-2 rounded-lg text-sm resize-none"
          style={{
            backgroundColor: "var(--bg-primary)",
            border: "1px solid var(--border)",
            color: "var(--text-primary)",
          }}
          placeholder="e.g., You are a helpful assistant specializing in enterprise software..."
          aria-label="System prompt text"
        />
        <div className="flex justify-end gap-3 mt-4">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm"
            style={{ color: "var(--text-secondary)" }}
          >
            Cancel
          </button>
          <button
            onClick={() => { onSave(prompt); onClose(); }}
            className="px-4 py-2 rounded-lg text-sm font-medium"
            style={{ backgroundColor: "var(--accent)", color: "white" }}
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
