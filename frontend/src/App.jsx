import { Navigate, Route, Routes } from 'react-router-dom';
import AppLayout from './layouts/AppLayout';
import DashboardPage from './pages/DashboardPage';
import CandidatesPage from './pages/CandidatesPage';
import CandidateDetailsPage from './pages/CandidateDetailsPage';
import PipelinePage from './pages/PipelinePage';
import PlaceholderPage from './pages/PlaceholderPage';
import JobsPage from './pages/JobsPage';
import TalentPoolResumesPage from './pages/TalentPoolResumesPage';
import RankingAuditPage from './pages/RankingAuditPage';
import LoginPage from './pages/LoginPage';
import { getAuthSession } from './services/api';

function RequireAuth({ children }) {
  const session = getAuthSession();
  if (!session?.authenticated && !session?.access_token) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<RequireAuth><AppLayout /></RequireAuth>}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="candidatos" element={<CandidatesPage />} />
        <Route path="candidatos/:candidateId" element={<CandidateDetailsPage />} />
        <Route path="pipeline" element={<PipelinePage />} />
        <Route path="vagas" element={<JobsPage />} />
        <Route path="auditoria-ranking" element={<RankingAuditPage />} />
        <Route path="curriculos" element={<Navigate to="/candidatos" replace />} />
        <Route path="curriculos-banco-talentos" element={<TalentPoolResumesPage />} />
        <Route path="revisao-manual" element={<Navigate to="/candidatos" replace />} />
        <Route path="relatorios" element={<PlaceholderPage title="Relatórios" />} />
        <Route path="configuracoes" element={<PlaceholderPage title="Configurações" />} />
      </Route>
    </Routes>
  );
}

export default App;
