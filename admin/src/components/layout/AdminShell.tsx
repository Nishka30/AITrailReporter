import { Outlet } from 'react-router-dom';

import Sidebar from './Sidebar';

export default function AdminShell() {
  return (
    <div className="flex h-screen overflow-hidden bg-paper">
      <Sidebar />
      <main className="min-h-0 flex-1 overflow-y-auto px-8 py-8">
        <div className="mx-auto max-w-6xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
