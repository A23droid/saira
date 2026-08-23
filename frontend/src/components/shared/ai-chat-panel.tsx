"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, ArrowUp, User, AlertCircle } from "lucide-react";
import { ChatMessage } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { askPaperQA, modelLabel } from "@/lib/api/ai";

/**
 * AI Chat Panel — wired to the SAIRA backend Q&A endpoint.
 *
 * When paperId is provided, questions are sent to POST /api/v1/ai/qa
 * which routes them through the AI Router to Llama 3.3 70B via Groq.
 *
 * When paperId is not provided (e.g. project-level context), the panel
 * shows a notice that paper context is required.
 */
export function AIChatPanel({
  initialMessages,
  contextLabel,
  placeholder = "Ask about the papers in this project…",
  paperId,
}: {
  initialMessages: ChatMessage[];
  contextLabel?: string;
  placeholder?: string;
  /** The database UUID of the paper to ask about. Required for real AI Q&A. */
  paperId?: string;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastModel, setLastModel] = useState<string | undefined>(undefined);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, thinking]);

  async function handleSend() {
    if (!input.trim() || thinking) return;

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: input.trim(),
      createdAt: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setThinking(true);
    setError(null);

    try {
      if (!paperId) {
        // No paper context — give a helpful notice instead of crashing
        const reply: ChatMessage = {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "Please open a specific paper to ask questions about it. The AI Q&A feature requires a paper context.",
          createdAt: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, reply]);
        return;
      }

      const result = await askPaperQA(paperId, userMsg.content);
      setLastModel(result.model);
      const reply: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: result.answer,
        createdAt: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, reply]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to get an answer. Please try again.";
      setError(msg);
    } finally {
      setThinking(false);
    }
  }

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-line bg-surface">
      <div className="flex items-center gap-2 border-b border-line-soft px-5 py-3.5">
        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-teal-50">
          <Sparkles className="h-3.5 w-3.5 text-teal-600" />
        </div>
        <div>
          <p className="text-sm font-medium text-ink">Ask SAIRA</p>
          {contextLabel && <p className="text-xs text-ink-faint">{contextLabel}</p>}
        </div>
        {paperId && lastModel && (
          <span className="ml-auto rounded-full bg-teal-50 px-2 py-0.5 text-[10px] font-medium text-teal-700">
            {modelLabel(lastModel)}
          </span>
        )}
      </div>

      <div ref={scrollRef} className="thin-scroll flex-1 space-y-4 overflow-y-auto px-5 py-5">
        {messages.length === 0 && (
          <p className="text-center text-xs text-ink-faint">
            {paperId
              ? "Ask any question about this paper. SAIRA will answer using its metadata."
              : "Open a paper to enable AI Q&A."}
          </p>
        )}
        {messages.map((m) => (
          <ChatBubble key={m.id} message={m} />
        ))}
        <AnimatePresence>
          {thinking && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex items-center gap-2 text-xs text-ink-faint"
            >
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-teal-50">
                <Sparkles className="h-3 w-3 text-teal-600" />
              </span>
              Thinking…
            </motion.div>
          )}
        </AnimatePresence>
        {error && (
          <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-3">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
            <p className="text-xs text-red-700">{error}</p>
          </div>
        )}
      </div>

      <div className="border-t border-line-soft p-3">
        <div className="flex items-end gap-2 rounded-2xl border border-line bg-paper-dim/40 p-2 focus-within:border-teal-500">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            rows={1}
            placeholder={paperId ? placeholder : "Open a paper to enable AI Q&A…"}
            disabled={!paperId || thinking}
            className="max-h-28 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-ink placeholder:text-ink-faint focus:outline-none disabled:opacity-50"
          />
          <Button size="icon" onClick={handleSend} disabled={!input.trim() || thinking || !paperId}>
            <ArrowUp className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`flex gap-2.5 ${isUser ? "flex-row-reverse" : ""}`}
    >
      <div
        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${
          isUser ? "bg-paper-dim text-ink-soft" : "bg-teal-50 text-teal-600"
        }`}
      >
        {isUser ? <User className="h-3.5 w-3.5" /> : <Sparkles className="h-3.5 w-3.5" />}
      </div>
      <div className={`max-w-[80%] ${isUser ? "text-right" : ""}`}>
        <div
          className={`inline-block rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
            isUser ? "bg-teal-600 text-white" : "bg-paper-dim text-ink"
          }`}
        >
          {message.content}
        </div>
      </div>
    </motion.div>
  );
}
