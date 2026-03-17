"use client";

import { useState } from "react";
import { Message } from "@/lib/api";

interface MessageBubbleProps {
  message: Message;
  isStreaming?: boolean;
}

/**
 * Simple markdown-like rendering:
 * - ```code blocks```
 * - `inline code`
 * - **bold**
 * - *italic*
 * - Preserves newlines
 */
function renderContent(text: string): React.ReactNode[] {
  const segments: React.ReactNode[] = [];
  const codeBlockRegex = /```(\w*)\n?([\s\S]*?)```/g;
  let lastIndex = 0;
  let match;

  while ((match = codeBlockRegex.exec(text)) !== null) {
    // Text before code block
    if (match.index > lastIndex) {
      segments.push(
        <span key={`text-${lastIndex}`} className="whitespace-pre-wrap">
          {renderInline(text.slice(lastIndex, match.index))}
        </span>
      );
    }

    // Code block
    const lang = match[1] || "";
    const code = match[2].trim();
    segments.push(
      <div key={`code-${match.index}`} className="my-2">
        {lang && (
          <div
            className="text-xs px-3 py-1 rounded-t-lg"
            style={{ backgroundColor: "#1a1a2e", color: "var(--text-secondary)" }}
          >
            {lang}
          </div>
        )}
        <pre
          className="px-3 py-2 rounded-lg text-sm overflow-x-auto"
          style={{
            backgroundColor: "#1a1a2e",
            borderRadius: lang ? "0 0 0.5rem 0.5rem" : "0.5rem",
          }}
        >
          <code>{code}</code>
        </pre>
      </div>
    );

    lastIndex = match.index + match[0].length;
  }

  // Remaining text
  if (lastIndex < text.length) {
    segments.push(
      <span key={`text-${lastIndex}`} className="whitespace-pre-wrap">
        {renderInline(text.slice(lastIndex))}
      </span>
    );
  }

  return segments;
}

function renderInline(text: string): React.ReactNode[] {
  // Process inline code, bold, italic
  const parts: React.ReactNode[] = [];
  const regex = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g;
  let lastIdx = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIdx) {
      parts.push(text.slice(lastIdx, match.index));
    }

    const m = match[0];
    if (m.startsWith("```")) {
      // Already handled
      parts.push(m);
    } else if (m.startsWith("`")) {
      parts.push(
        <code
          key={`ic-${match.index}`}
          className="px-1 py-0.5 rounded text-sm"
          style={{ backgroundColor: "rgba(255,255,255,0.1)" }}
        >
          {m.slice(1, -1)}
        </code>
      );
    } else if (m.startsWith("**")) {
      parts.push(<strong key={`b-${match.index}`}>{m.slice(2, -2)}</strong>);
    } else if (m.startsWith("*")) {
      parts.push(<em key={`i-${match.index}`}>{m.slice(1, -1)}</em>);
    }

    lastIdx = match.index + m.length;
  }

  if (lastIdx < text.length) {
    parts.push(text.slice(lastIdx));
  }

  return parts;
}

export function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={`flex gap-3 ${isUser ? "justify-end" : ""} group`}>
      {!isUser && (
        <div
          className="w-8 h-8 rounded-full flex items-center justify-center text-sm shrink-0 mt-1"
          style={{ backgroundColor: "var(--accent)" }}
          aria-hidden="true"
        >
          AI
        </div>
      )}

      <div className={`max-w-[80%] ${isUser ? "order-first" : ""}`}>
        <div
          className="rounded-2xl px-4 py-2.5 text-sm leading-relaxed relative"
          style={{
            backgroundColor: isUser ? "var(--accent)" : "var(--bg-secondary)",
            color: isUser ? "white" : "var(--text-primary)",
            border: isUser ? "none" : "1px solid var(--border)",
          }}
        >
          <div className="break-words">
            {isUser ? (
              <span className="whitespace-pre-wrap">{message.content}</span>
            ) : (
              renderContent(message.content)
            )}
            {isStreaming && <span className="animate-pulse ml-0.5">▊</span>}
          </div>
        </div>

        {/* Actions + metadata row */}
        {!isUser && !isStreaming && (
          <div className="flex items-center gap-3 mt-1 px-1 text-xs" style={{ color: "var(--text-secondary)" }}>
            {message.model_id && <span>{message.model_id}</span>}
            {message.input_tokens != null && message.output_tokens != null && (
              <span>{message.input_tokens + message.output_tokens} tokens</span>
            )}
            {message.cost_usd != null && message.cost_usd > 0 && (
              <span>${message.cost_usd.toFixed(4)}</span>
            )}
            <button
              onClick={handleCopy}
              className="opacity-0 group-hover:opacity-100 transition-opacity"
              aria-label="Copy message"
            >
              {copied ? "✓ Copied" : "📋 Copy"}
            </button>
          </div>
        )}
      </div>

      {isUser && (
        <div
          className="w-8 h-8 rounded-full flex items-center justify-center text-sm shrink-0 mt-1"
          style={{ backgroundColor: "var(--bg-tertiary)" }}
          aria-hidden="true"
        >
          You
        </div>
      )}
    </div>
  );
}
