import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { WorkspaceProvider } from "./context/WorkspaceContext";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { Layout } from "./components/Layout";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { DataSourcesPage } from "./pages/DataSourcesPage";
import { PipelinesPage } from "./pages/PipelinesPage";
import { PipelineNewPage } from "./pages/PipelineNewPage";
import { PipelineDetailPage } from "./pages/PipelineDetailPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LineagePage } from "./pages/LineagePage";
import { ScorecardsPage } from "./pages/ScorecardsPage";

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        element={
          <ProtectedRoute>
            <WorkspaceProvider>
              <Layout />
            </WorkspaceProvider>
          </ProtectedRoute>
        }
      >
        <Route path="/datasources" element={<DataSourcesPage />} />
        <Route path="/pipelines" element={<PipelinesPage />} />
        <Route path="/pipelines/new" element={<PipelineNewPage />} />
        <Route path="/pipelines/:id" element={<PipelineDetailPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/lineage" element={<LineagePage />} />
        <Route path="/scorecards" element={<ScorecardsPage />} />
      </Route>
      <Route path="/" element={<Navigate to="/datasources" replace />} />
      <Route path="*" element={<Navigate to="/datasources" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  );
}

export default App;
