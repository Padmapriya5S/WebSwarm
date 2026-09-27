import { useState, useEffect } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Legend } from 'recharts';
import { TrendingUp, TrendingDown, Target, Activity, ShieldAlert, Zap, Globe } from 'lucide-react';

export default function History() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedUrl, setSelectedUrl] = useState('');
  const [availableUrls, setAvailableUrls] = useState([]);

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const user = JSON.parse(localStorage.getItem('user'));
        const userId = user ? user.id : 1; // Fallback to 1 if not strictly logged in for demo
        
        let fetchUrl = `http://localhost:8000/api/v1/history?user_id=${userId}`;
        if (selectedUrl) {
          fetchUrl += `&url=${encodeURIComponent(selectedUrl)}`;
        }
        
        const res = await fetch(fetchUrl);
        const data = await res.json();
        
        // Format for Recharts
        const chartData = data.map((run, i) => ({
          name: `Run #${i + 1}`,
          bugs: run.metrics.total_bugs,
          high: run.metrics.high,
          medium: run.metrics.medium,
          low: run.metrics.low,
          delta: run.metrics.delta,
          confidence: Math.round(run.metrics.avg_confidence * 100),
          time: run.execution_time_ms,
          target: run.target_url
        }));
        
        setHistory(chartData);
        
        // Extract unique URLs if we haven't selected one yet
        if (!selectedUrl && data.length > 0) {
          const urls = [...new Set(data.map(run => run.target_url))];
          setAvailableUrls(urls);
          setSelectedUrl(urls[0]); // Auto-select the first URL
        }
        
      } catch (error) {
        console.error('Failed to fetch history', error);
      } finally {
        setLoading(false);
      }
    };
    fetchHistory();
  }, [selectedUrl]);

  if (loading) {
    return (
      <div className="flex justify-center p-24">
        <div className="w-10 h-10 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin"></div>
      </div>
    );
  }

  if (history.length === 0 && availableUrls.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-24 text-slate-400">
        <Activity className="w-16 h-16 mb-4 opacity-50" />
        <h2 className="text-xl font-bold">No History Found</h2>
        <p>Run some swarm tests to generate regression data.</p>
      </div>
    );
  }

  const latest = history.length > 0 ? history[history.length - 1] : { delta: 0, target: '' };
  const deltaColor = latest.delta > 0 ? 'text-red-500' : latest.delta < 0 ? 'text-emerald-500' : 'text-slate-500';

  return (
    <div className="max-w-7xl mx-auto p-8">
      {/* Header & URL Selector */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end mb-10 gap-6">
        <div>
          <h1 className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-violet-600 to-indigo-600 flex items-center gap-4">
            <TrendingUp className="w-10 h-10 text-violet-600" />
            Regression Analytics
          </h1>
          <p className="text-slate-500 mt-2 text-lg">AI-powered historical test tracking and vulnerability trends.</p>
        </div>
        
        {availableUrls.length > 0 && (
          <div className="flex items-center gap-3 bg-white p-2 rounded-2xl shadow-sm border border-slate-200">
            <Globe className="w-5 h-5 text-slate-400 ml-2" />
            <select 
              value={selectedUrl}
              onChange={(e) => setSelectedUrl(e.target.value)}
              className="bg-transparent border-none text-slate-700 font-semibold focus:ring-0 cursor-pointer pr-8 outline-none"
            >
              {availableUrls.map(url => (
                <option key={url} value={url}>{url}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {history.length === 0 ? (
        <div className="flex flex-col items-center justify-center p-24 text-slate-400 bg-white rounded-3xl border border-slate-200 shadow-sm mb-10">
          <Target className="w-16 h-16 mb-4 opacity-50 text-indigo-400" />
          <h2 className="text-xl font-bold">No data for this URL</h2>
        </div>
      ) : (
        <>
          {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-10">
        <div className="bg-white/80 backdrop-blur-xl p-6 rounded-3xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-white flex flex-col relative overflow-hidden group">
          <div className="absolute -right-6 -top-6 w-24 h-24 bg-violet-100 rounded-full blur-2xl group-hover:bg-violet-200 transition-colors"></div>
          <span className="text-slate-500 font-bold uppercase tracking-wider text-xs mb-2 relative z-10 flex items-center gap-2">
            <Target className="w-4 h-4"/> Total Runs
          </span>
          <span className="text-4xl font-black text-slate-800 relative z-10">{history.length}</span>
        </div>
        
        <div className="bg-white/80 backdrop-blur-xl p-6 rounded-3xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-white flex flex-col relative overflow-hidden group">
          <div className="absolute -right-6 -top-6 w-24 h-24 bg-indigo-100 rounded-full blur-2xl group-hover:bg-indigo-200 transition-colors"></div>
          <span className="text-slate-500 font-bold uppercase tracking-wider text-xs mb-2 relative z-10 flex items-center gap-2">
            <ShieldAlert className="w-4 h-4"/> Latest Bug Count
          </span>
          <div className="flex items-baseline gap-3 relative z-10">
            <span className="text-4xl font-black text-slate-800">{latest.bugs}</span>
            <span className={`text-sm font-bold flex items-center ${deltaColor}`}>
              {latest.delta > 0 ? <TrendingUp className="w-4 h-4 mr-1"/> : <TrendingDown className="w-4 h-4 mr-1"/>}
              {Math.abs(latest.delta)} from last
            </span>
          </div>
        </div>

        <div className="bg-white/80 backdrop-blur-xl p-6 rounded-3xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-white flex flex-col relative overflow-hidden group">
          <div className="absolute -right-6 -top-6 w-24 h-24 bg-emerald-100 rounded-full blur-2xl group-hover:bg-emerald-200 transition-colors"></div>
          <span className="text-slate-500 font-bold uppercase tracking-wider text-xs mb-2 relative z-10 flex items-center gap-2">
            <Zap className="w-4 h-4"/> Avg Confidence
          </span>
          <span className="text-4xl font-black text-emerald-600 relative z-10">{latest.confidence}%</span>
        </div>
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        
        {/* Trend Line Chart */}
        <div className="bg-white/90 backdrop-blur-xl rounded-3xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-white p-6">
          <h3 className="text-lg font-bold text-slate-800 mb-6">Total Bug Trend (Regression)</h3>
          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={history} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorBugs" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.4}/>
                    <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{fill: '#94a3b8', fontSize: 12}} dy={10} />
                <YAxis axisLine={false} tickLine={false} tick={{fill: '#94a3b8', fontSize: 12}} />
                <Tooltip 
                  contentStyle={{ borderRadius: '16px', border: 'none', boxShadow: '0 10px 25px -5px rgb(0 0 0 / 0.1)' }}
                  itemStyle={{ fontWeight: 'bold' }}
                />
                <Area type="monotone" dataKey="bugs" stroke="#8b5cf6" strokeWidth={3} fillOpacity={1} fill="url(#colorBugs)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Severity Bar Chart */}
        <div className="bg-white/90 backdrop-blur-xl rounded-3xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-white p-6">
          <h3 className="text-lg font-bold text-slate-800 mb-6">Severity Breakdown Over Time</h3>
          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={history} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{fill: '#94a3b8', fontSize: 12}} dy={10} />
                <YAxis axisLine={false} tickLine={false} tick={{fill: '#94a3b8', fontSize: 12}} />
                <Tooltip 
                  cursor={{fill: '#f8fafc'}}
                  contentStyle={{ borderRadius: '16px', border: 'none', boxShadow: '0 10px 25px -5px rgb(0 0 0 / 0.1)' }}
                />
                <Legend iconType="circle" wrapperStyle={{ paddingTop: '20px', fontSize: '12px' }}/>
                <Bar dataKey="high" name="High Priority" stackId="a" fill="#ef4444" radius={[0, 0, 4, 4]} />
                <Bar dataKey="medium" name="Medium Priority" stackId="a" fill="#f59e0b" />
                <Bar dataKey="low" name="Low Priority" stackId="a" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

      </div>
      </>
      )}
    </div>
  );
}
