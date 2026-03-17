"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useAuth } from "@/lib/auth-context";
import {
  Conversation,
  Message,
  ModelInfo,
  listConversations,
  createConversation,
  deleteConversation,
  listMessages,
  listModels,
  sendMessageStream,
} from "@/lib/api";
import { Sidebar } from "@/components/sidebar";
import { ChatView } from "@/components/chat-view";
import { ModelSelector } from "@/components/model-selector";
import { SystemPromptModal } from "@/components/system-prompt-modal";
import { ThemeToggle } from "@/components/theme-toggle";
import { useKeyboardShortcuts } from "@/lib/use-keyboard-shortcuts";

export default function ChatPage() {
  const { user, loading, logout } = useAuth();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [streaming, setStreaming] = useState(false);
  const [streamContent, setStreamContent] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [showSystemPrompt, setShowSystemPrompt] = useState(false);

  // Redirect if not authenticated
  useEffect(() => {
    if (!loading && !user) {
      window.location.href = "/login";
    }
  }, [user, loading]);

  // Load conversations and models on mount
  useEffect(() => {
    if (user) {
      loadConversations();
      loadModels();
    }
  }, [user]);

  // Load messages when conversation changes
  useEffect(() => {
    if (activeConvId) {
      loadMessages(activeConvId);
    } else {
      setMessages([]);
    }
  }, [activeConvId]);

  const loadConversations = async () => {
    try {
      const convs = await listConversations();
      setConversations(convs);
    } catch (err) {
      console.error("Failed to load conversations:", err);
    }
  };

  const loadModels = async () => {
    try {
      const m = await listModels();
      setModels(m);
      if (m.length > 0 && !selectedModel) {
        setSelectedModel(m[0].id);
      }
    } catch (err) {
      console.error("Failed to load models:", err);
    }
  };

  const loadMessages = async (convId: string) => {
    try {
      const msgs = await listMessages(convId);
      setMessages(msgs);
    } catch (err) {
      console.error("Failed to load messages:", err);
    }
  };

  const handleNewChat = async () => {
    try {
      const conv = await createConversation(undefined, selectedModel, systemPrompt || undefined);
      setConversations((prev) => [conv, ...prev]);
      setActiveConvId(conv.id);
      setMessages([]);
    } catch (err) {
      console.error("Failed to create conversation:", err);
    }
  };

  // Keyboard shortcuts
  useKeyboardShortcuts({
    onNewChat: handleNewChat,
    onCloseModal: () => setShowSystemPrompt(false),
    onToggleSidebar: () => setSidebarOpen((v) => !v),
  });

  const handleDeleteConversation = async (id: string) => {
    try {
      await deleteConversation(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (activeConvId === id) {
        setActiveConvId(null);
        setMessages([]);
      }
    } catch (err) {
      console.error("Failed to delete conversation:", err);
    }
  };

  const handleSendMessage = useCallback(
    async (content: string) => {
      if (!content.trim() || streaming) return;

      let convId = activeConvId;

      // Create conversation if none active
      if (!convId) {
        try {
          const conv = await createConversation(undefined, selectedModel, systemPrompt || undefined);
          convId = conv.id;
          setConversations((prev) => [conv, ...prev]);
          setActiveConvId(conv.id);
        } catch (err) {
          console.error("Failed to create conversation:", err);
          return;
        }
      }

      // Add user message to UI immediately
      const userMsg: Message = {
        id: crypto.randomUUID(),
        role: "user",
        content,
        model_id: null,
        input_tokens: null,
        output_tokens: null,
        cost_usd: null,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setStreaming(true);
      setStreamContent("");

      let accumulated = "";

      await sendMessageStream(
        convId,
        content,
        selectedModel || undefined,
        // onToken
        (text) => {
          accumulated += text;
          setStreamContent(accumulated);
        },
        // onDone
        (usage) => {
          // Convert stream to a proper message
          const assistantMsg: Message = {
            id: crypto.randomUUID(),
            role: "assistant",
            content: accumulated,
            model_id: usage?.model || selectedModel,
            input_tokens: usage?.input_tokens || null,
            output_tokens: usage?.output_tokens || null,
            cost_usd: null,
            created_at: new Date().toISOString(),
          };
          setMessages((prev) => [...prev, assistantMsg]);
          setStreaming(false);
          setStreamContent("");
          // Refresh conversation list for updated titles
          loadConversations();
        },
        // onError
        (error) => {
          console.error("Stream error:", error);
          const errorMsg: Message = {
            id: crypto.randomUUID(),
            role: "assistant",
            content: `⚠️ Error: ${error}`,
            model_id: null,
            input_tokens: null,
            output_tokens: null,
            cost_usd: null,
            created_at: new Date().toISOString(),
          };
          setMessages((prev) => [...prev, errorMsg]);
          setStreaming(false);
          setStreamContent("");
        },
      );
    },
    [activeConvId, selectedModel, streaming],
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-pulse" style={{ color: "var(--text-secondary)" }}>
          Loading...
        </div>
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <Sidebar
        conversations={conversations}
        activeConvId={activeConvId}
        onSelect={setActiveConvId}
        onNewChat={handleNewChat}
        onDelete={handleDeleteConversation}
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
        user={user}
        onLogout={logout}
      />

      {/* Main content */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header
          className="flex items-center justify-between px-4 py-3 shrink-0"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <div className="flex items-center gap-3">
            {!sidebarOpen && (
              <button
                onClick={() => setSidebarOpen(true)}
                className="p-1.5 rounded-lg hover:bg-[var(--bg-tertiary)]"
                aria-label="Open sidebar"
              >
                ☰
              </button>
            )}
            <h2 className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
              {conversations.find((c) => c.id === activeConvId)?.title || "New Chat"}
            </h2>
          </div>

          <div className="flex items-center gap-2">
            <ThemeToggle />
            <a
              href="/settings"
              className="px-2 py-1 rounded-lg text-xs transition-colors"
              style={{ backgroundColor: "var(--bg-tertiary)", border: "1px solid var(--border)", color: "var(--text-secondary)" }}
              aria-label="Settings"
            >
              ⚙️
            </a>
            <button
              onClick={() => setShowSystemPrompt(true)}
              className="px-2 py-1 rounded-lg text-xs transition-colors"
              style={{
                backgroundColor: systemPrompt ? "var(--accent)" : "var(--bg-tertiary)",
                color: systemPrompt ? "white" : "var(--text-secondary)",
                border: "1px solid var(--border)",
              }}
              aria-label="Set system prompt"
              title={systemPrompt ? "System prompt active" : "Set system prompt"}
            >
              🎯 System
            </button>
            <ModelSelector
              models={models}
              selected={selectedModel}
              onChange={setSelectedModel}
            />
          </div>
        </header>

        {/* Chat area */}
        <ChatView
          messages={messages}
          streaming={streaming}
          streamContent={streamContent}
          onSend={handleSendMessage}
        />
      </main>

      {/* System Prompt Modal */}
      <SystemPromptModal
        isOpen={showSystemPrompt}
        initialPrompt={systemPrompt}
        onSave={setSystemPrompt}
        onClose={() => setShowSystemPrompt(false)}
      />
    </div>
  );
}
