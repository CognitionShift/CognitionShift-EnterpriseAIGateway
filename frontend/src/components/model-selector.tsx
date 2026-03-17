"use client";

import { ModelInfo } from "@/lib/api";

interface ModelSelectorProps {
  models: ModelInfo[];
  selected: string;
  onChange: (modelId: string) => void;
}

export function ModelSelector({ models, selected, onChange }: ModelSelectorProps) {
  return (
    <select
      value={selected}
      onChange={(e) => onChange(e.target.value)}
      className="text-sm rounded-lg px-3 py-1.5 outline-none cursor-pointer"
      style={{
        backgroundColor: "var(--bg-tertiary)",
        border: "1px solid var(--border)",
        color: "var(--text-primary)",
      }}
      aria-label="Select AI model"
    >
      {models.map((model) => (
        <option key={model.id} value={model.id}>
          {model.display_name}
          {model.input_cost_per_1k ? ` ($${model.input_cost_per_1k}/1k in)` : ""}
        </option>
      ))}
    </select>
  );
}
