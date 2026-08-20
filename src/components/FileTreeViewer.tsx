import React, { useState } from 'react';
import {
  FileCode,
  FileJson,
  FileText,
  Copy,
  Check,
  Download,
  Search,
  Folder,
  Terminal,
} from 'lucide-react';
import { ProjectFile } from '../types/scaffold';

interface FileTreeViewerProps {
  files: ProjectFile[];
  projectName: string;
  onDownloadZip: () => void;
}

export const FileTreeViewer: React.FC<FileTreeViewerProps> = ({ files, projectName, onDownloadZip }) => {
  const [selectedFile, setSelectedFile] = useState<ProjectFile>(files[0] || null);
  const [searchFilter, setSearchFilter] = useState('');
  const [copied, setCopied] = useState(false);

  // Keep selected file in sync if files array changes
  React.useEffect(() => {
    if (files.length > 0 && (!selectedFile || !files.some(f => f.path === selectedFile.path))) {
      setSelectedFile(files[0]);
    }
  }, [files]);

  const filteredFiles = files.filter(f =>
    f.path.toLowerCase().includes(searchFilter.toLowerCase())
  );

  const handleCopyCode = () => {
    if (!selectedFile) return;
    navigator.clipboard.writeText(selectedFile.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadSingleFile = () => {
    if (!selectedFile) return;
    const blob = new Blob([selectedFile.content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = selectedFile.path.split('/').pop() || 'file.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const getFileIcon = (path: string) => {
    if (path.endsWith('.json')) return <FileJson className="w-3.5 h-3.5 text-white/70 shrink-0" />;
    if (path.endsWith('.ts') || path.endsWith('.tsx') || path.endsWith('.js')) {
      return <FileCode className="w-3.5 h-3.5 text-[#ccff00] shrink-0" />;
    }
    if (path.endsWith('.md')) return <FileText className="w-3.5 h-3.5 text-white/50 shrink-0" />;
    return <Terminal className="w-3.5 h-3.5 text-white/60 shrink-0" />;
  };

  const lineCount = selectedFile ? selectedFile.content.split('\n').length : 0;
  const byteCount = selectedFile ? new Blob([selectedFile.content]).size : 0;

  return (
    <div className="bg-[#0a0a0a] border border-white/10 flex flex-col md:flex-row h-[700px] relative overflow-hidden">
      <div className="absolute top-0 left-0 w-full h-1 bg-[#ccff00]"></div>

      {/* Left Pane: File Tree Explorer */}
      <div className="w-full md:w-80 border-b md:border-b-0 md:border-r border-white/10 flex flex-col bg-[#111111]/80">
        {/* Header & Search */}
        <div className="p-4 border-b border-white/10 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono font-bold uppercase tracking-wider text-white flex items-center gap-2">
              <Folder className="w-3.5 h-3.5 text-[#ccff00]" />
              PROJECT TREE ({files.length})
            </span>
            <span className="text-[9px] font-mono bg-white/5 text-[#ccff00] px-2 py-0.5 border border-white/10">
              ESM
            </span>
          </div>

          <div className="relative">
            <Search className="w-3.5 h-3.5 text-white/30 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search file path..."
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              className="w-full bg-[#0a0a0a] border border-white/10 pl-8 pr-3 py-2 text-xs text-white font-mono placeholder-white/30 focus:outline-none focus:border-[#ccff00]"
            />
          </div>
        </div>

        {/* File List */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {filteredFiles.map((file) => {
            const isSelected = selectedFile?.path === file.path;
            return (
              <button
                key={file.path}
                onClick={() => setSelectedFile(file)}
                className={`w-full text-left flex items-center justify-between px-3 py-2 text-xs font-mono transition-all ${
                  isSelected
                    ? 'bg-[#ccff00] text-black font-black shadow-[0_0_10px_rgba(204,255,0,0.2)]'
                    : 'text-white/60 hover:bg-white/5 hover:text-white'
                }`}
              >
                <div className="flex items-center space-x-2 min-w-0">
                  {getFileIcon(file.path)}
                  <span className="truncate">{file.path}</span>
                </div>
                {file.isEntry && (
                  <span className={`text-[8px] uppercase tracking-wider px-1.5 py-0.2 shrink-0 ml-1 font-bold ${
                    isSelected ? 'bg-black text-[#ccff00]' : 'bg-white/10 text-[#ccff00]'
                  }`}>
                    entry
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Footer Actions */}
        <div className="p-4 border-t border-white/10 bg-[#0a0a0a] flex items-center justify-between">
          <div className="text-[10px] font-mono text-white/40 uppercase">
            {files.length} Modules
          </div>
          <button
            onClick={onDownloadZip}
            className="bg-[#ccff00] text-black font-black text-xs px-3.5 py-2 uppercase tracking-tight hover:bg-[#b8e600] flex items-center space-x-1.5 transition-all shadow-[0_0_10px_rgba(204,255,0,0.2)]"
          >
            <Download className="w-3.5 h-3.5 stroke-[2.5]" />
            <span>EXPORT ALL</span>
          </button>
        </div>
      </div>

      {/* Right Pane: Code Viewer */}
      <div className="flex-1 flex flex-col min-w-0 bg-[#0a0a0a]">
        {selectedFile ? (
          <>
            {/* Code Header Bar */}
            <div className="px-6 py-4 border-b border-white/10 bg-[#111111]/40 flex items-center justify-between flex-wrap gap-3">
              <div className="flex items-center space-x-2 min-w-0">
                <span className="text-xs font-mono font-black text-white tracking-wide truncate">
                  // {selectedFile.path}
                </span>
                {selectedFile.description && (
                  <span className="text-[11px] font-mono text-white/40 hidden lg:inline-block truncate">
                    ({selectedFile.description})
                  </span>
                )}
              </div>

              <div className="flex items-center space-x-3">
                <span className="text-[10px] font-mono text-white/40 bg-white/5 px-2.5 py-1 border border-white/10">
                  {lineCount} LINES • {(byteCount / 1024).toFixed(1)} KB
                </span>

                <button
                  onClick={handleCopyCode}
                  className="flex items-center space-x-1.5 text-xs font-mono font-bold bg-white/5 hover:bg-white/10 text-white px-3 py-1.5 border border-white/10 transition-colors"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-[#ccff00]" /> : <Copy className="w-3.5 h-3.5 text-white/40" />}
                  <span>{copied ? 'COPIED' : 'COPY'}</span>
                </button>

                <button
                  onClick={handleDownloadSingleFile}
                  className="flex items-center space-x-1.5 text-xs font-mono font-bold bg-white/5 hover:bg-white/10 text-white px-3 py-1.5 border border-white/10 transition-colors"
                >
                  <Download className="w-3.5 h-3.5 text-white/40" />
                  <span>SAVE</span>
                </button>
              </div>
            </div>

            {/* Code Body */}
            <div className="flex-1 overflow-auto font-mono text-xs p-6 bg-[#0a0a0a] flex select-text">
              {/* Line numbers column */}
              <div className="select-none pr-5 text-right text-white/20 border-r border-white/10 font-mono shrink-0">
                {selectedFile.content.split('\n').map((_, idx) => (
                  <div key={idx} className="leading-relaxed">
                    {idx + 1}
                  </div>
                ))}
              </div>

              {/* Code lines */}
              <pre className="pl-5 text-white/90 leading-relaxed overflow-x-auto whitespace-pre font-mono flex-1">
                <code>{selectedFile.content}</code>
              </pre>
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-white/30 p-8 font-mono">
            <Terminal className="w-12 h-12 mb-3 text-white/20" />
            <p className="text-xs uppercase tracking-widest">Select a module from the tree</p>
          </div>
        )}
      </div>
    </div>
  );
};
