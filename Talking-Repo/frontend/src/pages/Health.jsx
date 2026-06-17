import { useEffect, useState } from "react";
import { Loader2, AlertTriangle, GitBranch, FileWarning } from "lucide-react";
import { api } from "../lib/api";
import RepoSelector from "../components/app/RepoSelector";

export default function HealthPage({ repos, activeRepo, setActiveRepo }) {
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
      .get(`/health-report/${activeRepo}`)
      .then((r) => setData(r.data))
      .catch((e) => setErr(e.response?.data?.detail || "Failed to load health report"))
      .finally(() => setLoading(false));
  }, [activeRepo]);

  return (
    <div className="space-y-6 fade-in" data-testid="page-health">
      <header className="border-b border-zinc-800 pb-6">
        <div className="text-xs font-mono uppercase tracking-widest text-zinc-500 mb-2">
          repository_health
        </div>
        <h1 className="font-display text-3xl text-zinc-100">Health report</h1>
        <p className="text-sm text-zinc-400 mt-2">
          Largest files, most connected modules, dead-code candidates, and circular dependencies.
        </p>
      </header>

      <RepoSelector repos={repos} activeRepo={activeRepo} setActiveRepo={setActiveRepo} />

      {loading && (
        <div className="text-sm font-mono text-zinc-400 flex items-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin" /> Analyzing health...
        </div>
      )}
      {err && <div className="text-sm text-red-400 font-mono">{err}</div>}

      {data && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Stat label="Files" value={data.total_files} />
            <Stat label="Dead candidates" value={data.possible_dead_code.length} accent="warning" />
            <Stat label="Circular deps" value={data.circular_dependencies.length} accent="danger" />
            <Stat label="Hot modules" value={data.most_connected.length} accent="success" />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card title="Largest files" icon={FileWarning}>
              <ul className="font-mono text-xs space-y-2" data-testid="largest-files">
                {data.largest_files.map((f, i) => (
                  <li key={i} className="flex items-center gap-3">
                    <span className="flex-1 truncate text-zinc-300">{f.file}</span>
                    <div className="w-40 h-1.5 bg-zinc-800 rounded">
                      <div
                        className="h-full bg-amber-500 rounded"
                        style={{
                          width: `${Math.min(100, (f.bytes / data.largest_files[0].bytes) * 100)}%`,
                        }}
                      />
                    </div>
                    <span className="w-16 text-right text-zinc-500">{(f.bytes / 1024).toFixed(1)}K</span>
                  </li>
                ))}
              </ul>
            </Card>

            <Card title="Most connected modules" icon={GitBranch}>
              <ul className="font-mono text-xs space-y-2" data-testid="most-connected">
                {data.most_connected.map((m, i) => (
                  <li key={i} className="flex items-center gap-3">
                    <span className="flex-1 truncate text-zinc-300">{m.file}</span>
                    <span className="text-cyan-400">{m.imports} imports</span>
                  </li>
                ))}
              </ul>
            </Card>

            <Card title="Possible dead code" icon={AlertTriangle}>
              {data.possible_dead_code.length === 0 ? (
                <div className="text-xs font-mono text-zinc-500">None detected.</div>
              ) : (
                <ul className="font-mono text-xs space-y-1" data-testid="dead-code">
                  {data.possible_dead_code.map((f, i) => (
                    <li key={i} className="text-zinc-300 truncate">
                      <span className="text-amber-500">·</span> {f}
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card title="Circular dependencies" icon={GitBranch}>
              {data.circular_dependencies.length === 0 ? (
                <div className="text-xs font-mono text-zinc-500">None detected.</div>
              ) : (
                <ul className="font-mono text-xs space-y-2" data-testid="circular-deps">
                  {data.circular_dependencies.map((c, i) => (
                    <li key={i} className="text-zinc-300">
                      <span className="text-red-400">↻</span> {c.join(" → ")}
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, accent }) {
  const color = {
    warning: "text-amber-500",
    danger: "text-red-500",
    success: "text-emerald-500",
  }[accent] || "text-zinc-100";
  return (
    <div className="p-5 border border-zinc-800 rounded-md bg-zinc-900/30">
      <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-mono mb-2">{label}</div>
      <div className={`text-3xl font-display tracking-tight ${color}`}>{value}</div>
    </div>
  );
}

function Card({ title, icon: Icon, children }) {
  return (
    <div className="border border-zinc-800 rounded-md p-5 bg-zinc-900/30">
      <h3 className="font-display text-base text-zinc-100 mb-3 flex items-center gap-2">
        <Icon className="h-4 w-4 text-cyan-400" /> {title}
      </h3>
      {children}
    </div>
  );
}
