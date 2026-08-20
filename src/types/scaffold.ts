export interface ProjectFile {
  path: string;
  content: string;
  language: 'typescript' | 'javascript' | 'json' | 'markdown' | 'dockerfile' | 'yaml' | 'css' | 'html' | 'shell' | 'sql';
  description?: string;
  isEntry?: boolean;
}

export type FrameworkType = 'express' | 'hono' | 'fastify' | 'native-http';
export type DatabaseType = 'sqlite-native' | 'drizzle-sqlite' | 'prisma-pg' | 'pglite' | 'none';
export type FrontendType = 'react19-vite' | 'pure-api' | 'vue-vite' | 'vanilla';
export type AuthType = 'jwt' | 'session-cookies' | 'api-key' | 'none';
export type TestRunnerType = 'node-test' | 'vitest' | 'jest';

export interface ScaffoldConfig {
  projectName: string;
  description: string;
  nodeVersion: '22-lts' | '23-current';
  framework: FrameworkType;
  frontend: FrontendType;
  database: DatabaseType;
  auth: AuthType;
  testRunner: TestRunnerType;
  enableTypeStripping: boolean;
  enableNativeSqlite: boolean;
  enableProcessEnvFile: boolean;
  enableNativeWatch: boolean;
  enableDocker: boolean;
  enableGithubActions: boolean;
  enableOpenApi: boolean;
  architecturePattern: 'clean' | 'modular-monolith' | 'vertical-slice' | 'microservice';
}

export interface ProjectTemplate {
  id: string;
  name: string;
  tagline: string;
  category: 'Full-Stack' | 'Microservice' | 'AI & LLM' | 'Real-Time' | 'Enterprise';
  icon: string;
  badge: string;
  description: string;
  highlights: string[];
  config: ScaffoldConfig;
  files: ProjectFile[];
}

export interface Node22Feature {
  id: string;
  title: string;
  category: 'Runtime' | 'Standard Library' | 'V8 & Performance' | 'Security & CLI';
  badge: string;
  summary: string;
  description: string;
  codeSnippet: string;
  advantages: string[];
  sampleRunnableCode?: string;
}

export interface NodeSystemInfo {
  nodeVersion: string;
  v8Version: string;
  uvVersion: string;
  zlibVersion: string;
  opensslVersion: string;
  platform: string;
  arch: string;
  pid: number;
  uptimeSeconds: number;
  memory: {
    rssMb: string;
    heapTotalMb: string;
    heapUsedMb: string;
    externalMb: string;
  };
  features: {
    hasNativeSqlite: boolean;
    hasNativeFetch: boolean;
    hasNativeWebSocket: boolean;
    hasCryptoUUID: boolean;
    hasProcessLoadEnvFile: boolean;
    hasStructuredClone: boolean;
    hasAsyncLocalStorage: boolean;
    hasWebStreams: boolean;
  };
  timestamp: string;
}

export interface BenchmarkResult {
  name: string;
  opsPerSec: number;
  timeMs: number;
  category: string;
  note: string;
}
