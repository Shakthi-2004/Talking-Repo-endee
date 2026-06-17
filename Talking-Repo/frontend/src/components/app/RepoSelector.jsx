import { useState } from "react";
import { ChevronDown } from "lucide-react";

export default function RepoSelector({ repos, activeRepo, setActiveRepo }) {
  const [open, setOpen] = useState(false);
  const current = repos.find((r) => r.id === activeRepo);
  const ready = repos.filter((r) => r.status === "ready");

  return (
    <div className="relative inline-block" data-testid="repo-selector">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-2 border border-zinc-800 hover:border-zinc-600 bg-zinc-900/50 px-3 py-2 rounded-md text-sm font-mono text-zinc-200"
        data-testid="repo-selector-btn"
      >
        <span className="text-[10px] uppercase tracking-widest text-zinc-500">repo</span>
        <span className="truncate max-w-[260px]">
          {current ? current.name : "Select a repository"}
        </span>
        <ChevronDown className="h-3 w-3 text-zinc-500" />
      </button>
      {open && (
        <div
          className="absolute z-30 mt-1 w-80 border border-zinc-800 bg-zinc-950 rounded-md overflow-hidden shadow-2xl"
          data-testid="repo-selector-dropdown"
        >
          {repos.length === 0 ? (
            <div className="text-xs font-mono text-zinc-500 p-3">No repositories yet.</div>
          ) : (
            <ul className="max-h-72 overflow-y-auto">
              {repos.map((r) => (
                <li
                  key={r.id}
                  onClick={() => {
                    setActiveRepo(r.id);
                    setOpen(false);
                  }}
                  className={`px-3 py-2 text-sm font-mono cursor-pointer flex items-center gap-2 hover:bg-zinc-900 ${
                    activeRepo === r.id ? "text-cyan-400" : "text-zinc-200"
                  }`}
                  data-testid={`repo-option-${r.id}`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      r.status === "ready"
                        ? "bg-emerald-500"
                        : r.status === "failed"
                        ? "bg-red-500"
                        : "bg-amber-500 animate-pulse"
                    }`}
                  />
                  <span className="truncate flex-1">{r.name}</span>
                  <span className="text-[10px] text-zinc-500">{r.status}</span>
                </li>
              ))}
            </ul>
          )}
          {ready.length === 0 && repos.length > 0 && (
            <div className="text-xs font-mono text-zinc-500 p-3 border-t border-zinc-800">
              Wait until at least one repo is "ready".
            </div>
          )}
        </div>
      )}
    </div>
  );
}
