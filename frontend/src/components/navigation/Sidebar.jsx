import { BriefcaseBusiness, FileText, LayoutDashboard, ListChecks, Users2, Workflow } from 'lucide-react';
import { NavLink } from 'react-router-dom';

const navItems = [
  { label: 'Dashboard', to: '/dashboard', icon: LayoutDashboard },
  { label: 'Candidatos', to: '/candidatos', icon: Users2 },
  { label: 'Pipeline', to: '/pipeline', icon: Workflow },
  { label: 'Banco de talentos', to: '/curriculos-banco-talentos', icon: FileText },
  { label: 'Vagas', to: '/vagas', icon: BriefcaseBusiness },
  { label: 'Auditoria ranking', to: '/auditoria-ranking', icon: ListChecks },
];

function Sidebar({ collapsed = false }) {
  return (
    <aside className={`sticky top-0 hidden h-screen border-r border-slatewarm-800 bg-slatewarm-900 py-6 lg:block ${collapsed ? 'px-3' : 'px-5'}`}>
      <div className={`mb-8 flex items-center ${collapsed ? 'justify-center' : 'gap-3'}`}>
        <img src="/logo.png" alt="Logo Carris" className="h-11 w-11 rounded-full border border-slatewarm-700 bg-slatewarm-950 p-0.5 shadow-soft" />
        <div className={collapsed ? 'hidden' : ''}>
          <p className="text-sm font-semibold text-slatewarm-50">Recrutamento Carris</p>
          <p className="text-xs text-slatewarm-300">Plataforma de Seleção</p>
        </div>
      </div>

      <nav className="space-y-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                [
                  `flex items-center rounded-xl px-3 py-2.5 text-sm font-medium transition ${collapsed ? 'justify-center gap-0' : 'gap-3'}`,
                  isActive
                    ? 'subtle-ring bg-brand-900/20 text-brand-100'
                    : 'text-slatewarm-200 hover:bg-slatewarm-800 hover:text-slatewarm-50',
                ].join(' ')
              }
              title={collapsed ? item.label : undefined}
            >
              <Icon size={18} />
              <span className={collapsed ? 'hidden' : ''}>{item.label}</span>
            </NavLink>
          );
        })}
      </nav>

      <div className={`card-surface mt-8 p-4 ${collapsed ? 'hidden' : ''}`}>
        <p className="text-sm font-semibold text-slatewarm-50">Produtividade do time</p>
        <p className="mt-1 text-xs text-slatewarm-300">92% das vagas com triagem em menos de 24h.</p>
      </div>
    </aside>
  );
}

export default Sidebar;
