"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, ArrowUp, User } from "lucide-react";
import { ChatMessage } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { getPaperById } from "@/lib/mock-data";
import Link from "next/link";

const mockReplies = [
  "Based on the papers saved here, the strongest signal is a shift toward parameter-efficient adaptation rather than full retraining — worth foregrounding in your framing.",
  "That's covered in the methodology section — the authors validate this with an ablation that isolates the effect from confounding hyperparameter changes.",
  "A few papers in this collection touch on that, but none benchmark it directly. It could be a genuine gap worth flagging in your literature review.",
  "Comparing the two, they agree on the core mechanism but differ in evaluation scale — one uses held-out benchmarks, the other reports only in-domain results.",
];

export function AIChatPanel({
  initialMessages,
  contextLabel,
  placeholder = "Ask about the papers in this project…",
}: {
  initialMessages: ChatMessage[];
  contextLabel?: string;
  placeholder?: string;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, thinking]);

  function handleSend() {
    if (!input.trim()) return;
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: input.trim(),
      createdAt: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setThinking(true);

    setTimeout(() => {
      const reply: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: mockReplies[Math.floor(Math.random() * mockReplies.length)],
        citedPaperIds: ["p1", "p4"].slice(0, Math.floor(Math.random() * 2) + 1),
        createdAt: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, reply]);
      setThinking(false);
    }, 1100);
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
      </div>

      <div ref={scrollRef} className="thin-scroll flex-1 space-y-4 overflow-y-auto px-5 py-5">
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
              Reading the papers…
            </motion.div>
          )}
        </AnimatePresence>
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
            placeholder={placeholder}
            className="max-h-28 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-ink placeholder:text-ink-faint focus:outline-none"
          />
          <Button size="icon" onClick={handleSend} disabled={!input.trim()}>
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
        {message.citedPaperIds && message.citedPaperIds.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {message.citedPaperIds.map((id) => {
              const paper = getPaperById(id);
              if (!paper) return null;
              return (
                <Link key={id} href={`/papers/${id}`}>
                  <Badge variant="outline" className="cursor-pointer hover:bg-paper-dim">
                    {paper.title.length > 28 ? paper.title.slice(0, 28) + "…" : paper.title}
                  </Badge>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </motion.div>
  );
}
