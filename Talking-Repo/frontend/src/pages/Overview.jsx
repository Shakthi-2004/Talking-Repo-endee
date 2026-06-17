import { Link } from "react-router-dom";
import { Database, Github, Search, MessageSquare, Network, Activity } from "lucide-react";

const FEATURES = [
  { icon: Github, title: "Ingest", desc: "Clone a public GitHub repo or drop in a .zip — Endee handles the indexing." },
  { icon: Search, title: "Semantic search", desc: "AST-aware chunking + sentence-transformers embeddings stored in Endee." },
  { icon: MessageSquare, title: "RAG chat", desc: "Conversational answers grounded in your code via Gemini 2.5 Flash." },
  { icon: Network, title: "Architecture", desc: "Auto-generated tech stack, API routes, folder tree, dependency graph." },
  { icon: Activity, title: "Health", desc: "Largest files, dead-code candidates, circular dependencies." },
  { icon: Database, title: "Endee-first", desc: "All retrieval workflows are built on the Endee vector DB API." },
];

export default function Overview({ repos = [], vectorStore }) {
  const ready = repos.filter((r) => r.status === "ready").length;
  return (
    <div className="space-y-10 fade-in" data-testid="page-overview">
      <header className="border-b border-zinc-800 pb-8">
        <div className="text-xs font-mono uppercase tracking-widest text-zinc-500 mb-3">
          endee_labs / codebase_assistant
        </div>
        <h1 className="font-display text-3xl sm:text-4xl text-zinc-100 max-w-2xl">
          Ask any codebase a question. <span className="text-cyan-400">Get answers with citations.</span>
        </h1>
        <p className="text-sm text-zinc-400 max-w-xl mt-4 leading-relaxed">
          A production-grade RAG assistant that indexes GitHub repositories into the Endee vector
          database, then lets you semantically search, chat, and audit them in seconds.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            to="/upload"
            data-testid="cta-add-repo"
            className="inline-flex items-center gap-2 bg-zinc-100 text-zinc-900 hover:bg-white px-4 py-2 rounded-md text-sm font-medium transition-colors"
          >
            <Github className="h-4 w-4" /> Add repository
          </Link>
          <Link
            to="/search"
            data-testid="cta-search"
            className="inline-flex items-center gap-2 border border-zinc-800 hover:border-zinc-600 text-zinc-100 px-4 py-2 rounded-md text-sm font-medium transition-colors"
          >
            <Search className="h-4 w-4" /> Try semantic search
          </Link>
        </div>
      </header>

      <section className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard label="Repositories" value={repos.length} testid="stat-repos" />
        <StatCard label="Ready to query" value={ready} testid="stat-ready" />
        <StatCard
          label="Vector backend"
          value={vectorStore?.backend || "—"}
          mono
          testid="stat-backend"
        />
      </section>

      <section>
        <h2 className="font-display text-xl text-zinc-100 mb-4">What it can do</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map((f) => (
            <div
              key={f.title}
              className="border border-zinc-800 rounded-md p-5 bg-zinc-900/30 hover:border-zinc-700 transition-colors"
            >
              <f.icon className="h-5 w-5 text-cyan-400 mb-3" />
              <div className="font-display text-base text-zinc-100 mb-1">{f.title}</div>
              <div className="text-sm text-zinc-400 leading-relaxed">{f.desc}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="border border-zinc-800 rounded-md p-6 bg-zinc-900/30">
        <h2 className="font-display text-xl text-zinc-100 mb-3">Why Endee</h2>
        <ul className="text-sm text-zinc-400 space-y-2 leading-relaxed">
          <li>• HNSW-backed ANN with INT8 precision for 4× memory savings on millions of code chunks.</li>
          <li>• Hybrid (dense + sparse) search ready for keyword-boosted queries.</li>
          <li>• Filterable metadata lets us scope retrieval to a single repository in one call.</li>
          <li>• A single SDK call surface for upsert, query, delete, describe.</li>
        </ul>
      </section>
    </div>
  );
}

function StatCard({ label, value, mono, testid }) {
  return (
    <div className="p-5 border border-zinc-800 rounded-md bg-zinc-900/30" data-testid={testid}>
      <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-mono mb-2">{label}</div>
      <div className={`text-3xl text-zinc-100 ${mono ? "font-mono" : "font-display"} tracking-tight`}>
        {value}
      </div>
    </div>
  );
}
