"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import type { ChatAction, ChatMessage } from "@/lib/types";
import { fmtPrice, fmtQty } from "@/lib/format";

/** Human-readable one-liner for an executed/failed action. */
export function describeAction(a: ChatAction): string {
  if (a.type === "trade") {
    const verb = a.side === "buy" ? "Bought" : "Sold";
    const base = `${fmtQty(a.quantity)} ${a.ticker}`;
    if (a.status === "executed") {
      return a.price != null ? `${verb} ${base} @ $${fmtPrice(a.price)}` : `${verb} ${base}`;
    }
    const v = a.side === "buy" ? "Buy" : "Sell";
    return `${v} ${base} failed${a.error ? `: ${a.error}` : ""}`;
  }
  if (a.status === "executed") {
    return a.action === "add" ? `Added ${a.ticker} to watchlist` : `Removed ${a.ticker} from watchlist`;
  }
  const v = a.action === "add" ? "Add" : "Remove";
  return `${v} ${a.ticker} failed${a.error ? `: ${a.error}` : ""}`;
}

export function ActionList({ actions }: { actions: ChatAction[] | null | undefined }) {
  if (!actions || actions.length === 0) return null;
  return (
    <ul className="mt-1.5 space-y-1" data-testid="chat-actions">
      {actions.map((a, i) => {
        const ok = a.status === "executed";
        return (
          <li
            key={i}
            data-testid="chat-action"
            data-status={a.status}
            data-type={a.type}
            className={`flex items-start gap-1.5 rounded-sm border px-2 py-1 font-mono text-2xs ${
              ok ? "border-up/30 bg-up/10 text-up" : "border-down/30 bg-down/10 text-down"
            }`}
          >
            <span aria-hidden className="font-bold">
              {ok ? "✓" : "✗"}
            </span>
            <span>{describeAction(a)}</span>
          </li>
        );
      })}
    </ul>
  );
}

interface ChatPanelProps {
  open: boolean;
  onToggle: () => void;
  messages: ChatMessage[];
  loading: boolean;
  onSend: (text: string) => void;
  loadError?: string | null;
}

const SUGGESTIONS = ["How is my portfolio doing?", "Buy 5 NVDA", "What's my biggest risk?"];

export default function ChatPanel({ open, onToggle, messages, loading, onSend, loadError }: ChatPanelProps) {
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages.length, loading, open]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;
    onSend(text);
    setInput("");
  };

  if (!open) {
    return (
      <aside
        data-testid="chat-panel"
        data-open="false"
        className="flex shrink-0 border-l border-ink-700 bg-ink-850/80 lg:w-11 lg:flex-col"
      >
        <button
          type="button"
          data-testid="chat-toggle"
          onClick={onToggle}
          aria-label="Open AI assistant"
          className="flex w-full items-center justify-center gap-2 py-2 text-2xs font-semibold uppercase tracking-[0.2em] text-accent hover:bg-ink-800 lg:h-full lg:flex-col lg:py-4"
        >
          <span className="rounded-sm bg-accent px-1 font-mono text-ink-950">AI</span>
          <span className="lg:[writing-mode:vertical-rl]">FinAlly Assistant</span>
        </button>
      </aside>
    );
  }

  return (
    <aside
      data-testid="chat-panel"
      data-open="true"
      className="flex h-[440px] shrink-0 flex-col border-t border-ink-700 bg-ink-850/90 lg:h-auto lg:w-[360px] lg:border-l lg:border-t-0 xl:w-[400px]"
    >
      <header className="flex h-9 shrink-0 items-center justify-between border-b border-ink-700 bg-ink-800/70 px-3">
        <div className="flex items-center gap-2">
          <span className="rounded-sm bg-accent px-1 font-mono text-2xs font-bold text-ink-950">AI</span>
          <span className="text-xs font-semibold text-slate-100">FinAlly Assistant</span>
          <span className="font-mono text-2xs text-mute-500">gpt-oss-120b</span>
        </div>
        <button
          type="button"
          data-testid="chat-toggle"
          onClick={onToggle}
          aria-label="Collapse AI assistant"
          className="rounded-sm px-1.5 font-mono text-sm text-mute-400 hover:bg-ink-700 hover:text-slate-100"
        >
          »
        </button>
      </header>

      <div data-testid="chat-messages" className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3">
        {messages.length === 0 && !loading ? (
          <div className="space-y-3 pt-6 text-center">
            <p className="text-xs text-mute-400">
              Ask about your portfolio, get analysis, or tell me to trade and manage your watchlist.
            </p>
            <div className="flex flex-wrap justify-center gap-1.5">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setInput(s)}
                  className="rounded-sm border border-ink-600 px-2 py-1 font-mono text-2xs text-mute-400 hover:border-primary hover:text-primary"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : null}
        {loadError ? <p className="font-mono text-2xs text-down">{loadError}</p> : null}
        {messages.map((m) => (
          <div
            key={m.id}
            data-testid="chat-message"
            data-role={m.role}
            className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}
          >
            <span className="mb-0.5 font-mono text-2xs uppercase tracking-wider text-mute-600">
              {m.role === "user" ? "You" : "FinAlly"}
            </span>
            <div
              className={`max-w-[92%] whitespace-pre-wrap rounded-sm px-2.5 py-1.5 text-xs leading-relaxed ${
                m.role === "user"
                  ? "border border-primary/30 bg-primary/10 text-slate-100"
                  : "border border-ink-700 bg-ink-800 text-slate-200"
              }`}
            >
              <span data-testid="chat-message-content">{m.content}</span>
              <ActionList actions={m.actions} />
            </div>
          </div>
        ))}
        {loading ? (
          <div data-testid="chat-loading" role="status" className="flex items-center gap-2 text-xs text-mute-400">
            <span className="font-mono text-2xs uppercase tracking-wider text-mute-600">FinAlly</span>
            <span className="flex gap-0.5" aria-label="FinAlly is thinking">
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-accent" />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-accent" />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-accent" />
            </span>
          </div>
        ) : null}
        <div ref={endRef} />
      </div>

      <form onSubmit={submit} className="shrink-0 border-t border-ink-700 p-2">
        <div className="flex gap-1.5">
          <input
            data-testid="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask FinAlly… e.g. “buy 10 AAPL”"
            aria-label="Message FinAlly"
            className="min-w-0 flex-1 rounded-sm border border-ink-600 bg-ink-900 px-2 py-1.5 text-xs text-slate-100 placeholder:text-mute-600 focus:border-primary focus:outline-none"
          />
          <button
            type="submit"
            data-testid="chat-send"
            disabled={loading || !input.trim()}
            className="rounded-sm bg-secondary px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-secondary-bright disabled:cursor-not-allowed disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </form>
    </aside>
  );
}
