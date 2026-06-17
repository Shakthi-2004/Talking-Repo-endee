import { useEffect, useRef, useState } from "react";
import { Github, Upload as UploadIcon, Loader2, Trash2, RefreshCw } from "lucide-react";
import { api } from "../lib/api";
import { toast } from "sonner";

export default function Upload({ repos, refresh, setActiveRepo }) {
  const [githubUrl, setGithubUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInput = useRef(null);
  const pollRef = useRef(null);

  useEffect(() => {
    const anyPending = repos.some((r) => r.status === "queued" || r.status === "indexing");
    if (anyPending) {
      pollRef.current = setInterval(refresh, 2000);
    }
    return () => pollRef.current && clearInterval(pollRef.current);
  }, [repos, refresh]);

  const submitGithub = async (e) => {
    e.preventDefault();
    if (!githubUrl.trim()) return;
    setBusy(true);
    try {
      const { data } = await api.post("/github", { url: githubUrl.trim() });
      toast.success(`Cloning ${data.name} — Endee is indexing.`);
      setGithubUrl("");
      setActiveRepo(data.id);
      refresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to clone repository.");
    } finally {
      setBusy(false);
    }
  };

  const submitZip = async (file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".zip")) {
      toast.error("Only .zip uploads are supported.");
      return;
    }
    setBusy(true);
    const form = new FormData();
    form.append("file", file);
    try {
      const { data } = await api.post("/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(`Uploaded ${data.name}. Indexing started.`);
      setActiveRepo(data.id);
      refresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Upload failed.");
    } finally {
      setBusy(false);
    }
  };

  const removeRepo = async (id) => {
    if (!window.confirm("Delete repository and its embeddings?")) return;
    try {
      await api.delete(`/repositories/${id}`);
      toast.success("Repository removed.");
      refresh();
    } catch (e) {
      toast.error("Delete failed.");
    }
  };

  const reindex = async (id) => {
    try {
      await api.post(`/index/${id}`);
      toast.success("Re-indexing triggered.");
      refresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Re-index failed.");
    }
  };

  return (
    <div className="space-y-8 fade-in" data-testid="page-upload">
      <header className="border-b border-zinc-800 pb-6">
        <div className="text-xs font-mono uppercase tracking-widest text-zinc-500 mb-2">
          repositories
        </div>
        <h1 className="font-display text-3xl text-zinc-100">Add a codebase</h1>
        <p className="text-sm text-zinc-400 mt-2">
          Drop in a ZIP archive or paste a public GitHub URL. We'll chunk by class &amp; function,
          embed with all-MiniLM-L6-v2, and upsert into Endee.
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <form
          onSubmit={submitGithub}
          className="border border-zinc-800 rounded-md p-6 bg-zinc-900/30 space-y-4"
          data-testid="github-form"
        >
          <div className="flex items-center gap-2">
            <Github className="h-4 w-4 text-cyan-400" />
            <span className="text-sm font-mono text-zinc-300">GitHub URL</span>
          </div>
          <input
            type="url"
            placeholder="https://github.com/owner/repo"
            value={githubUrl}
            onChange={(e) => setGithubUrl(e.target.value)}
            className="w-full bg-black border border-zinc-800 focus:border-zinc-600 outline-none rounded-md px-3 py-2 text-sm font-mono text-zinc-200 placeholder:text-zinc-600"
            data-testid="github-url-input"
            required
          />
          <button
            type="submit"
            disabled={busy}
            className="w-full inline-flex items-center justify-center gap-2 bg-zinc-100 text-zinc-900 hover:bg-white disabled:opacity-60 px-4 py-2 rounded-md text-sm font-medium transition-colors"
            data-testid="github-submit-btn"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Github className="h-4 w-4" />}
            Clone &amp; index
          </button>
          <p className="text-xs text-zinc-500 font-mono">
            Public repos only. PAT support is wired in architecture for a future iteration.
          </p>
        </form>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            const f = e.dataTransfer.files?.[0];
            if (f) submitZip(f);
          }}
          className={`border border-dashed rounded-md p-6 bg-zinc-900/30 flex flex-col items-center justify-center text-center transition-colors ${
            dragOver ? "border-cyan-500/60 bg-cyan-500/5" : "border-zinc-800"
          }`}
          data-testid="zip-dropzone"
        >
          <UploadIcon className="h-6 w-6 text-zinc-500 mb-3" />
          <div className="font-display text-base text-zinc-100">Drop a .zip here</div>
          <div className="text-xs text-zinc-500 font-mono mt-1">
            or click to browse — node_modules, .git, dist, build are auto-ignored
          </div>
          <input
            ref={fileInput}
            type="file"
            accept=".zip"
            onChange={(e) => submitZip(e.target.files?.[0])}
            className="hidden"
            data-testid="zip-file-input"
          />
          <button
            type="button"
            onClick={() => fileInput.current?.click()}
            disabled={busy}
            className="mt-4 inline-flex items-center gap-2 border border-zinc-700 hover:border-zinc-500 text-zinc-100 px-4 py-2 rounded-md text-sm font-medium transition-colors"
            data-testid="zip-browse-btn"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <UploadIcon className="h-4 w-4" />}
            Browse files
          </button>
        </div>
      </div>

      <section>
        <h2 className="font-display text-xl text-zinc-100 mb-4">Indexed repositories</h2>
        {repos.length === 0 ? (
          <div
            className="border border-dashed border-zinc-800 rounded-md p-10 text-center text-sm font-mono text-zinc-500"
            data-testid="empty-repos"
          >
            No repositories yet. Add one above.
          </div>
        ) : (
          <ul className="space-y-3" data-testid="repo-list">
            {repos.map((r) => (
              <li
                key={r.id}
                className="border border-zinc-800 rounded-md p-4 bg-zinc-900/30 hover:border-zinc-700 transition-colors"
                data-testid={`repo-row-${r.id}`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <StatusDot status={r.status} />
                      <div className="font-display text-base text-zinc-100 truncate">{r.name}</div>
                    </div>
                    <div className="text-xs font-mono text-zinc-500 mt-1 truncate">
                      {r.url || `${r.source} • ${r.files_indexed} files • ${r.chunks_indexed} chunks`}
                    </div>
                    {r.status === "indexing" && (
                      <div className="mt-2 h-1 bg-zinc-800 rounded">
                        <div
                          className="h-full bg-cyan-500 rounded"
                          style={{ width: `${Math.round((r.progress || 0) * 100)}%` }}
                        />
                      </div>
                    )}
                    {r.error && (
                      <div className="text-xs font-mono text-red-400 mt-2 truncate">{r.error}</div>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => {
                        setActiveRepo(r.id);
                        toast.success(`Active: ${r.name}`);
                      }}
                      data-testid={`repo-activate-${r.id}`}
                      className="text-xs font-mono px-2 py-1 border border-zinc-700 hover:border-zinc-500 rounded text-zinc-200"
                    >
                      Use
                    </button>
                    <button
                      onClick={() => reindex(r.id)}
                      data-testid={`repo-reindex-${r.id}`}
                      className="text-zinc-400 hover:text-zinc-100 p-1.5 rounded"
                      title="Re-index"
                    >
                      <RefreshCw className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => removeRepo(r.id)}
                      data-testid={`repo-delete-${r.id}`}
                      className="text-zinc-400 hover:text-red-400 p-1.5 rounded"
                      title="Delete"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function StatusDot({ status }) {
  const map = {
    ready: ["bg-emerald-500", "ready"],
    failed: ["bg-red-500", "failed"],
    indexing: ["bg-amber-500 animate-pulse", "indexing"],
    queued: ["bg-zinc-500 animate-pulse", "queued"],
  };
  const [cls, label] = map[status] || ["bg-zinc-500", status];
  return (
    <span className="inline-flex items-center gap-2">
      <span className={`h-2 w-2 rounded-full ${cls}`} />
      <span className="text-[10px] font-mono uppercase tracking-widest text-zinc-500">{label}</span>
    </span>
  );
}
