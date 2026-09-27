import { useState, useEffect } from 'react';
import { Bug, AlertCircle, AlertTriangle, ShieldCheck, Filter } from 'lucide-react';

export default function Bugs() {
  const [bugs, setBugs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterSeverity, setFilterSeverity] = useState('ALL');

  useEffect(() => {
    const fetchBugs = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/v1/bugs');
        const data = await res.json();
        setBugs(data);
      } catch (error) {
        console.error('Failed to fetch bugs', error);
      } finally {
        setLoading(false);
      }
    };
    fetchBugs();
  }, []);

  const filteredBugs = filterSeverity === 'ALL' ? bugs : bugs.filter(b => b.severity === filterSeverity);

  const getSeverityBadge = (severity) => {
    switch (severity) {
      case 'HIGH':
        return <span className="flex items-center gap-1 bg-red-100 text-red-700 px-3 py-1 rounded-full text-xs font-bold"><AlertCircle className="w-3 h-3"/> High</span>;
      case 'MEDIUM':
        return <span className="flex items-center gap-1 bg-yellow-100 text-yellow-700 px-3 py-1 rounded-full text-xs font-bold"><AlertTriangle className="w-3 h-3"/> Medium</span>;
      case 'LOW':
        return <span className="flex items-center gap-1 bg-blue-100 text-blue-700 px-3 py-1 rounded-full text-xs font-bold"><ShieldCheck className="w-3 h-3"/> Low</span>;
      default:
        return <span className="bg-slate-100 text-slate-700 px-3 py-1 rounded-full text-xs font-bold">{severity}</span>;
    }
  };

  return (
    <div className="max-w-7xl mx-auto p-8">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-8 gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-900 flex items-center gap-3">
            <Bug className="w-8 h-8 text-red-500" />
            Detected Vulnerabilities
          </h1>
          <p className="text-slate-500 mt-2">All bugs found by the AI Swarm, populated directly from the local database.</p>
        </div>
        
        <div className="flex items-center gap-2 bg-white px-4 py-2 rounded-xl shadow-sm border border-slate-200">
          <Filter className="w-4 h-4 text-slate-400" />
          <select 
            className="bg-transparent text-sm font-semibold text-slate-700 outline-none"
            value={filterSeverity}
            onChange={(e) => setFilterSeverity(e.target.value)}
          >
            <option value="ALL">All Severities</option>
            <option value="HIGH">High Priority</option>
            <option value="MEDIUM">Medium Priority</option>
            <option value="LOW">Low Priority</option>
          </select>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center p-12">
          <div className="w-8 h-8 border-4 border-slate-200 border-t-blue-500 rounded-full animate-spin"></div>
        </div>
      ) : filteredBugs.length === 0 ? (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-12 text-center">
          <ShieldCheck className="w-16 h-16 text-slate-300 mx-auto mb-4" />
          <h3 className="text-xl font-bold text-slate-700">No vulnerabilities detected</h3>
          <p className="text-slate-500 mt-2">The swarm has not discovered any bugs matching your criteria.</p>
        </div>
      ) : (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 text-sm">
                <th className="p-4 font-semibold w-24">ID</th>
                <th className="p-4 font-semibold w-32">Severity</th>
                <th className="p-4 font-semibold">Description</th>
                <th className="p-4 font-semibold w-48">Agent</th>
                <th className="p-4 font-semibold w-32 text-center">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {filteredBugs.map((bug) => (
                <tr key={bug.id} className="border-b border-slate-100 hover:bg-slate-50/50 transition-colors">
                  <td className="p-4 font-mono text-sm text-slate-500">#{bug.id}</td>
                  <td className="p-4">{getSeverityBadge(bug.severity)}</td>
                  <td className="p-4">
                    <p className="text-sm font-medium text-slate-800">{bug.description}</p>
                    <p className="text-xs text-slate-400 mt-1 truncate max-w-md" title={bug.page}>{bug.page}</p>
                  </td>
                  <td className="p-4 text-sm font-mono text-slate-600">{bug.agent}</td>
                  <td className="p-4 text-center">
                    <span className="text-sm font-bold text-slate-700">
                      {Math.round((bug.confidence || 0.95) * 100)}%
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
