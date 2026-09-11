import { Navigate, Route, Routes } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import ReposPage from "./pages/ReposPage";
import RepoDetailPage from "./pages/RepoDetailPage";
import ProtectedRoute from "./components/ProtectedRoute";
import Sidebar from "./components/Sidebar";
import { useAuth } from "./context/AuthContext";

function AuthenticatedLayout({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  if (!user) return <>{children}</>;
  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "#070b14" }}>
      <Sidebar />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, overflowX: "hidden" }}>
        {children}
      </div>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/repos"
        element={
          <ProtectedRoute>
            <AuthenticatedLayout>
              <ReposPage />
            </AuthenticatedLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/repos/:id"
        element={
          <ProtectedRoute>
            <AuthenticatedLayout>
              <RepoDetailPage />
            </AuthenticatedLayout>
          </ProtectedRoute>
        }
      />
      {/* Fallback: redirect root to /repos */}
      <Route path="*" element={<Navigate to="/repos" replace />} />
    </Routes>
  );
}
