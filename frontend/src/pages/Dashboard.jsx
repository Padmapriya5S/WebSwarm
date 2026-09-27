import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Target, Flag, Zap } from 'lucide-react';

export default function Dashboard() {
  const [targetUrl, setTargetUrl] = useState('');
  const [testingGoal, setTestingGoal] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!targetUrl) return;
    setLoading(true);
    try {
      const user = JSON.parse(localStorage.getItem('user'));
      const userId = user ? user.id : null;
      
      const res = await fetch('http://localhost:8000/api/v1/start-swarm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ targetUrl, testingGoal, userId })
      });
      
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to initialize swarm');
      
      navigate('/live-testing', { 
        state: { testId: data.testId, targetUrl: data.targetUrl } 
      });
    } catch (err) {
      console.error(err);
      alert('Failed to connect to backend engine.');
      setLoading(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto p-8">
      <div className="mb-10">
        <h1 className="text-4xl font-extrabold text-slate-900 tracking-tight">Deploy New Swarm</h1>
        <p className="text-slate-500 mt-2 text-lg">Configure your agents and specify the testing objective.</p>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="p-8">
          <form onSubmit={handleSubmit} className="space-y-8">
            
            <div className="space-y-3">
              <label className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                <Target className="w-5 h-5 text-blue-500" />
                Target URL
              </label>
              <input
                type="url"
                required
                placeholder="https://example.com"
                value={targetUrl}
                onChange={(e) => setTargetUrl(e.target.value)}
                className="w-full px-4 py-3 rounded-xl border border-slate-300 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors outline-none text-slate-700 placeholder-slate-400"
              />
            </div>

            <div className="space-y-3">
              <label className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                <Flag className="w-5 h-5 text-purple-500" />
                Testing Goal (Optional)
              </label>
              <textarea
                placeholder="e.g., Test authentication flow and look for broken links on the dashboard."
                rows={4}
                value={testingGoal}
                onChange={(e) => setTestingGoal(e.target.value)}
                className="w-full px-4 py-3 rounded-xl border border-slate-300 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors outline-none text-slate-700 placeholder-slate-400 resize-none"
              />
            </div>

            <div className="pt-4 border-t border-slate-100 flex justify-end">
              <button
                type="submit"
                disabled={loading}
                className="group relative flex items-center gap-2 px-8 py-4 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-xl font-bold text-lg hover:from-blue-500 hover:to-indigo-500 transition-all shadow-[0_0_20px_rgba(79,70,229,0.4)] hover:shadow-[0_0_30px_rgba(79,70,229,0.6)] hover:-translate-y-0.5 disabled:opacity-50"
              >
                {loading ? (
                  <div className="w-6 h-6 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                ) : (
                  <Zap className="w-6 h-6 fill-white/20" />
                )}
                <span>{loading ? 'Initializing...' : 'Unleash Swarm'}</span>
                <div className="absolute inset-0 rounded-xl bg-white/20 blur opacity-0 group-hover:opacity-100 transition-opacity"></div>
              </button>
            </div>
            
          </form>
        </div>
      </div>
    </div>
  );
}
