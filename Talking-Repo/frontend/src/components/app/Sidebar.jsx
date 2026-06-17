import { NavLink } from "react-router-dom";
import { Home, Upload, Search, MessageSquare, Network, Activity, Database } from "lucide-react";

const NAV = [
  { to: "/", label: "Overview", icon: Home, testid: "nav-overview" },
  { to: "/upload", label: "Repositories", icon: Upload, testid: "nav-upload" },
  { to: "/search", label: "Code Search", icon: Search, testid: "nav-search" },
  { to: "/chat", label: "RAG Chat", icon: MessageSquare, testid: "nav-chat" },
  { to: "/architecture", label: "Architecture", icon: Network, testid: "nav-arch" },
  { to: "/health", label: "Health Report", icon: Activity, testid: "nav-health" },
];

export default function Sidebar({ repos = [], active }) {
  return (
    <aside className="w-64 shrink-0 h-screen border-r border-zinc-800 bg-zinc-950 flex flex-col">
      <div className="px-6 py-6 border-b border-zinc-800">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-md bg-zinc-100 text-zinc-900 grid place-items-center font-display font-semibold">
            E
          </div>
          <div>
            <div className="font-display text-sm font-semibold tracking-tight">
              Endee Codebase
            </div>
            <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-mono">
              vector intelligence
            </div>
          </div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1">
        {NAV.map(({ to, label, icon: Icon, testid }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            data-testid={testid}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-md text-sm font-mono transition-colors ${
                isActive
                  ? "bg-zinc-900 text-zinc-100 border border-zinc-800"
                  : "text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900/60"
              }`
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}

        <div className="mt-6 px-3">
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-mono mb-2">
            Indexed repos
          </div>
          {repos.length === 0 ? (
            <div className="text-xs font-mono text-zinc-600">— none yet —</div>
          ) : (
            <ul className="space-y-1" data-testid="sidebar-repos">
              {repos.slice(0, 8).map((r) => (
                <li
                  key={r.id}
                  className={`text-xs font-mono truncate px-2 py-1 rounded ${
                    active === r.id ? "text-cyan-400" : "text-zinc-500"
                  }`}
                  title={r.name}
                >
                  <span
                    className={`inline-block h-1.5 w-1.5 rounded-full mr-2 ${
                      r.status === "ready"
                        ? "bg-emerald-500"
                        : r.status === "failed"
                        ? "bg-red-500"
                        : "bg-amber-500 animate-pulse"
                    }`}
                  />
                  {r.name}
                </li>
              ))}
            </ul>
          )}
        </div>
      </nav>

      <div className="border-t border-zinc-800 p-4 text-[10px] font-mono text-zinc-600 flex items-center gap-2">
        <Database className="h-3 w-3" />
        Powered by Endee
      </div>
    </aside>
  );
}
