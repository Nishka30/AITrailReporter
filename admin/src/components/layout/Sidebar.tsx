import {
  ClipboardCheck,
  Compass,
  HelpCircle,
  LayoutDashboard,
  LogOut,
  MapPin,
  Users,
} from 'lucide-react';
import { NavLink } from 'react-router-dom';

import { useAdminAuth } from '../../auth/AdminAuthContext';

const NAV_ITEMS = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/review-queue', label: 'Review Queue', icon: ClipboardCheck },
  { to: '/knowledge', label: 'Knowledge', icon: Compass },
  { to: '/places', label: 'Places', icon: MapPin },
  { to: '/contributors', label: 'Contributors', icon: Users },
  { to: '/questions', label: 'Questions', icon: HelpCircle },
];

export default function Sidebar() {
  const { auth, logout } = useAdminAuth();

  return (
    <aside className="flex h-screen w-64 shrink-0 flex-col border-r border-border bg-paper-elevated">
      <div className="px-6 py-6">
        <div className="font-heading text-lg font-extrabold text-ink">Trail Reporter</div>
        <div className="text-xs font-bold uppercase tracking-wide text-marigold-deep">
          Content Console
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3">
        {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-bold transition-colors ${
                isActive ? 'bg-ink text-marigold-soft' : 'text-ink-soft hover:bg-paper-muted'
              }`
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-border px-4 py-4">
        <div className="mb-2 truncate text-xs text-ink-faint">Signed in as {auth?.name}</div>
        <button
          onClick={logout}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-bold text-ink-soft hover:bg-paper-muted"
        >
          <LogOut className="h-4 w-4" /> Sign out
        </button>
      </div>
    </aside>
  );
}
