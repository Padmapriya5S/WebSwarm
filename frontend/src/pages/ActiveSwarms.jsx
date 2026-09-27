import { useEffect, useState, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { Terminal, Globe, AlertTriangle, CheckCircle, Loader2, Bug, Play, Shield, Navigation, Eye, FileText, MonitorPlay, Power, Lock } from 'lucide-react';

const AGENT_ICONS = {
  Planner: Play,
  Navigation: Navigation,
  Functional: Lock,
  Chaos: Power,
  Vision: Eye,
  Validation: Shield,
  Report: FileText
};

const AGENT_COLORS = {
  Planner: 'text-purple-400',
  Navigation: 'text-blue-400',
  Functional: 'text-teal-400',
  Chaos: 'text-orange-400',
  Validation: 'text-emerald-400',
  Report: 'text-amber-400',
  System: 'text-slate-400'
};

export default function ActiveSwarms() {
  const location = useLocation();
  const [logs, setLogs] = useState([]);
  const [wsStatus, setWsStatus] = useState('connecting'); // connecting, connected, error, done
  const [agents, setAgents] = useState({
    Planner: 'Idle',
    Navigation: 'Idle',
    Functional: 'Idle',
    Chaos: 'Idle',
    Validation: 'Idle',
    Report: 'Idle'
  });
  const [telemetry, setTelemetry] = useState({});
  const [liveBugs, setLiveBugs] = useState([]);
  const [latestScreenshot, setLatestScreenshot] = useState(null);
  const [autoScroll, setAutoScroll] = useState(true);
  
  const logsEndRef = useRef(null);
  const wsRef = useRef(null);

  useEffect(() => {
    if (autoScroll) {
      logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, autoScroll]);

  useEffect(() => {
    const data = location.state;
    if (!data || !data.testId) {
      setWsStatus('error');
      addLog('System', '[SYSTEM] No active test session found. Please start a test from the Dashboard.');
      return;
    }

    const ws = new WebSocket(`ws://localhost:8000/api/v1/ws/live-testing/${data.testId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsStatus('connected');
      ws.send(JSON.stringify({ action: 'start', targetUrl: data.targetUrl, testingGoal: data.testingGoal }));
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      
      if (msg.type === 'log') {
        addLog(msg.agent, msg.message);
      } else if (msg.type === 'status') {
        setAgents(prev => ({ ...prev, [msg.agent]: msg.status }));
      } else if (msg.type === 'telemetry') {
        setTelemetry(prev => ({ ...prev, [msg.agent]: msg.metrics }));
      } else if (msg.type === 'bug') {
        setLiveBugs(prev => [...prev, msg.data]);
      } else if (msg.type === 'screenshot') {
        setLatestScreenshot(msg.data);
      } else if (msg.type === 'finish') {
        setWsStatus('done');
      }
    };

    ws.onerror = () => {
      setWsStatus('error');
      addLog('System', '[SYSTEM] WebSocket Connection Error. Ensure backend is running.');
    };

    ws.onclose = () => {
      if (wsStatus !== 'done') setWsStatus('error');
    };

    return () => ws.close();
    // eslint-disable-next-line
  }, [location]);

  const addLog = (agent, msg) => {
    setLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), agent, msg }]);
  };

  const getAgentColor = (status) => {
    if (status === 'Running') return 'bg-blue-100 text-blue-700 border-blue-300';
    if (status === 'Completed') return 'bg-green-100 text-green-700 border-green-300';
    if (status === 'Error') return 'bg-red-100 text-red-700 border-red-300';
    return 'bg-slate-50 text-slate-500 border-slate-200';
  };

  return (
    <div className="max-w-[1600px] mx-auto p-6 lg:p-8 h-full min-h-screen flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-6 shrink-0">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Live Execution Engine</h1>
          <p className="text-slate-500 mt-1">Real-time telemetry streaming from WebSocket backend.</p>
        </div>
        
        {wsStatus === 'connected' && (
          <div className="flex items-center gap-3 px-4 py-2 bg-blue-50 text-blue-700 rounded-full border border-blue-200 shadow-sm">
            <Loader2 className="w-5 h-5 animate-spin" />
            <span className="font-semibold text-sm uppercase tracking-wide">Live Stream Active</span>
            <div className="w-3 h-3 bg-blue-500 rounded-full animate-pulse ml-1"></div>
          </div>
        )}
        
        {wsStatus === 'done' && (
          <div className="flex items-center gap-2 px-4 py-2 bg-green-50 text-green-700 rounded-full border border-green-200">
            <CheckCircle className="w-5 h-5" />
            <span className="font-semibold text-sm uppercase tracking-wide">Execution Complete</span>
          </div>
        )}

        {wsStatus === 'error' && (
          <div className="flex items-center gap-2 px-4 py-2 bg-red-50 text-red-700 rounded-full border border-red-200">
            <AlertTriangle className="w-5 h-5" />
            <span className="font-semibold text-sm uppercase tracking-wide">Connection Lost</span>
          </div>
        )}
      </div>

      {/* Main Layout Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 flex-1 min-h-0">
        
        {/* Left Column (Span 3): Banner + Terminal */}
        <div className="lg:col-span-3 flex flex-col gap-6">
          
          {/* Embedded Live Visual Browser Viewer */}
          <div className="bg-slate-950 rounded-2xl shadow-xl overflow-hidden border border-slate-800 flex flex-col shrink-0" style={{ minHeight: '400px' }}>
            <div className="bg-[#1e293b] p-3 flex items-center gap-3 border-b border-slate-700">
              <div className="flex gap-1.5 ml-2">
                <div className="w-3 h-3 rounded-full bg-red-400/80"></div>
                <div className="w-3 h-3 rounded-full bg-amber-400/80"></div>
                <div className="w-3 h-3 rounded-full bg-green-400/80"></div>
              </div>
              <div className="bg-slate-900/50 text-slate-400 text-xs px-4 py-1.5 rounded-md w-full max-w-xl mx-auto truncate font-mono border border-slate-800 flex items-center gap-2">
                <Lock className="w-3 h-3 text-slate-500" />
                {location.state?.targetUrl || "Awaiting target..."}
              </div>
            </div>
            
            <div className="flex-1 flex items-center justify-center bg-slate-900 relative">
              {latestScreenshot ? (
                <img src={`data:image/jpeg;base64,${latestScreenshot}`} alt="Live Execution Stream" className="w-full h-full object-contain" />
              ) : (
                <div className="flex flex-col items-center justify-center text-slate-500 animate-pulse">
                  <MonitorPlay className="w-12 h-12 mb-3 opacity-40" />
                  <span className="font-medium text-sm">
                    {wsStatus === 'done' ? 'Execution Finished' : 'Establishing visual stream...'}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Real-time Log Terminal */}
          <div className="bg-[#0f172a] rounded-2xl shadow-xl overflow-hidden flex flex-col border border-slate-800 h-[500px]">
            <div className="bg-[#1e293b] border-b border-slate-700 px-4 py-3 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-3">
                <Terminal className="w-5 h-5 text-slate-400" />
                <span className="font-mono text-slate-300 text-sm font-semibold">Live Developer Console</span>
              </div>
              
              <button 
                onClick={() => setAutoScroll(!autoScroll)}
                className={`text-xs font-mono px-3 py-1.5 rounded transition-colors border ${
                  autoScroll ? 'bg-blue-900/40 text-blue-400 border-blue-800/50 hover:bg-blue-900/60' : 'bg-slate-800 text-slate-500 border-slate-700 hover:bg-slate-700'
                }`}
              >
                Auto-scroll: {autoScroll ? 'ON' : 'OFF'}
              </button>
            </div>
            
            <div className="flex-1 p-5 overflow-y-auto font-mono text-sm leading-relaxed scroll-smooth">
              {logs.length === 0 ? (
                <div className="flex items-center justify-center h-full text-slate-600 italic">
                  Waiting for LangGraph stream...
                </div>
              ) : (
                <div className="space-y-2">
                  {logs.map((log, i) => {
                    const agentColor = AGENT_COLORS[log.agent] || AGENT_COLORS['System'];
                    
                    return (
                      <div key={i} className="flex flex-col sm:flex-row gap-2 sm:gap-4 hover:bg-slate-800/30 p-1 rounded transition-colors break-words">
                        <span className="text-slate-500 shrink-0 w-[100px]">[{log.time}]</span>
                        <span className={`font-bold shrink-0 w-[120px] ${agentColor}`}>[{log.agent}]</span>
                        <span className={`${
                          log.msg.includes('[ERROR]') || log.msg.includes('[ALERT]') ? 'text-red-400' :
                          log.msg.includes('[WARNING]') ? 'text-yellow-400' :
                          'text-slate-300'
                        } flex-1 whitespace-pre-wrap`}>
                          {log.msg}
                        </span>
                      </div>
                    );
                  })}
                  <div ref={logsEndRef} className="h-4" />
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right Column (Span 1): Agents Grid & Bugs */}
        <div className="flex flex-col gap-6 lg:sticky lg:top-8 h-fit">
          
          {/* Agent Activity Sidebar */}
          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
            <div className="bg-slate-50 border-b border-slate-100 px-5 py-4">
              <h3 className="font-bold text-slate-800 text-sm uppercase tracking-wide flex items-center gap-2">
                <Globe className="w-4 h-4 text-blue-500" />
                Agent Metrics & Telemetry
              </h3>
            </div>
            <div className="p-5 flex flex-col gap-3">
              {Object.entries(agents).map(([agentName, status]) => {
                const Icon = AGENT_ICONS[agentName] || Globe;
                const isRunning = status === 'Running';
                const t = telemetry[agentName];
                
                return (
                  <div key={agentName} className={`p-3 rounded-xl border flex flex-col transition-all duration-300 ${getAgentColor(status)}`}>
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-3">
                        <Icon className={`w-5 h-5 ${isRunning ? 'animate-pulse' : ''}`} />
                        <span className="font-bold text-sm">{agentName}</span>
                      </div>
                      <span className="text-xs font-semibold bg-white/60 px-2 py-1 rounded shadow-sm">
                        {status}
                      </span>
                    </div>

                    {t && (
                      <div className="mt-2 space-y-2">
                        {t.confidence_score !== undefined && (
                          <div>
                            <div className="flex justify-between text-[10px] uppercase font-bold text-slate-600 mb-1">
                              <span>Confidence</span>
                              <span>{(t.confidence_score * 100).toFixed(1)}%</span>
                            </div>
                            <div className="h-1.5 w-full bg-white rounded-full overflow-hidden border border-black/5">
                              <div className="h-full bg-indigo-500 rounded-full transition-all duration-500" style={{ width: `${t.confidence_score * 100}%` }}></div>
                            </div>
                          </div>
                        )}
                        <div className="flex justify-between items-center bg-white/60 border border-black/5 rounded-md p-1.5 px-2">
                          <span className="text-[10px] text-slate-600 font-mono">Time: {t.execution_time_ms}ms</span>
                          {t.tokens_consumed > 0 && (
                            <span className="text-[10px] text-blue-700 font-mono font-bold bg-blue-100 px-1.5 py-0.5 rounded">Tok: {t.tokens_consumed}</span>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Real-time Bug Counter */}
          {liveBugs.length > 0 && (
            <div className="bg-red-50 rounded-2xl border border-red-200 p-5 shadow-sm animate-in fade-in slide-in-from-bottom-4">
              <h3 className="text-red-800 font-bold flex items-center gap-2 mb-4 text-sm uppercase tracking-wide">
                <Bug className="w-5 h-5" />
                Live Detections ({liveBugs.length})
              </h3>
              <div className="space-y-3 max-h-[300px] overflow-y-auto pr-1">
                {liveBugs.map((bug, i) => (
                  <div key={i} className="bg-white p-3 rounded-xl border border-red-100 shadow-sm flex flex-col gap-2">
                    <div className="flex justify-between items-start gap-2">
                      <span className="bg-red-100 text-red-700 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider">
                        {bug.severity}
                      </span>
                      <span className="text-xs font-mono text-slate-400">{bug.agent}</span>
                    </div>
                    <p className="text-sm text-slate-700 font-medium leading-snug">{bug.description}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
          
        </div>
      </div>
    </div>
  );
}
