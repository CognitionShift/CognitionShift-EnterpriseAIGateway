"use client";

export function SkeletonLine({ width = "100%" }: { width?: string }) {
  return (
    <div
      className="h-4 rounded animate-pulse"
      style={{ width, backgroundColor: "var(--bg-tertiary, #2a2a3a)" }}
    />
  );
}

export function SkeletonConversation() {
  return (
    <div className="px-3 py-2 flex flex-col gap-2">
      <SkeletonLine width="80%" />
      <SkeletonLine width="50%" />
    </div>
  );
}

export function ConversationListSkeleton({ count = 5 }: { count?: number }) {
  return (
    <div className="flex flex-col gap-1 px-2">
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonConversation key={i} />
      ))}
    </div>
  );
}

export function MessageSkeleton() {
  return (
    <div className="flex gap-3 animate-pulse">
      <div className="w-8 h-8 rounded-full" style={{ backgroundColor: "var(--bg-tertiary)" }} />
      <div className="flex-1 flex flex-col gap-2 py-1">
        <SkeletonLine width="90%" />
        <SkeletonLine width="70%" />
        <SkeletonLine width="40%" />
      </div>
    </div>
  );
}

export function MessageListSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="max-w-3xl mx-auto space-y-6 py-6 px-4">
      {Array.from({ length: count }).map((_, i) => (
        <MessageSkeleton key={i} />
      ))}
    </div>
  );
}

export function TableSkeleton({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="rounded-xl overflow-hidden" style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
      <div className="animate-pulse">
        {/* Header */}
        <div className="flex gap-4 px-4 py-3" style={{ borderBottom: "1px solid var(--border)" }}>
          {Array.from({ length: cols }).map((_, i) => (
            <SkeletonLine key={i} width={`${100 / cols}%`} />
          ))}
        </div>
        {/* Rows */}
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="flex gap-4 px-4 py-3" style={{ borderBottom: "1px solid var(--border)" }}>
            {Array.from({ length: cols }).map((_, j) => (
              <SkeletonLine key={j} width={`${100 / cols}%`} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
