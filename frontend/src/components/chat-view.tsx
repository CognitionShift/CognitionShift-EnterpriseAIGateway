"use client";

import { useState, useRef, useEffect } from "react";
import { Message } from "@/lib/api";
import { MessageBubble } from "./message-bubble";
import { branding } from "@/lib/branding";

interface ChatViewProps {
  messages: Message[];
  streaming: boolean;
  streamContent: string;
  onSend: (content: string) => void;
}

export function ChatView({ messages, streaming, streamContent, onSend }: ChatViewProps) {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamContent]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 200) + "px";
    }
  }, [input]);

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim() || streaming) return;
    onSend(input.trim());
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-3xl mx-auto space-y-6">
          {messages.length === 0 && !streaming && (
            <div className="text-center py-16">
              {branding.hasOrgLogo ? (
                <img src={branding.orgLogoUrl} alt={branding.orgName} className="h-16 mx-auto mb-4" />
              ) : (
                <div className="text-5xl mb-4">{branding.platformIcon}</div>
              )}
              <h2 className="text-2xl font-semibold mb-3">{branding.welcomeTitle}</h2>
              <p className="text-base mb-8" style={{ color: "var(--text-secondary)" }}>
                {branding.welcomeSubtitle}
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-lg mx-auto">
                {[
                  { icon: "📝", text: "Draft a project proposal" },
                  { icon: "🔍", text: "Analyze a dataset" },
                  { icon: "💡", text: "Brainstorm solutions" },
                  { icon: "📊", text: "Create a report summary" },
                ].map((suggestion, i) => (
                  <button
                    key={i}
                    onClick={() => onSend(suggestion.text)}
                    className="flex items-center gap-2 px-4 py-3 rounded-xl text-sm text-left transition-colors hover:bg-[var(--bg-tertiary)]"
                    style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}
                  >
                    <span>{suggestion.icon}</span>
                    <span>{suggestion.text}</span>
                  </button>
                ))}
              </div>
              <p className="text-xs mt-6" style={{ color: "var(--text-secondary)" }}>
                Press <kbd className="px-1 py-0.5 rounded text-[10px]" style={{ backgroundColor: "var(--bg-tertiary)", border: "1px solid var(--border)" }}>Ctrl+N</kbd> for new chat • <kbd className="px-1 py-0.5 rounded text-[10px]" style={{ backgroundColor: "var(--bg-tertiary)", border: "1px solid var(--border)" }}>Ctrl+B</kbd> toggle sidebar
              </p>
            </div>
          )}

          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}

          {/* Streaming message */}
          {streaming && streamContent && (
            <MessageBubble
              message={{
                id: "streaming",
                role: "assistant",
                content: streamContent,
                model_id: null,
                input_tokens: null,
                output_tokens: null,
                cost_usd: null,
                created_at: new Date().toISOString(),
              }}
              isStreaming
            />
          )}

          {/* Typing indicator */}
          {streaming && !streamContent && (
            <div className="flex gap-3" role="status" aria-label="AI is thinking">
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center text-sm shrink-0"
                style={{ backgroundColor: "var(--accent)" }}
              >
                AI
              </div>
              <div
                className="flex items-center gap-1.5 px-4 py-3 rounded-2xl"
                style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}
              >
                <span className="w-2 h-2 rounded-full animate-bounce" style={{ backgroundColor: "var(--text-secondary)", animationDelay: "0ms" }} />
                <span className="w-2 h-2 rounded-full animate-bounce" style={{ backgroundColor: "var(--text-secondary)", animationDelay: "150ms" }} />
                <span className="w-2 h-2 rounded-full animate-bounce" style={{ backgroundColor: "var(--text-secondary)", animationDelay: "300ms" }} />
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input area */}
      <div className="shrink-0 px-4 pb-4 pt-2" style={{ borderTop: "1px solid var(--border)" }}>
        <form onSubmit={handleSubmit} className="max-w-3xl mx-auto">
          <div
            className="flex items-end gap-2 rounded-xl px-4 py-3"
            style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}
          >
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type a message... (Enter to send, Shift+Enter for new line)"
              rows={1}
              className="flex-1 resize-none text-sm bg-transparent outline-none"
              style={{ color: "var(--text-primary)", maxHeight: "200px" }}
              disabled={streaming}
              aria-label="Message input"
            />
            <button
              type="submit"
              disabled={!input.trim() || streaming}
              className="px-4 py-1.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-30"
              style={{ backgroundColor: "var(--accent)", color: "white" }}
              aria-label="Send message"
            >
              {streaming ? "..." : "Send"}
            </button>
          </div>
          <p className="text-xs mt-2 text-center" style={{ color: "var(--text-secondary)" }}>
            AI can make mistakes. Verify important information.
          </p>
        </form>
      </div>
    </div>
  );
}
