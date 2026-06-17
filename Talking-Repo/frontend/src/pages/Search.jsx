import { useState } from "react";
import { Search as SearchIcon, Loader2 } from "lucide-react";
import { api } from "../lib/api";
import { toast } from "sonner";
import RepoSelector from "../components/app/RepoSelector";

const SUGGESTIONS = [
  "authentication logic",
  "database connection",
  "JWT implementation",
  "payment flow",
  "API rate limiting",
];

export default function SearchPage({ repos, activeRepo, setActiveRepo }) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState([]);
  const [tookMs, setTookMs] = useState(null);

  const run = async (q) => {
    const targetQuery = (q ?? query).trim();
    if (!targetQuery) return;
    if (!activeRepo) {
      toast.error("Select an indexed repository first.");
      return;
    }
    setQuery(targetQuery);
    setLoading(true);
    try {
      const { data } = await api.post("/search", {
        repository_id: activeRepo,
        query: targetQuery,
        top_k: 8,
      });
      setResults(data.results || []);
      setTookMs(data.took_ms);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Search failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 fade-in" data-testid="page-search">
      <header className="border-b border-zinc-800 pb-6">
        <div className="text-xs font-mono uppercase tracking-widest text-zinc-500 mb-2">
          semantic_search
        </div>
        <h1 className="font-display text-3xl text-zinc-100">Search the codebase</h1>
        <p className="text-sm text-zinc-400 mt-2">
          Natural-language queries embedded with all-MiniLM-L6-v2 and matched in Endee.
        </p>
      </header>

      <RepoSelector repos={repos} activeRepo={activeRepo} setActiveRepo={setActiveRepo} />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          run();
        }}
        className="flex items-center gap-2"
      >
        <div className="flex-1 flex items-center gap-2 border border-zinc-800 focus-within:border-zinc-600 bg-black rounded-md px-3 py-2">
          <SearchIcon className="h-4 w-4 text-zinc-500" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. how does authentication work?"
            className="flex-1 bg-transparent outline-none text-sm font-mono text-zinc-200 placeholder:text-zinc-600"
            data-testid="search-input"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="bg-zinc-100 text-zinc-900 hover:bg-white px-4 py-2 rounded-md text-sm font-medium disabled:opacity-60"
          data-testid="search-submit-btn"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Search"}
        </button>
      </form>

      <div className="flex flex-wrap gap-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => run(s)}
            className="text-xs font-mono px-3 py-1.5 border border-zinc-800 hover:border-zinc-600 text-zinc-400 hover:text-zinc-100 rounded-full"
            data-testid={`suggestion-${s.replace(/\s/g, "-")}`}
          >
            {s}
          </button>
        ))}
      </div>

      {tookMs !== null && (
        <div className="text-xs font-mono text-zinc-500">
          {results.length} result{results.length === 1 ? "" : "s"} · {tookMs}ms
        </div>
      )}

      <ul className="flex flex-col gap-4" data-testid="search-results">
        {results.map((r, i) => (
          <li
            key={r.id}
            className="border border-zinc-800 rounded-md bg-zinc-900/30 hover:border-zinc-700 transition-colors"
            data-testid={`search-result-${i}`}
          >
            <div className="flex justify-between items-center text-xs font-mono text-zinc-500 px-4 py-2 border-b border-zinc-800">
              <span className="truncate text-zinc-300">
                {r.file}
                {r.start_line ? `  L${r.start_line}-${r.end_line}` : ""}
              </span>
              <span className="flex items-center gap-2">
                <Badge>{r.language}</Badge>
                <Badge>{r.chunk_type}</Badge>
                <span className="text-cyan-400">{(r.score * 100).toFixed(1)}%</span>
              </span>
            </div>
            <pre className="px-4 py-3 text-xs overflow-x-auto text-zinc-300 leading-relaxed">
              <code>{r.content}</code>
            </pre>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Badge({ children }) {
  return (
    <span className="px-2 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-zinc-300">
      {children}
    </span>
  );
}
