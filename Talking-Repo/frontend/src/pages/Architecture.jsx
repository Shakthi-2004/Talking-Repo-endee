import { useEffect, useState } from "react";
import { Loader2, Folder, FileCode, Layers } from "lucide-react";
import { api } from "../lib/api";
import RepoSelector from "../components/app/RepoSelector";

export default function ArchitecturePage({ repos, activeRepo, setActiveRepo }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!activeRepo) {
      setData(null);
      return;
    }
    setLoading(true);
    setErr(null);
    api
      .get(`/architecture/${activeRepo}`)
      .then((r) => setData(r.data))
      .catch((e) => setErr(e.response?.data?.detail || "Failed to load architecture"))
      .finally(() => setLoading(false));
  }, [activeRepo]);

  return (
    <div className="space-y-6 fade-in" data-testid="page-architecture">
      <header className="border-b border-zinc-800 pb-6">
        <div className="text-xs font-mono uppercase tracking-widest text-zinc-500 mb-2">
          architecture
        </div>
        <h1 className="font-display text-3xl text-zinc-100">Architecture analysis</h1>
        <p className="text-sm text-zinc-400 mt-2">
          Auto-generated tech-stack detection, folder layout, API surface, and module graph.
        </p>
      </header>

      <RepoSelector repos={repos} activeRepo={activeRepo} setActiveRepo={setActiveRepo} />

      {loading && (
        <div className="text-sm font-mono text-zinc-400 flex items-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin" /> Analyzing...
        </div>
      )}
      {err && <div className="text-sm text-red-400 font-mono">{err}</div>}

      {data && (
        <>
          <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Stat label="Files" value={data.summary.total_files} />
            <Stat label="Size" value={`${(data.summary.total_bytes / 1024).toFixed(1)} KB`} />
            <Stat label="Routes" value={data.api_routes.length} />
          </section>

          {data.brief && (
            <section
              className="border border-zinc-800 rounded-md p-5 bg-zinc-900/30"
              data-testid="architecture-brief"
            >
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-display text-lg text-zinc-100 flex items-center gap-2">
                  <Layers className="h-4 w-4 text-cyan-400" /> Architecture brief
                </h2>
                <span className="text-[10px] uppercase tracking-widest text-zinc-500 font-mono">
                  generated from {data.brief_citations?.length || 0} Endee retrievals
                </span>
              </div>
              <div className="text-sm text-zinc-300 leading-relaxed whitespace-pre-wrap">
                {data.brief}
              </div>
              {data.brief_citations?.length > 0 && (
                <div className="mt-4 flex flex-wrap gap-1.5">
                  {data.brief_citations.map((c, i) => (
                    <span
                      key={i}
                      title={c.snippet}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-zinc-800 text-xs font-mono border border-zinc-700 text-zinc-300"
                    >
                      <span className="text-cyan-400">{c.file}</span>
                      <span className="text-zinc-500">·</span>
                      <span className="text-zinc-500">{c.chunk_type}</span>
                    </span>
                  ))}
                </div>
              )}
            </section>
          )}

          <section className="border border-zinc-800 rounded-md p-5 bg-zinc-900/30">
            <h2 className="font-display text-lg text-zinc-100 mb-3 flex items-center gap-2">
              <Layers className="h-4 w-4 text-cyan-400" /> Tech stack
            </h2>
            <div className="flex flex-wrap gap-2">
              {data.tech_stack.length === 0 ? (
                <span className="text-sm font-mono text-zinc-500">No manifests detected.</span>
              ) : (
                data.tech_stack.map((t) => (
                  <span
                    key={t}
                    className="text-xs font-mono px-3 py-1 bg-zinc-800 border border-zinc-700 rounded-full text-zinc-200"
                    data-testid={`stack-${t}`}
                  >
                    {t}
                  </span>
                ))
              )}
            </div>
          </section>

          <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="border border-zinc-800 rounded-md p-5 bg-zinc-900/30">
              <h2 className="font-display text-lg text-zinc-100 mb-3 flex items-center gap-2">
                <FileCode className="h-4 w-4 text-cyan-400" /> Languages
              </h2>
              <ul className="space-y-2">
                {data.languages.map((l) => (
                  <li key={l.language} className="font-mono text-xs flex items-center gap-2">
                    <span className="w-24 truncate text-zinc-300">{l.language}</span>
                    <div className="flex-1 h-1.5 bg-zinc-800 rounded">
                      <div
                        className="h-full bg-cyan-500 rounded"
                        style={{
                          width: `${Math.min(100, (l.files / data.summary.total_files) * 100)}%`,
                        }}
                      />
                    </div>
                    <span className="text-zinc-500 w-10 text-right">{l.files}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="border border-zinc-800 rounded-md p-5 bg-zinc-900/30 max-h-96 overflow-y-auto">
              <h2 className="font-display text-lg text-zinc-100 mb-3 flex items-center gap-2">
                <Folder className="h-4 w-4 text-cyan-400" /> Folder tree
              </h2>
              <Tree node={data.folder_tree} />
            </div>
          </section>

          <section className="border border-zinc-800 rounded-md p-5 bg-zinc-900/30">
            <h2 className="font-display text-lg text-zinc-100 mb-3">API routes</h2>
            <ul className="font-mono text-xs space-y-1" data-testid="api-routes">
              {data.api_routes.length === 0 ? (
                <li className="text-zinc-500">None detected.</li>
              ) : (
                data.api_routes.slice(0, 50).map((r, i) => (
                  <li key={i} className="flex items-center gap-3">
                    <span className="w-14 text-cyan-400">{r.method}</span>
                    <span className="text-zinc-200 flex-1 truncate">{r.path}</span>
                    <span className="text-zinc-500 truncate">{r.file}</span>
                  </li>
                ))
              )}
            </ul>
          </section>

          <section className="border border-zinc-800 rounded-md p-5 bg-zinc-900/30">
            <h2 className="font-display text-lg text-zinc-100 mb-3">Module graph</h2>
            <div className="text-xs font-mono text-zinc-500 mb-3">
              {data.graph.nodes.length} nodes · {data.graph.edges.length} edges
            </div>
            <Graph nodes={data.graph.nodes} edges={data.graph.edges} />
          </section>
        </>
      )}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="p-5 border border-zinc-800 rounded-md bg-zinc-900/30">
      <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-mono mb-2">{label}</div>
      <div className="text-3xl font-display text-zinc-100 tracking-tight">{value}</div>
    </div>
  );
}

function Tree({ node }) {
  if (!node) return null;
  const rows = [];
  const walk = (n, depth) => {
    rows.push({ name: n.name, type: n.type, depth, key: rows.length });
    if (n.children) {
      for (const c of n.children) walk(c, depth + 1);
    }
  };
  walk(node, 0);
  return (
    <ul className="font-mono text-xs space-y-0.5">
      {rows.map((r) => (
        <li key={r.key} className={r.type === "dir" ? "text-zinc-200" : "text-zinc-400"}>
          <span>{"\u00A0\u00A0".repeat(r.depth)}{r.type === "dir" ? "▸" : "·"} {r.name}</span>
        </li>
      ))}
    </ul>
  );
}

function Graph({ nodes, edges }) {
  if (nodes.length === 0) return <div className="text-sm text-zinc-500 font-mono">No graph data.</div>;
  // Simple radial SVG layout
  const W = 720, H = 360;
  const cx = W / 2, cy = H / 2;
  const r = Math.min(W, H) / 2 - 30;
  const positions = {};
  nodes.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / nodes.length;
    positions[n.id] = { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
  });
  return (
    <div className="overflow-x-auto">
      <svg width={W} height={H} className="bg-black rounded border border-zinc-800">
        {edges.map((e, i) => {
          const s = positions[e.source];
          const t = positions[e.target];
          if (!s || !t) return null;
          return (
            <line
              key={i}
              x1={s.x}
              y1={s.y}
              x2={t.x}
              y2={t.y}
              stroke="#27272a"
              strokeWidth="1"
            />
          );
        })}
        {nodes.map((n) => {
          const p = positions[n.id];
          return (
            <g key={n.id}>
              <circle cx={p.x} cy={p.y} r="3" fill="#22d3ee" />
              <text x={p.x + 5} y={p.y + 3} fontSize="9" fill="#a1a1aa" fontFamily="JetBrains Mono">
                {n.label.slice(0, 16)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
