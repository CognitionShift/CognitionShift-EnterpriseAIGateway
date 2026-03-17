"use client";

import { Message } from "@/lib/api";

interface MessageBubbleProps {
  message: Message;
  isStreaming?: boolean;
}

export function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex gap-3 ${isUser ? "justify-end" : ""}`}>
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
          className="rounded-2xl px-4 py-2.5 text-sm leading-relaxed"
          style={{
            backgroundColor: isUser ? "var(--accent)" : "var(--bg-secondary)",
            color: isUser ? "white" : "var(--text-primary)",
            border: isUser ? "none" : "1px solid var(--border)",
          }}
        >
          {/* Render message content with basic formatting */}
          <div className="whitespace-pre-wrap break-words">
            {message.content}
            {isStreaming && (
              <span className="animate-pulse ml-0.5">▊</span>
            )}
          </div>
        </div>

        {/* Metadata row for assistant messages */}
        {!isUser && !isStreaming && (message.model_id || message.input_tokens) && (
          <div className="flex gap-3 mt-1 px-1 text-xs" style={{ color: "var(--text-secondary)" }}>
            {message.model_id && <span>{message.model_id}</span>}
            {message.input_tokens != null && message.output_tokens != null && (
              <span>
                {message.input_tokens + message.output_tokens} tokens
              </span>
            )}
            {message.cost_usd != null && message.cost_usd > 0 && (
              <span>${message.cost_usd.toFixed(4)}</span>
            )}
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
