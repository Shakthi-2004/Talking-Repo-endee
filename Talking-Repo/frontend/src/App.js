import { useEffect, useState, useCallback } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";

import Sidebar from "@/components/app/Sidebar";
import Overview from "@/pages/Overview";
import UploadPage from "@/pages/Upload";
import SearchPage from "@/pages/Search";
import ChatPage from "@/pages/Chat";
import ArchitecturePage from "@/pages/Architecture";
import HealthPage from "@/pages/Health";
import { api } from "@/lib/api";
import "@/index.css";

export default function App() {
  const [repos, setRepos] = useState([]);
  const [activeRepo, setActiveRepo] = useState(null);
  const [vectorStore, setVectorStore] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get("/repositories");
      setRepos(data || []);
      if (!activeRepo) {
        const ready = (data || []).find((r) => r.status === "ready") || (data || [])[0];
        if (ready) setActiveRepo(ready.id);
      }
    } catch (e) {
      // silent
    }
  }, [activeRepo]);

  useEffect(() => {
    refresh();
    api
      .get("/vectorstore")
      .then((r) => setVectorStore(r.data))
      .catch(() => {});
  }, [refresh]);

  return (
    <BrowserRouter>
      <Toaster
        theme="dark"
        position="top-right"
        toastOptions={{
          style: { background: "#09090b", border: "1px solid #27272a", color: "#f4f4f5" },
        }}
      />
      <div className="flex h-screen w-screen overflow-hidden bg-zinc-950 text-zinc-100">
        <Sidebar repos={repos} active={activeRepo} />
        <main className="flex-1 overflow-y-auto p-8 lg:p-10 dotted-bg" data-testid="main-content">
          <Routes>
            <Route
              path="/"
              element={<Overview repos={repos} vectorStore={vectorStore} />}
            />
            <Route
              path="/upload"
              element={
                <UploadPage repos={repos} refresh={refresh} setActiveRepo={setActiveRepo} />
              }
            />
            <Route
              path="/search"
              element={
                <SearchPage
                  repos={repos}
                  activeRepo={activeRepo}
                  setActiveRepo={setActiveRepo}
                />
              }
            />
            <Route
              path="/chat"
              element={
                <ChatPage
                  repos={repos}
                  activeRepo={activeRepo}
                  setActiveRepo={setActiveRepo}
                />
              }
            />
            <Route
              path="/architecture"
              element={
                <ArchitecturePage
                  repos={repos}
                  activeRepo={activeRepo}
                  setActiveRepo={setActiveRepo}
                />
              }
            />
            <Route
              path="/health"
              element={
                <HealthPage
                  repos={repos}
                  activeRepo={activeRepo}
                  setActiveRepo={setActiveRepo}
                />
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
