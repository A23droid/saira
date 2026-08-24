"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, ArrowUp, User, AlertCircle, ExternalLink } from "lucide-react";
import Link from "next/link";
import { ChatMessage } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { getChatSessions, createChatSession, addChatMessage } from "@/lib/api/chat";
import { projectChat, ChatCitation } from "@/lib/api/project_ai";

/**
 * AI Chat Panel — supports both paper-scoped and project-scoped chat.
 *
 * When projectId is provided:
 *   - Uses POST /projects/{projectId}/ai/chat (retrieval + structured citations)
 *   - Citations are rendered as clickable links below the AI reply
 *
 * When paperId is provided:
 *   - Uses the existing /chat/sessions endpoint for paper-level QA
 */
export function AIChatPanel({
  initialMessages = [],
  contextLabel,
  placeholder = "Ask about the papers in this project…",
  projectId,
  paperId,
}: {
  initialMessages?: ChatMessage[];
  contextLabel?: string;
  placeholder?: string;
  projectId?: string;
  paperId?: string;
}) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [messageCitations, setMessageCitations] = useState<Record<string, ChatCitation[]>>({});
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastModel, setLastModel] = useState<string | undefined>(undefined);
  const scrollRef = useRef<HTMLDivElement>(null);

  const isProjectMode = Boolean(projectId && !paperId);
  const hasSomeContext = Boolean(projectId || paperId);

  // Auto-load existing paper-mode session (project mode creates sessions on-demand)
  useEffect(() => {
    async function initSession() {
      if (!paperId) return;
      try {
        const sessions = await getChatSessions(undefined, paperId);
        if (sessions.length > 0) {
          setSessionId(sessions[0].id);
          if (sessions[0].messages) {
            setMessages(sessions[0].messages);
          }
        }
      } catch (err) {
        console.error("Failed to load chat sessions:", err);
      }
    }
    initSession();
  }, [paperId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, thinking]);

  async function handleSend() {
    if (!input.trim() || thinking || !hasSomeContext) return;

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
      // ── Project Mode: use new retrieval-backed chat endpoint ──────────────
      if (isProjectMode && projectId) {
        const result = await projectChat(projectId, userMsg.content, sessionId);
        if (result.session_id) setSessionId(result.session_id);
        if (result.model) setLastModel(result.model);

        const replyId = crypto.randomUUID();
        const reply: ChatMessage = {
          id: replyId,
          role: "assistant",
          content: result.answer,
          citedPaperIds: result.citations.map((c) => c.paper_id),
          createdAt: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, reply]);
        if (result.citations.length > 0) {
          setMessageCitations((prev) => ({ ...prev, [replyId]: result.citations }));
        }
        return;
      }

      // ── Paper Mode: use existing session-based endpoint ────────────────────
      let activeSessionId = sessionId;
      if (!activeSessionId) {
        const newSession = await createChatSession({
          title: userMsg.content.substring(0, 30) + (userMsg.content.length > 30 ? "..." : ""),
          paper_id: paperId,
        });
        activeSessionId = newSession.id;
        setSessionId(activeSessionId);
      }

      const result = await addChatMessage(activeSessionId, userMsg.content);
      setLastModel(result.ai_message.model);

      const reply: ChatMessage = {
        id: result.ai_message.id,
        role: "assistant",
        content: result.ai_message.content,
        createdAt: (result.ai_message as any).created_at || new Date().toISOString(),
      };
      setMessages((prev) => [...prev, reply]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to get an answer. Please try again.";
      setError(msg);
    } finally {
      setThinking(false);
    }
  }

  const emptyStateText = isProjectMode
    ? "Ask anything about the papers in this project. SAIRA will retrieve relevant context and cite sources."
    : paperId
      ? "Ask any question about this paper. SAIRA will answer using its metadata."
      : "Open a paper or project to enable AI Q&A.";

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-line bg-surface">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-line-soft px-5 py-3.5">
        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-teal-50">
          <Sparkles className="h-3.5 w-3.5 text-teal-600" />
        </div>
        <div>
          <p className="text-sm font-medium text-ink">Ask SAIRA</p>
          {contextLabel && <p className="text-xs text-ink-faint">{contextLabel}</p>}
        </div>
        {hasSomeContext && lastModel && (
          <span className="ml-auto rounded-full bg-teal-50 px-2 py-0.5 text-[10px] font-medium text-teal-700">
            {lastModel}
          </span>
        )}
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="thin-scroll flex-1 space-y-4 overflow-y-auto px-5 py-5">
        {messages.length === 0 && (
          <p className="text-center text-xs text-ink-faint">{emptyStateText}</p>
        )}
        {messages.map((m) => (
          <ChatBubble
            key={m.id}
            message={m}
            citations={messageCitations[m.id]}
          />
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
                <Sparkles className="h-3 w-3 text-teal-600 animate-pulse" />
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

      {/* Input */}
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
            placeholder={hasSomeContext ? placeholder : "Open a paper or project to enable AI Q&A…"}
            disabled={!hasSomeContext || thinking}
            className="max-h-28 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-ink placeholder:text-ink-faint focus:outline-none disabled:opacity-50"
          />
          <Button size="icon" onClick={handleSend} disabled={!input.trim() || thinking || !hasSomeContext}>
            <ArrowUp className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

function ChatBubble({ message, citations }: { message: ChatMessage; citations?: ChatCitation[] }) {
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
        {/* Citations — only shown for assistant messages */}
        {!isUser && citations && citations.length > 0 && (
          <div className="mt-2 space-y-1">
            {citations.map((c, i) => (
              <Link
                key={c.paper_id}
                href={`/papers/${c.paper_id}`}
                className="flex items-center gap-1.5 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs text-ink-soft hover:border-teal-400 hover:text-teal-700 transition-colors"
              >
                <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-teal-50 text-[10px] font-bold text-teal-600">
                  {i + 1}
                </span>
                <span className="line-clamp-1 flex-1">{c.title}{c.year ? ` (${c.year})` : ""}</span>
                <ExternalLink className="h-3 w-3 shrink-0 opacity-50" />
              </Link>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
}


