"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, ArrowUp, User, AlertCircle, ExternalLink } from "lucide-react";
import Link from "next/link";
import { ChatMessage } from "@/lib/types";
import { Button } from "@/components/ui/button";
import {
  getChatSessions, createChatSession, addChatMessage,
  getPaperChatContext, askPaperEphemeral, promotePaperChat, ChatMode,
} from "@/lib/api/chat";
import { projectChat, ChatCitation } from "@/lib/api/project_ai";
import { createSavedArtifact } from "@/lib/api/projects";
import { BookmarkPlus, Check } from "lucide-react";
import toast from "react-hot-toast";

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
/** Ephemeral history in the shape the API accepts. Content is clipped to the
 *  server's per-message limit so a long reply cannot 422 the next turn. */
function toTurns(msgs: ChatMessage[]) {
  return msgs.map((m) => ({ role: m.role, content: m.content.slice(0, 8000) }));
}

/** The paper-chat endpoints return snake_case rows straight from the DB. */
function normalizeMessage(m: any): ChatMessage {
  return {
    id: m.id ?? crypto.randomUUID(),
    role: m.role,
    content: m.content,
    citedPaperIds: m.citedPaperIds ?? m.cited_paper_ids ?? [],
    createdAt: m.createdAt ?? m.created_at ?? new Date().toISOString(),
  };
}

/** Restored history carries cited paper IDs but not the original evidence, so
 *  older replies get link-only citations rather than fabricated reasons. */
function placeholderCitations(msgs: any[]): Record<string, ChatCitation[]> {
  const out: Record<string, ChatCitation[]> = {};
  for (const m of msgs) {
    const ids = m.citedPaperIds ?? m.cited_paper_ids ?? [];
    if (m.role === "assistant" && ids.length > 0) {
      out[m.id] = ids.map((id: string) => ({
        paper_id: id,
        title: "Cited Paper",
        reason: "Cited in previous conversation",
      }));
    }
  }
  return out;
}

export function AIChatPanel({
  initialMessages = [],
  contextLabel,
  placeholder = "Ask about the papers in this project…",
  projectId,
  paperId,
  paperSaved,
}: {
  initialMessages?: ChatMessage[];
  contextLabel?: string;
  placeholder?: string;
  projectId?: string;
  paperId?: string;
  /** Whether the paper is in one of the user's projects. Flipping this to true
   *  promotes an in-progress ephemeral conversation to persistent. */
  paperSaved?: boolean;
}) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [chatMode, setChatMode] = useState<ChatMode | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [messageCitations, setMessageCitations] = useState<Record<string, ChatCitation[]>>({});
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastModel, setLastModel] = useState<string | undefined>(undefined);
  const scrollRef = useRef<HTMLDivElement>(null);

  const isProjectMode = Boolean(projectId && !paperId);
  const hasSomeContext = Boolean(projectId || paperId);

  // Auto-load existing session (for both paper and project modes)
  useEffect(() => {
    async function initSession() {
      if (!paperId && !projectId) return;
      try {
        // Paper mode: the server decides ephemeral vs persistent from whether
        // the paper is saved, and returns the history to restore. An ephemeral
        // paper has none by definition, so a reopen starts blank.
        if (paperId && !projectId) {
          const ctx = await getPaperChatContext(paperId);
          setChatMode(ctx.mode);
          setSessionId(ctx.session_id);
          if (ctx.messages.length > 0) {
            setMessages(ctx.messages.map(normalizeMessage));
            setMessageCitations(placeholderCitations(ctx.messages));
          }
          return;
        }

        const sessions = await getChatSessions(projectId, paperId);
        if (sessions.length > 0) {
          setSessionId(sessions[0].id);
          if (sessions[0].messages) {
            setMessages(sessions[0].messages);
            
            // Reconstruct basic citations for previous assistant messages
            const citationsMap: Record<string, ChatCitation[]> = {};
            sessions[0].messages.forEach((msg) => {
              const citedIds = msg.citedPaperIds || (msg as any).cited_paper_ids;
              if (msg.role === "assistant" && citedIds && citedIds.length > 0) {
                // We only have the IDs from the backend, so we create placeholder citations
                citationsMap[msg.id] = citedIds.map((id: string) => ({
                  paper_id: id,
                  title: "Cited Paper",
                  reason: "Cited in previous conversation"
                }));
              }
            });
            setMessageCitations(citationsMap);
          }
        }
      } catch (err) {
        console.error("Failed to load chat sessions:", err);
      }
    }
    initSession();
  }, [paperId, projectId]);

  // Promotion: saving the paper mid-conversation carries that conversation into
  // the persistent session. Nothing is written until the save has succeeded.
  const messagesRef = useRef<ChatMessage[]>(messages);
  messagesRef.current = messages;

  useEffect(() => {
    if (!paperId || projectId) return;
    if (!paperSaved || chatMode !== "ephemeral") return;
    let active = true;
    (async () => {
      try {
        const res = await promotePaperChat(paperId, toTurns(messagesRef.current));
        if (!active) return;
        setSessionId(res.session_id);
        setChatMode("persistent");
      } catch (err) {
        // The paper is saved regardless; only the carry-over failed. Staying in
        // ephemeral mode is the honest state — the banner keeps saying the
        // conversation is not stored, which is true.
        console.error("Failed to promote paper chat:", err);
      }
    })();
    return () => { active = false; };
  }, [paperId, projectId, paperSaved, chatMode]);

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

      // ── Paper Mode, ephemeral: nothing is stored server-side. The history
      //    the model sees comes from this page and dies with it. ────────────
      if (paperId && chatMode === "ephemeral") {
        const result = await askPaperEphemeral(paperId, userMsg.content, toTurns(messages));
        setLastModel(result.ai_message.model);
        setMessages((prev) => [
          ...prev,
          normalizeMessage({ ...result.ai_message, id: crypto.randomUUID() }),
        ]);
        return;
      }

      // ── Paper Mode, persistent: session-backed, history stored ────────────
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
          {paperId && chatMode && (
            <p className="text-xs text-ink-faint">
              {chatMode === "ephemeral"
                ? "Temporary chat — save this paper to a project to keep your conversation."
                : "Saved to a project — chat history is kept."}
            </p>
          )}
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
            projectId={projectId}
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

function ChatBubble({ message, citations, projectId }: { message: ChatMessage; citations?: ChatCitation[]; projectId?: string }) {
  const isUser = message.role === "user";
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSave = async () => {
    if (!projectId || saving || saved) return;
    setSaving(true);
    try {
      await createSavedArtifact(projectId, {
        type: "chat_answer",
        title: message.content.slice(0, 40) + "...",
        content: message.content,
        citedPaperIds: citations?.map(c => c.paper_id) || []
      });
      setSaved(true);
      toast.success("Saved to artifacts");
    } catch (e) {
      console.error("Failed to save artifact:", e);
      toast.error("Failed to save artifact");
    } finally {
      setSaving(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`group flex gap-2.5 ${isUser ? "flex-row-reverse" : ""}`}
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
        
        {!isUser && projectId && (
          <div className="mt-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <Button
              variant="ghost"
              size="sm"
              className="h-6 text-[10px] text-ink-faint hover:text-teal-600 gap-1 px-2"
              onClick={handleSave}
              disabled={saving || saved}
            >
              {saved ? <Check className="h-3 w-3 text-green-600" /> : <BookmarkPlus className="h-3 w-3" />}
              {saved ? "Saved to artifacts" : "Save to artifacts"}
            </Button>
          </div>
        )}
      </div>
    </motion.div>
  );
}


