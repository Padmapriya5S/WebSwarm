import { useState, useEffect } from 'react';
import { Eye, ArrowRight, Percent, MonitorPlay } from 'lucide-react';

export default function Vision() {
  const [diffs, setDiffs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchVisionDiffs = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/v1/vision-diffs');
        const data = await res.json();
        setDiffs(data);
      } catch (error) {
        console.error('Failed to fetch vision diffs', error);
      } finally {
        setLoading(false);
      }
    };
    fetchVisionDiffs();
  }, []);

  return (
    <div className="max-w-7xl mx-auto p-8">
      <div className="mb-10">
        <h1 className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-cyan-600 to-blue-600 flex items-center gap-4">
          <Eye className="w-10 h-10 text-cyan-500" />
          Vision Comparison Engine
        </h1>
        <p className="text-slate-500 mt-2 text-lg">Rapid layout-shift indicator from an optimized structural JPEG byte-size heuristic; this is not a pixel-level image diff.</p>
      </div>

      {loading ? (
        <div className="flex justify-center p-24">
          <div className="w-10 h-10 border-4 border-cyan-200 border-t-cyan-600 rounded-full animate-spin"></div>
        </div>
      ) : diffs.length === 0 ? (
        <div className="bg-white/80 backdrop-blur-xl rounded-3xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-white p-16 text-center">
          <MonitorPlay className="w-20 h-20 text-slate-200 mx-auto mb-6" />
          <h3 className="text-2xl font-bold text-slate-700">No vision metrics available</h3>
          <p className="text-slate-500 mt-2">Run a test swarm to generate visual baseline comparisons.</p>
        </div>
      ) : (
        <div className="space-y-8">
          {diffs.map((diff) => (
            <div key={diff.id} className="bg-white/90 backdrop-blur-xl rounded-3xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-white overflow-hidden flex flex-col">
              
              {/* Header */}
              <div className="bg-slate-50/50 border-b border-slate-100 p-6 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <div>
                  <h3 className="font-bold text-slate-800 text-sm uppercase tracking-wide">Target: {diff.page_url}</h3>
                  <p className="text-xs text-slate-500 mt-1 font-mono">Test ID: #{diff.test_id} | Timestamp: {new Date(diff.created_at).toLocaleString()}</p>
                </div>
                <div className="flex items-center gap-2 bg-gradient-to-r from-cyan-50 to-blue-50 text-blue-700 px-5 py-2.5 rounded-xl border border-cyan-100 shadow-sm">
                  <Percent className="w-4 h-4 text-cyan-600" />
                  <span className="font-bold text-sm">Variance: {diff.variance_pct.toFixed(2)}%</span>
                </div>
              </div>

              {/* Images */}
              <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-slate-800 bg-slate-900 relative">
                
                {/* Center glowing orb */}
                <div className="hidden md:flex absolute top-1/2 left-1/2 w-12 h-12 bg-gradient-to-br from-cyan-400 to-blue-500 rounded-full items-center justify-center border-4 border-slate-900 -translate-x-1/2 -translate-y-1/2 z-20 shadow-[0_0_20px_rgba(6,182,212,0.5)]">
                  <ArrowRight className="w-5 h-5 text-white" />
                </div>                <div className="p-6 flex flex-col">
                  <span className="text-slate-400 font-mono text-xs mb-3 flex items-center justify-between">
                    <span>BASELINE SNAPSHOT</span>
                  </span>
                  <div className="flex-1 rounded border border-slate-700 overflow-hidden bg-slate-950 flex items-center justify-center shadow-inner">
                    <img 
                      src={`data:image/jpeg;base64,${diff.baseline_b64}`} 
                      alt="Baseline" 
                      className="max-h-[450px] object-contain w-full"
                    />
                  </div>
                </div>

                <div className="p-6 flex flex-col relative">
                  <span className="text-slate-400 font-mono text-xs mb-3 flex items-center justify-between">
                    <span>POST-INTERACTION SNAPSHOT</span>
                  </span>
                  <div className="flex-1 rounded border border-slate-700 overflow-hidden bg-slate-950 flex items-center justify-center shadow-inner">
                    <img 
                      src={`data:image/jpeg;base64,${diff.current_b64}`} 
                      alt="Current" 
                      className="max-h-[450px] object-contain w-full"
                    />
                  </div>
                </div>
              </div>

            </div>
          ))}
        </div>
      )}
    </div>
  );
}
