import React from 'react';
import {
  Activity,
  Cpu,
  HardDrive,
  Clock,
  ShieldCheck,
  CheckCircle,
  RefreshCw,
  Zap,
} from 'lucide-react';
import { NodeSystemInfo } from '../types/scaffold';

interface RuntimeInspectorProps {
  systemInfo: NodeSystemInfo | null;
  onRefresh: () => void;
  loading: boolean;
}

export const RuntimeInspector: React.FC<RuntimeInspectorProps> = ({ systemInfo, onRefresh, loading }) => {
  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="bg-[#0a0a0a] border border-white/10 p-8 space-y-6 relative overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-1 bg-[#ccff00]"></div>

        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
          <div>
            <div className="flex items-center space-x-2 text-xs font-mono font-bold text-[#ccff00] mb-2 uppercase tracking-widest">
              <span className="w-2 h-2 rounded-full bg-[#ccff00] shadow-[0_0_8px_#ccff00]"></span>
              <span>LIVE PROCESS TELEMETRY</span>
            </div>
            <h2 className="text-4xl sm:text-5xl font-black text-white tracking-tighter uppercase">
              RUNTIME & ENGINE INSPECTOR
            </h2>
            <p className="text-sm font-light text-white/60 mt-2 max-w-2xl leading-relaxed">
              Real-time diagnostic metrics gathered directly from the backend server process running Node.js 22 LTS with V8 Maglev compilation.
            </p>
          </div>

          <button
            onClick={onRefresh}
            disabled={loading}
            className="flex items-center space-x-2 text-xs font-mono font-bold uppercase tracking-wider bg-white/5 hover:bg-white/10 text-white px-5 py-3 border border-white/10 transition-colors shrink-0"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-[#ccff00]' : 'text-white/40'}`} />
            <span>REFRESH TELEMETRY</span>
          </button>
        </div>
      </div>

      {systemInfo ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {/* Node & V8 Version */}
          <div className="bg-[#0a0a0a] border border-white/10 p-6 flex flex-col justify-between h-[180px] relative group hover:border-white/30 transition-colors">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono uppercase tracking-widest text-white/40 font-bold">RUNTIME ENGINE</span>
              <Cpu className="w-4 h-4 text-[#ccff00]" />
            </div>
            <div>
              <div className="text-4xl font-black text-white font-mono tracking-tight">{systemInfo.nodeVersion}</div>
              <div className="text-xs font-mono text-white/60 mt-1">V8: {systemInfo.v8Version}</div>
            </div>
            <div className="text-[10px] font-mono text-white/40 pt-2 border-t border-white/10 uppercase">
              ARCH: {systemInfo.arch} • OS: {systemInfo.platform}
            </div>
          </div>

          {/* Memory Heap Used */}
          <div className="bg-[#0a0a0a] border border-white/10 p-6 flex flex-col justify-between h-[180px] relative group hover:border-white/30 transition-colors">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono uppercase tracking-widest text-white/40 font-bold">HEAP MEMORY</span>
              <HardDrive className="w-4 h-4 text-[#ccff00]" />
            </div>
            <div>
              <div className="text-4xl font-black text-[#ccff00] font-mono tracking-tight">
                {systemInfo.memory.heapUsedMb} <span className="text-sm font-normal text-white/40">MB</span>
              </div>
              <div className="text-xs font-mono text-white/60 mt-1">TOTAL HEAP: {systemInfo.memory.heapTotalMb} MB</div>
            </div>
            <div className="text-[10px] font-mono text-white/40 pt-2 border-t border-white/10 uppercase">
              RSS: {systemInfo.memory.rssMb} MB
            </div>
          </div>

          {/* Process Uptime */}
          <div className="bg-[#0a0a0a] border border-white/10 p-6 flex flex-col justify-between h-[180px] relative group hover:border-white/30 transition-colors">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono uppercase tracking-widest text-white/40 font-bold">PROCESS UPTIME</span>
              <Clock className="w-4 h-4 text-[#ccff00]" />
            </div>
            <div>
              <div className="text-4xl font-black text-white font-mono tracking-tight">
                {systemInfo.uptimeSeconds} <span className="text-sm font-normal text-white/40">SEC</span>
              </div>
              <div className="text-xs font-mono text-white/60 mt-1">PROCESS ID: {systemInfo.pid}</div>
            </div>
            <div className="text-[10px] font-mono text-white/40 pt-2 border-t border-white/10 uppercase">
              LIBUV: {systemInfo.uvVersion}
            </div>
          </div>

          {/* Security & Cryptography */}
          <div className="bg-[#0a0a0a] border border-white/10 p-6 flex flex-col justify-between h-[180px] relative group hover:border-white/30 transition-colors">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono uppercase tracking-widest text-white/40 font-bold">CRYPTO ENGINE</span>
              <ShieldCheck className="w-4 h-4 text-[#ccff00]" />
            </div>
            <div>
              <div className="text-lg font-black text-white font-mono uppercase truncate">OPENSSL {systemInfo.opensslVersion}</div>
              <div className="text-xs font-mono text-[#ccff00] mt-1">WEBCRYPTO NATIVE</div>
            </div>
            <div className="text-[10px] font-mono text-white/40 pt-2 border-t border-white/10 uppercase">
              ZLIB: {systemInfo.zlibVersion}
            </div>
          </div>
        </div>
      ) : (
        <div className="p-12 text-center bg-[#0a0a0a] border border-white/10 font-mono text-xs text-white/40 uppercase tracking-widest">
          Loading system telemetry...
        </div>
      )}

      {/* Feature Flags Status Table */}
      {systemInfo && (
        <div className="bg-[#0a0a0a] border border-white/10 p-8 space-y-6">
          <div className="flex items-center justify-between border-b border-white/10 pb-4">
            <h3 className="text-lg font-black uppercase tracking-tight text-white flex items-center gap-2">
              <Zap className="w-4 h-4 text-[#ccff00]" />
              <span>NODE 22 STANDARD CAPABILITY MATRIX</span>
            </h3>
            <span className="text-[10px] font-mono text-white/40 uppercase">
              UPDATED: {new Date(systemInfo.timestamp).toLocaleTimeString()}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {Object.entries(systemInfo.features).map(([featKey, enabled]) => (
              <div
                key={featKey}
                className="bg-[#111111] p-4 border border-white/10 flex items-center justify-between"
              >
                <div>
                  <div className="text-xs font-bold text-white font-mono uppercase">{featKey}</div>
                  <div className="text-[10px] font-mono text-white/40 uppercase">
                    {enabled ? 'NATIVE ENABLED' : 'DISABLED'}
                  </div>
                </div>
                <span className={`text-xs font-mono font-bold ${enabled ? 'text-[#ccff00]' : 'text-white/20'}`}>
                  {enabled ? '[OK]' : '[--]'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
