import { LogOut, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { clearAuthSession, getAuthSession } from '../../services/api';

const titleMap = {
  '/dashboard': 'Dashboard de Recrutamento',
  '/candidatos': 'Currículos e Candidatos',
  '/pipeline': 'Pipeline de Seleção',
  '/vagas': 'Vagas',
  '/auditoria-ranking': 'Auditoria de Ranking',
  '/curriculos-banco-talentos': 'Banco de Talentos',
  '/relatorios': 'Relatórios',
  '/configuracoes': 'Configurações',
};

function Header({ isSidebarCollapsed = false, onToggleSidebar = () => {} }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const session = getAuthSession();
  const userName = session?.user?.username || 'Usuário';
  const userRole = session?.user?.role || 'admin';
  const currentTitle =
    Object.entries(titleMap).find(([key]) => pathname.startsWith(key))?.[1] || 'Recrutamento Carris';

  const handleLogout = () => {
    clearAuthSession();
    navigate('/login', { replace: true });
  };

  return (
    <header className="sticky top-0 z-20 border-b border-slatewarm-800/80 bg-slatewarm-900/90 backdrop-blur">
      <div className="mx-auto flex h-16 w-full max-w-[1440px] items-center justify-between gap-3 px-4 md:px-6 lg:px-8">
        <div>
          <h1 className="text-base font-semibold text-slatewarm-50 md:text-lg">{currentTitle}</h1>
          <p className="hidden text-xs text-slatewarm-300 md:block">Visão clara para decisões rápidas e confiáveis</p>
        </div>

        <div className="flex items-center gap-2 md:gap-3">
          <button
            onClick={onToggleSidebar}
            className="hidden h-10 w-10 items-center justify-center rounded-xl border border-slatewarm-700 text-slatewarm-200 transition hover:border-brand-500 hover:text-brand-100 lg:flex"
            title={isSidebarCollapsed ? 'Expandir menu' : 'Recolher menu'}
          >
            {isSidebarCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
          <div className="flex items-center gap-3 rounded-xl border border-slatewarm-700 bg-slatewarm-900 px-3 py-2">
            <img
              src="data:image/svg+xml;utf8,%3Csvg%20xmlns%3D'http%3A//www.w3.org/2000/svg'%20width%3D'64'%20height%3D'64'%3E%3Crect%20width%3D'64'%20height%3D'64'%20rx%3D'18'%20fill%3D'%232f9b75'/%3E%3Ctext%20x%3D'32'%20y%3D'39'%20font-size%3D'22'%20text-anchor%3D'middle'%20fill%3D'%23eef9f5'%20font-family%3D'Arial'%20font-weight%3D'700'%3EAR%3C/text%3E%3C/svg%3E"
              alt="Avatar"
              className="h-8 w-8 rounded-full border border-slatewarm-700"
            />
            <div className="hidden md:block">
              <p className="text-sm font-semibold text-slatewarm-50">{userName}</p>
              <p className="text-xs text-slatewarm-300">{userRole}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-slatewarm-700 text-slatewarm-200 transition hover:border-brand-500 hover:text-brand-100"
            title="Sair"
          >
            <LogOut size={18} />
          </button>
        </div>
      </div>
    </header>
  );
}

export default Header;
