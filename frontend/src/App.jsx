import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';
import { Activity, FileText, PlusCircle, Hexagon, Bug, LogOut, Eye, TrendingUp } from 'lucide-react';
import Dashboard from './pages/Dashboard';
import ActiveSwarms from './pages/ActiveSwarms';
import Reports from './pages/Reports';
import Bugs from './pages/Bugs';
import Vision from './pages/Vision';
import History from './pages/History';
import Auth from './pages/Auth';

function Sidebar() {
  const location = useLocation();
  if (location.pathname === '/') return null; 

  const links = [
    { to: '/dashboard', icon: PlusCircle, label: 'New Test' },
    { to: '/live-testing', icon: Activity, label: 'Active Swarms' },
    { to: '/history', icon: TrendingUp, label: 'Regression Analytics' },
    { to: '/bugs', icon: Bug, label: 'Bug Tracker' },
    { to: '/vision', icon: Eye, label: 'Vision Diffs' },
    { to: '/reports', icon: FileText, label: 'Reports' },
  ];

  return (
    <div className="w-64 bg-gradient-to-b from-indigo-950 via-violet-950 to-indigo-950 text-white min-h-screen flex flex-col shadow-2xl shrink-0 border-r border-white/5">
      <div className="p-6 flex items-center gap-3 border-b border-white/10 bg-white/5 backdrop-blur-md">
        <div className="relative">
          <div className="absolute inset-0 bg-cyan-400 blur-md opacity-50 rounded-full"></div>
          <Hexagon className="w-8 h-8 text-cyan-300 fill-cyan-400/30 relative z-10" />
        </div>
        <h1 className="text-xl font-extrabold tracking-wider bg-clip-text text-transparent bg-gradient-to-r from-white to-cyan-200">WebSwarm</h1>
      </div>
      <nav className="flex-1 px-4 pt-6 space-y-2">
        {links.map((link) => {
          const isActive = location.pathname === link.to;
          return (
            <Link
              key={link.to}
              to={link.to}
              className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-300 ${
                isActive 
                  ? 'bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-[0_0_15px_rgba(6,182,212,0.4)] font-bold' 
                  : 'text-indigo-200 hover:bg-white/10 hover:text-white'
              }`}
            >
              <link.icon className="w-5 h-5" />
              <span>{link.label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="p-4 border-t border-slate-800">
        <Link to="/" onClick={() => localStorage.removeItem('webswarm_user')} className="flex items-center gap-3 px-4 py-3 rounded-lg text-slate-400 hover:text-white hover:bg-red-500/10 transition-colors">
          <LogOut className="w-5 h-5" />
          <span className="font-medium">Sign Out</span>
        </Link>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex min-h-screen bg-slate-50 font-sans">
        <Sidebar />
        <main className="flex-1 overflow-auto h-screen relative">
          <Routes>
            <Route path="/" element={<Auth />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/live-testing" element={<ActiveSwarms />} />
            <Route path="/history" element={<History />} />
            <Route path="/bugs" element={<Bugs />} />
            <Route path="/vision" element={<Vision />} />
            <Route path="/reports" element={<Reports />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
