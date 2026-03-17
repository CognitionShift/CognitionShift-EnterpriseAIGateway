/**
 * API client for CognitionShift Enterprise AI Gateway.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

interface UserResponse {
  id: string;
  email: string;
  name: string;
  role: string;
  org_id: string;
  org_name: string | null;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string | null;
  model_id: string | null;
  pinned: boolean;
  archived: boolean;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_preview: string | null;
}

export interface Message {
  id: string;
  role: string;
  content: string;
  model_id: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  created_at: string;
}

export interface ModelInfo {
  id: string;
  display_name: string;
  provider: string;
  supports_streaming: boolean;
  max_context_tokens: number | null;
  input_cost_per_1k: number | null;
  output_cost_per_1k: number | null;
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}

function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("refresh_token");
}

export function saveTokens(tokens: TokenResponse) {
  localStorage.setItem("access_token", tokens.access_token);
  localStorage.setItem("refresh_token", tokens.refresh_token);
}

export function clearTokens() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
}

async function fetchWithAuth(url: string, options: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  if (!headers["Content-Type"] && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  let response = await fetch(`${API_URL}${url}`, { ...options, headers });

  // If 401, try refreshing
  if (response.status === 401) {
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      const refreshResp = await fetch(`${API_URL}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (refreshResp.ok) {
        const tokens: TokenResponse = await refreshResp.json();
        saveTokens(tokens);
        headers["Authorization"] = `Bearer ${tokens.access_token}`;
        response = await fetch(`${API_URL}${url}`, { ...options, headers });
      } else {
        clearTokens();
        window.location.href = "/login";
        throw new Error("Session expired");
      }
    }
  }

  return response;
}

// Auth
export async function register(email: string, password: string, name: string): Promise<TokenResponse> {
  const resp = await fetch(`${API_URL}/api/v1/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, name }),
  });
  if (!resp.ok) {
    const err = await resp.json();
    throw new Error(err.detail || "Registration failed");
  }
  const tokens = await resp.json();
  saveTokens(tokens);
  return tokens;
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const resp = await fetch(`${API_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!resp.ok) {
    const err = await resp.json();
    throw new Error(err.detail || "Login failed");
  }
  const tokens = await resp.json();
  saveTokens(tokens);
  return tokens;
}

export async function getMe(): Promise<UserResponse> {
  const resp = await fetchWithAuth("/api/v1/auth/me");
  if (!resp.ok) throw new Error("Failed to fetch user");
  return resp.json();
}

// Models
export async function listModels(): Promise<ModelInfo[]> {
  const resp = await fetchWithAuth("/api/v1/models");
  if (!resp.ok) throw new Error("Failed to fetch models");
  return resp.json();
}

// Conversations
export async function listConversations(): Promise<Conversation[]> {
  const resp = await fetchWithAuth("/api/v1/conversations");
  if (!resp.ok) throw new Error("Failed to fetch conversations");
  return resp.json();
}

export async function createConversation(title?: string, modelId?: string): Promise<Conversation> {
  const resp = await fetchWithAuth("/api/v1/conversations", {
    method: "POST",
    body: JSON.stringify({ title, model_id: modelId }),
  });
  if (!resp.ok) throw new Error("Failed to create conversation");
  return resp.json();
}

export async function deleteConversation(id: string): Promise<void> {
  await fetchWithAuth(`/api/v1/conversations/${id}`, { method: "DELETE" });
}

// Messages
export async function listMessages(conversationId: string): Promise<Message[]> {
  const resp = await fetchWithAuth(`/api/v1/conversations/${conversationId}/messages`);
  if (!resp.ok) throw new Error("Failed to fetch messages");
  return resp.json();
}

// Streaming chat
export async function sendMessageStream(
  conversationId: string,
  content: string,
  model?: string,
  onToken: (text: string) => void = () => {},
  onDone: (usage: any) => void = () => {},
  onError: (error: string) => void = () => {},
): Promise<void> {
  const token = getToken();
  const resp = await fetch(`${API_URL}/api/v1/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`,
    },
    body: JSON.stringify({ content, model, stream: true }),
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: "Unknown error" }));
    onError(err.detail || `HTTP ${resp.status}`);
    return;
  }

  const reader = resp.body?.getReader();
  if (!reader) {
    onError("No response body");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = line.slice(6).trim();
      if (!data) continue;

      try {
        const event = JSON.parse(data);
        if (event.type === "token") {
          onToken(event.content);
        } else if (event.type === "done") {
          onDone(event.usage);
        } else if (event.type === "error") {
          onError(event.message);
        }
      } catch {
        // Skip malformed events
      }
    }
  }
}
