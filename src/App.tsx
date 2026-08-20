import React, { useState, useEffect } from 'react';
import { Navbar, ActiveTab } from './components/Navbar';
import { ScaffoldStudio } from './components/ScaffoldStudio';
import { TemplatesLibrary } from './components/TemplatesLibrary';
import { AiArchitect } from './components/AiArchitect';
import { Node22Playground } from './components/Node22Playground';
import { RuntimeInspector } from './components/RuntimeInspector';
import { ApiSandbox } from './components/ApiSandbox';
import { ScaffoldConfig, ProjectFile, NodeSystemInfo, ProjectTemplate } from './types/scaffold';
import { TEMPLATES } from './data/templates';
import { downloadProjectZip } from './utils/zipExport';

export default function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('scaffold');
  const [systemInfo, setSystemInfo] = useState<NodeSystemInfo | null>(null);
  const [loadingSystemInfo, setLoadingSystemInfo] = useState<boolean>(false);

  // Active Project Scaffolding State
  const defaultTemplate = TEMPLATES[0];
  const [currentConfig, setCurrentConfig] = useState<ScaffoldConfig>(defaultTemplate.config);
  const [files, setFiles] = useState<ProjectFile[]>(defaultTemplate.files);

  // Fetch Live Node 22 runtime diagnostics
  const fetchSystemInfo = async () => {
    setLoadingSystemInfo(true);
    try {
      const res = await fetch('/api/system/node-info');
      const data = await res.json();
      if (data.success && data.data) {
        setSystemInfo(data.data);
      }
    } catch (err) {
      console.error('Failed to load system diagnostics', err);
    } finally {
      setLoadingSystemInfo(false);
    }
  };

  useEffect(() => {
    fetchSystemInfo();
  }, []);

  const handleDownloadCurrentZip = () => {
    downloadProjectZip(currentConfig.projectName, files);
  };

  const handleLoadTemplate = (template: ProjectTemplate) => {
    setCurrentConfig(template.config);
    setFiles(template.files);
    setActiveTab('scaffold');
  };

  const handleLoadGeneratedProject = (projectName: string, newFiles: ProjectFile[]) => {
    setCurrentConfig((prev) => ({
      ...prev,
      projectName,
      description: `AI synthesized architecture for ${projectName}`,
    }));
    setFiles(newFiles);
    setActiveTab('scaffold');
  };

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white flex flex-col font-sans selection:bg-[#ccff00] selection:text-black">
      {/* Navigation Bar */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        systemInfo={systemInfo}
        onDownloadCurrentZip={handleDownloadCurrentZip}
        projectName={currentConfig.projectName}
      />

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-10">
        {activeTab === 'scaffold' && (
          <ScaffoldStudio
            currentConfig={currentConfig}
            setCurrentConfig={setCurrentConfig}
            files={files}
            setFiles={setFiles}
            onDownloadZip={handleDownloadCurrentZip}
          />
        )}

        {activeTab === 'templates' && (
          <TemplatesLibrary onLoadTemplate={handleLoadTemplate} />
        )}

        {activeTab === 'ai-architect' && (
          <AiArchitect onLoadGeneratedProject={handleLoadGeneratedProject} />
        )}

        {activeTab === 'sandbox' && <Node22Playground />}

        {activeTab === 'inspector' && (
          <RuntimeInspector
            systemInfo={systemInfo}
            onRefresh={fetchSystemInfo}
            loading={loadingSystemInfo}
          />
        )}

        {activeTab === 'api-docs' && <ApiSandbox />}
      </main>

      {/* High-Impact Footer matching Design Theme */}
      <footer className="border-t border-white/10 px-6 sm:px-12 py-6 bg-[#0a0a0a] text-white">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-6">
          <div className="flex flex-wrap items-center gap-8 sm:gap-12">
            <div className="flex flex-col">
              <span className="text-[9px] uppercase tracking-[0.2em] text-white/40 font-bold">PROJECT SLUG</span>
              <span className="text-xs font-mono text-white mt-0.5">{currentConfig.projectName}</span>
            </div>

            <div className="flex flex-col">
              <span className="text-[9px] uppercase tracking-[0.2em] text-white/40 font-bold">TARGET ENGINE</span>
              <span className="text-xs font-mono text-white mt-0.5">Node.js 22 LTS (V8 Maglev)</span>
            </div>

            <div className="flex flex-col hidden md:flex">
              <span className="text-[9px] uppercase tracking-[0.2em] text-white/40 font-bold">STANDARD BUILT-INS</span>
              <span className="text-xs font-mono text-[#ccff00] mt-0.5">node:sqlite • node:test • --watch</span>
            </div>
          </div>

          <div className="flex items-center space-x-4">
            <span className="text-[10px] font-mono text-white/40 uppercase hidden lg:inline">
              // READY TO DEPLOY
            </span>
            <button
              onClick={handleDownloadCurrentZip}
              className="bg-[#ccff00] text-black px-8 py-3 font-black text-xs uppercase tracking-tighter transform hover:-translate-y-0.5 transition-transform shadow-[0_0_15px_rgba(204,255,0,0.25)]"
            >
              RUN SCAFFOLD (.ZIP)
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
}
