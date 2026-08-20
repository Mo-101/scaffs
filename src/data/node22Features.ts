import { Node22Feature } from '../types/scaffold';

export const NODE22_FEATURES: Node22Feature[] = [
  {
    id: 'native-sqlite',
    title: 'Native SQLite Module (node:sqlite)',
    category: 'Standard Library',
    badge: 'Built-in DB',
    summary: 'Synchronous and transactional SQLite3 database client built directly into Node 22 without native C++ compilation or sqlite3 npm packages.',
    description: 'Node 22 introduces the experimental `node:sqlite` standard library module. It exposes `DatabaseSync` allowing instant in-memory or file-backed database storage with prepared statements, transactions, and parameter binding.',
    advantages: [
      'Zero npm install or node-gyp native compilation steps',
      'Synchronous and predictable high-performance query execution',
      'Prepared statements with parameter binding to eliminate SQL injections',
      'Direct support for in-memory databases (:memory:)',
    ],
    codeSnippet: `import { DatabaseSync } from 'node:sqlite';

// Initialize in-memory or file database
const db = new DatabaseSync(':memory:');

// Execute DDL
db.exec(\`
  CREATE TABLE users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    score INTEGER NOT NULL
  ) STRICT;
\`);

// Prepared statement
const insert = db.prepare('INSERT INTO users (id, name, score) VALUES (?, ?, ?)');
insert.run(crypto.randomUUID(), 'Alex Mercer', 985);

// Query records
const query = db.prepare('SELECT * FROM users WHERE score > ?');
const topUsers = query.all(500);
console.log(topUsers);
`,
    sampleRunnableCode: `// Live in-browser preview simulation of node:sqlite
const mockDb = [
  { id: 'usr_01', name: 'Dev Lead', role: 'Architect', score: 994 },
  { id: 'usr_02', name: 'SRE Specialist', role: 'DevOps', score: 880 },
];
console.log('Query: SELECT * FROM users WHERE score > 800');
console.table(mockDb);
`,
  },
  {
    id: 'native-test-runner',
    title: 'Native Test Runner (node:test & node:assert)',
    category: 'Standard Library',
    badge: 'Zero-Config Tests',
    summary: 'Full-featured unit & integration test runner built into Node.js, supporting subtests, mocking, snapshots, and TAP/spec reporters.',
    description: 'Eliminates the need for Jest, Mocha, or heavy test runners for standard backend testing. Includes `describe`, `it`, `before`, `after`, `mock`, and TAP/spec output formatting.',
    advantages: [
      'Zero extra dependencies or setup required',
      'Native watch mode: `node --test --watch`',
      'Built-in coverage reporter: `node --test --experimental-test-coverage`',
      'First-class TypeScript and ESM compatibility',
    ],
    codeSnippet: `import test, { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';

describe('Payment Calculator', () => {
  it('should calculate 20% VAT correctly', () => {
    const total = 100 * 1.20;
    assert.strictEqual(total, 120);
  });

  it('should handle async promises and rejects', async () => {
    await assert.rejects(
      async () => { throw new Error('Invalid token'); },
      { message: 'Invalid token' }
    );
  });
});
`,
  },
  {
    id: 'type-stripping',
    title: 'Native TypeScript Type Stripping',
    category: 'Runtime',
    badge: '--experimental-strip-types',
    summary: 'Run .ts files directly in Node 22 without ts-node, babel, or a pre-compilation step by stripping type annotations at parse time.',
    description: 'Node.js 22 can execute TypeScript files directly using the `--experimental-strip-types` flag. The V8 parser ignores inline type annotations, interfaces, and types to execute JavaScript at native speeds.',
    advantages: [
      'Execute `node --experimental-strip-types server.ts` directly',
      'No compile step or intermediate build artifacts during dev',
      'Fast startup time and minimal CPU overhead',
    ],
    codeSnippet: `// server.ts (executed directly: node --experimental-strip-types server.ts)
interface UserConfig {
  port: number;
  host: string;
  enableDebug: boolean;
}

const config: UserConfig = {
  port: 3000,
  host: '0.0.0.0',
  enableDebug: true,
};

function startServer(cfg: UserConfig): void {
  console.log(\`Starting server on \${cfg.host}:\${cfg.port}\`);
}

startServer(config);
`,
  },
  {
    id: 'native-env-loader',
    title: 'Native .env File Loader (process.loadEnvFile)',
    category: 'Runtime',
    badge: 'Native .env',
    summary: 'Load environment variables natively from .env files without dotenv or custom scripts.',
    description: 'Node 22 provides both CLI `--env-file=.env` and runtime programmatic `process.loadEnvFile(".env")` to safely parse and inject environment variables.',
    advantages: [
      'Drop dotenv runtime dependency',
      'Works with custom paths: `node --env-file=.env.production app.js`',
      'Consistent parse rules matching standard POSIX env formats',
    ],
    codeSnippet: `// Programmatic usage in code
if (process.env.NODE_ENV !== 'production') {
  process.loadEnvFile('.env.local');
}

console.log('Database URL:', process.env.DATABASE_URL);
console.log('App Secret:', process.env.APP_SECRET ? '******' : 'undefined');
`,
  },
  {
    id: 'native-watch',
    title: 'Native Watch Mode (node --watch)',
    category: 'Runtime',
    badge: '--watch',
    summary: 'Built-in process watcher that restarts the application on file changes without nodemon or pm2.',
    description: 'Watches imported files and restarts the process gracefully on save. Supports glob patterns and path filtering with `--watch-path`.',
    advantages: [
      'No need to install nodemon, ts-node-dev, or supervisor',
      'Optimized file watcher integrated with Libuv kernel notifications',
      'Combines seamlessly: `node --watch --env-file=.env server.ts`',
    ],
    codeSnippet: `# Command line execution:
node --watch --env-file=.env server.ts

# Watch specific directories only:
node --watch-path=./src --watch-path=./config app.js
`,
  },
  {
    id: 'web-standards',
    title: 'Web Standards: Fetch, WebSockets & Streams',
    category: 'Standard Library',
    badge: 'Web Interop',
    summary: 'Global fetch, WebSocket client, ReadableStream, TransformStream, and TextEncoder/TextDecoder out of the box.',
    description: 'Node 22 features comprehensive alignment with browser Web APIs. You can instantiate `new WebSocket("wss://...")`, call `fetch()`, and pipe `ReadableStream` natively on both client and server.',
    advantages: [
      'Write isomorphic JavaScript running identically in Node 22 and browser',
      'Zero dependency HTTP client and WebSocket connections',
      'High-speed streaming with backpressure support via Web Streams',
    ],
    codeSnippet: `// Global fetch with abort controller
const controller = new AbortController();
const timeout = setTimeout(() => controller.abort(), 5000);

const res = await fetch('https://api.github.com/zen', {
  signal: controller.signal,
  headers: { 'User-Agent': 'Node22-App' },
});
const quote = await res.text();
clearTimeout(timeout);
console.log('Zen quote:', quote);
`,
  },
];
