import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from '../components/navigation/Sidebar';
import Header from '../components/navigation/Header';

function AppLayout() {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  return (
    <div className={`min-h-screen bg-slatewarm-900 text-slatewarm-50 lg:grid ${isSidebarCollapsed ? 'lg:grid-cols-[88px_1fr]' : 'lg:grid-cols-[280px_1fr]'}`}>
      <Sidebar collapsed={isSidebarCollapsed} />
      <div className="flex min-h-screen flex-col">
        <Header isSidebarCollapsed={isSidebarCollapsed} onToggleSidebar={() => setIsSidebarCollapsed((prev) => !prev)} />
        <main className="mx-auto w-full max-w-[1440px] flex-1 p-4 md:p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default AppLayout;
