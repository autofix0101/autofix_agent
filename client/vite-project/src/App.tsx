import { Navigate, Route, Routes } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import ReposPage from "./pages/ReposPage";
import RepoDetailPage from "./pages/RepoDetailPage";
import ProtectedRoute from "./components/ProtectedRoute";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/repos"
        element={
          <ProtectedRoute>
            <ReposPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/repos/:id"
        element={
          <ProtectedRoute>
            <RepoDetailPage />
          </ProtectedRoute>
        }
      />
      {/* Fallback: redirect root to /repos */}
      <Route path="*" element={<Navigate to="/repos" replace />} />
    </Routes>
  );
}
