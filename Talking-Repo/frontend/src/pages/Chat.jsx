import { useEffect, useRef, useState } from "react";
import { Send, Loader2, Bot, User } from "lucide-react";
import { api } from "../lib/api";
import { toast } from "sonner";
import RepoSelector from "../components/app/RepoSelector";

export default function ChatPage({ repos, activeRepo, setActiveRepo }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    setMessages([]);
    setSessionId(null);
  }, [activeRepo]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const send = async (e) => {
    e?.preventDefault();
    const text = input.trim();
    if (!text) return;
    if (!activeRepo) {
      toast.error("Select an indexed repository first.");
      return;
    }
    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setLoading(true);
    try {
      const { data } = await api.post("/chat", {
        repository_id: activeRepo,
        question: text,
        session_id: sessionId,
      });
      setSessionId(data.session_id);
      setMessages((m) => [
        ...m,
        { role: "assistant", text: data.answer, citations: data.citations || [] },
      ]);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Chat failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full fade-in" data-testid="page-chat">
      <header className="border-b border-zinc-800 pb-6 mb-4">
        <div className="text-xs font-mono uppercase tracking-widest text-zinc-500 mb-2">
          rag_chat • Gemini_2.5_Flash
        </div>
        <h1 className="font-display text-3xl text-zinc-100">Ask the codebase</h1>
      </header>

      <RepoSelector repos={repos} activeRepo={activeRepo} setActiveRepo={setActiveRepo} />

      <div className="flex-1 overflow-y-auto py-6 space-y-6" data-testid="chat-messages">
        {messages.length === 0 && (
          <EmptyState onPick={(q) => setInput(q)} />
        )}
        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="flex justify-end" data-testid={`msg-user-${i}`}>
              <div className="bg-zinc-800 text-zinc-100 px-4 py-3 rounded-lg max-w-[80%]">
                <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest text-zinc-400 mb-1 font-mono">
                  <User className="h-3 w-3" /> you
                </div>
                <div className="text-sm whitespace-pre-wrap">{m.text}</div>
              </div>
            </div>
          ) : (
            <div key={i} className="space-y-3" data-testid={`msg-assistant-${i}`}>
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest text-zinc-500 font-mono">
                <Bot className="h-3 w-3 text-cyan-400" /> endee_assistant
              </div>
              <div className="text-sm text-zinc-200 leading-relaxed whitespace-pre-wrap max-w-[90%]">
                {m.text}
              </div>
              {m.citations?.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {m.citations.map((c, j) => (
                    <span
                      key={j}
                      title={c.snippet}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-zinc-800 text-xs font-mono border border-zinc-700 hover:border-zinc-500 cursor-default transition-colors text-zinc-300"
                      data-testid={`citation-${i}-${j}`}
                    >
                      <span className="text-cyan-400">{c.file}</span>
                      <span className="text-zinc-500">·</span>
                      <span className="text-zinc-500">{c.chunk_type}</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          )
        )}
        {loading && (
          <div className="text-sm font-mono text-cyan-400 terminal-cursor" data-testid="chat-typing">
            thinking
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={send}
        className="border-t border-zinc-800 pt-4 flex items-center gap-2"
        data-testid="chat-form"
      >
        <div className="flex-1 border border-zinc-800 focus-within:border-zinc-600 bg-black rounded-md px-3 py-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Explain the architecture of this codebase…"
            className="w-full bg-transparent outline-none text-sm font-mono text-zinc-200 placeholder:text-zinc-600"
            data-testid="chat-input-field"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="bg-zinc-100 text-zinc-900 hover:bg-white px-4 py-2 rounded-md disabled:opacity-60"
          data-testid="chat-send-btn"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </button>
      </form>
    </div>
  );
}

const STARTERS = [
  "Explain this codebase.",
  "How does authentication work?",
  "Which files handle user login?",
  "What APIs are exposed?",
];

function EmptyState({ onPick }) {
  return (
    <div className="border border-zinc-800 rounded-md p-6 bg-zinc-900/30" data-testid="chat-empty">
      <div className="text-sm text-zinc-400 mb-3 font-mono">Try a starter question:</div>
      <div className="flex flex-wrap gap-2">
        {STARTERS.map((q) => (
          <button
            key={q}
            onClick={() => onPick(q)}
            className="text-xs font-mono px-3 py-1.5 border border-zinc-800 hover:border-zinc-600 text-zinc-300 hover:text-zinc-100 rounded-full"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
