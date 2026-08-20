import { ScaffoldConfig, ProjectFile } from '../types/scaffold';

export function generateScaffoldFiles(config: ScaffoldConfig): ProjectFile[] {
  const files: ProjectFile[] = [];
  const name = config.projectName.toLowerCase().replace(/[^a-z0-9-]/g, '-') || 'node22-scaffold';

  // 1. package.json
  const dependencies: Record<string, string> = {};
  const devDependencies: Record<string, string> = {
    '@types/node': '^22.14.0',
    'typescript': '^5.8.2',
  };

  if (config.framework === 'express') {
    dependencies['express'] = '^4.21.2';
    devDependencies['@types/express'] = '^4.17.21';
    dependencies['cors'] = '^2.8.5';
    devDependencies['@types/cors'] = '^2.8.17';
    dependencies['helmet'] = '^8.0.0';
  } else if (config.framework === 'hono') {
    dependencies['hono'] = '^4.7.2';
    dependencies['@hono/node-server'] = '^1.13.8';
  } else if (config.framework === 'fastify') {
    dependencies['fastify'] = '^5.2.1';
    dependencies['@fastify/cors'] = '^10.0.2';
    dependencies['@fastify/helmet'] = '^13.0.1';
  }

  if (config.auth === 'jwt') {
    dependencies['jsonwebtoken'] = '^9.0.2';
    devDependencies['@types/jsonwebtoken'] = '^9.0.9';
    dependencies['zod'] = '^3.24.2';
  }

  if (config.database === 'drizzle-sqlite') {
    dependencies['drizzle-orm'] = '^0.39.3';
    devDependencies['drizzle-kit'] = '^0.30.4';
  }

  if (config.frontend === 'react19-vite') {
    dependencies['react'] = '^19.0.0';
    dependencies['react-dom'] = '^19.0.0';
    dependencies['lucide-react'] = '^0.546.0';
    devDependencies['@types/react'] = '^19.0.10';
    devDependencies['@types/react-dom'] = '^19.0.4';
    devDependencies['@vitejs/plugin-react'] = '^5.0.4';
    devDependencies['vite'] = '^6.2.3';
    devDependencies['tailwindcss'] = '^4.1.14';
    devDependencies['@tailwindcss/vite'] = '^4.1.14';
  }

  const scripts: Record<string, string> = {
    dev: config.enableProcessEnvFile
      ? 'node --watch --env-file=.env src/index.ts'
      : 'node --watch src/index.ts',
    build: config.frontend === 'react19-vite' ? 'vite build && tsc' : 'tsc',
    start: 'NODE_ENV=production node dist/index.js',
    test: 'node --test tests/**/*.test.ts',
    lint: 'tsc --noEmit',
  };

  const packageJson = {
    name,
    version: '1.0.0',
    private: true,
    type: 'module',
    engines: {
      node: config.nodeVersion === '22-lts' ? '>=22.0.0' : '>=23.0.0',
    },
    scripts,
    dependencies,
    devDependencies,
  };

  files.push({
    path: 'package.json',
    language: 'json',
    description: 'Project manifest with dependencies and Node 22 engines',
    content: JSON.stringify(packageJson, null, 2),
  });

  // 2. tsconfig.json
  files.push({
    path: 'tsconfig.json',
    language: 'json',
    description: 'TypeScript configuration optimized for Node 22 LTS module resolution',
    content: `{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "isolatedModules": true,
    "allowImportingTsExtensions": true,
    "noEmit": true,
    "jsx": "react-jsx"
  },
  "include": ["src", "tests"]
}`,
  });

  // 3. Server Entry File
  if (config.framework === 'express') {
    files.push({
      path: 'src/index.ts',
      language: 'typescript',
      isEntry: true,
      description: 'Primary Express entrypoint with security and routes',
      content: `import express, { Request, Response } from 'express';
import helmet from 'helmet';
import cors from 'cors';
import { apiRouter } from './routes/api.ts';

const app = express();
const PORT = process.env.PORT || 3000;

app.use(helmet());
app.use(cors());
app.use(express.json());

// Healthcheck probe with native Node 22 metrics
app.get('/healthz', (req: Request, res: Response) => {
  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    uptime: Math.floor(process.uptime()),
    nodeVersion: process.version,
    memory: process.memoryUsage(),
  });
});

app.use('/api', apiRouter);

app.listen(PORT, () => {
  console.log(\`⚡ Server listening on http://localhost:\${PORT} (Node \${process.version})\`);
});
`,
    });

    files.push({
      path: 'src/routes/api.ts',
      language: 'typescript',
      description: 'API Router mounting system and business endpoints',
      content: `import { Router, Request, Response } from 'express';

export const apiRouter = Router();

apiRouter.get('/status', (req: Request, res: Response) => {
  res.json({
    success: true,
    message: 'Node 22 LTS API is operational',
    uuid: crypto.randomUUID(),
    timestamp: Date.now(),
  });
});
`,
    });
  } else if (config.framework === 'hono') {
    files.push({
      path: 'src/index.ts',
      language: 'typescript',
      isEntry: true,
      description: 'High-speed Hono server for Node 22',
      content: `import { Hono } from 'hono';
import { serve } from '@hono/node-server';

const app = new Hono();

app.get('/healthz', (c) => c.json({ status: 'healthy', uptime: process.uptime(), node: process.version }));

app.get('/api/info', (c) => {
  return c.json({
    success: true,
    framework: 'Hono on Node 22',
    id: crypto.randomUUID(),
  });
});

const port = Number(process.env.PORT) || 3000;
console.log(\`🔥 Hono server running on http://localhost:\${port} (Node \${process.version})\`);
serve({ fetch: app.fetch, port });
`,
    });
  } else {
    // Native HTTP
    files.push({
      path: 'src/index.ts',
      language: 'typescript',
      isEntry: true,
      description: 'Zero-dependency Node 22 native HTTP server',
      content: `import http, { IncomingMessage, ServerResponse } from 'node:http';

const PORT = process.env.PORT || 3000;

const server = http.createServer((req: IncomingMessage, res: ServerResponse) => {
  res.writeHead(200, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({
    success: true,
    engine: 'Node 22 Native HTTP',
    nodeVersion: process.version,
    uuid: crypto.randomUUID(),
  }));
});

server.listen(PORT, () => {
  console.log(\`⚡ Zero-dependency server listening on http://localhost:\${PORT}\`);
});
`,
    });
  }

  // 4. Database Layer (if selected)
  if (config.database === 'sqlite-native') {
    files.push({
      path: 'src/db/sqlite.ts',
      language: 'typescript',
      description: 'Node 22 native SQLite DatabaseSync manager',
      content: `import { DatabaseSync } from 'node:sqlite';

const dbPath = process.env.DATABASE_PATH || ':memory:';
export const db = new DatabaseSync(dbPath);

// Initialize schema tables
db.exec(\`
  CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    createdAt TEXT NOT NULL
  );
\`);

export const itemsRepo = {
  create: (title: string) => {
    const id = crypto.randomUUID();
    const now = new Date().toISOString();
    const stmt = db.prepare('INSERT INTO items (id, title, status, createdAt) VALUES (?, ?, ?, ?)');
    stmt.run(id, title, 'pending', now);
    return { id, title, status: 'pending', createdAt: now };
  },
  findAll: () => {
    const stmt = db.prepare('SELECT * FROM items ORDER BY createdAt DESC');
    return stmt.all();
  },
};
`,
    });
  }

  // 5. Native Tests
  files.push({
    path: 'tests/app.test.ts',
    language: 'typescript',
    description: 'Node 22 native test runner suite',
    content: `import test, { describe, it } from 'node:test';
import assert from 'node:assert/strict';

describe('App Architecture & Node 22 Verification', () => {
  it('should verify Node 22 native crypto.randomUUID', () => {
    const id = crypto.randomUUID();
    assert.strictEqual(typeof id, 'string');
    assert.strictEqual(id.length, 36);
  });

  it('should verify structuredClone', () => {
    const obj = { nested: { a: 1 }, list: [10, 20] };
    const clone = structuredClone(obj);
    assert.deepStrictEqual(obj, clone);
    assert.notStrictEqual(obj.nested, clone.nested);
  });
});
`,
  });

  // 6. Dockerfile
  if (config.enableDocker) {
    files.push({
      path: 'Dockerfile',
      language: 'dockerfile',
      description: 'Production-grade multi-stage Dockerfile for Node 22 Alpine',
      content: `FROM node:22-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000

RUN addgroup --system --gid 1001 nodejs && \\
    adduser --system --uid 1001 nodeapp

COPY package*.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY --from=builder /app/dist ./dist

USER nodeapp
EXPOSE 3000

CMD ["node", "dist/index.js"]
`,
    });
  }

  // 7. GitHub Actions
  if (config.enableGithubActions) {
    files.push({
      path: '.github/workflows/ci.yml',
      language: 'yaml',
      description: 'GitHub Actions Continuous Integration configuration',
      content: `name: Node 22 CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22.x
          cache: 'npm'
      - run: npm ci
      - run: npm run lint
      - run: npm test
`,
    });
  }

  // 8. .env.example
  files.push({
    path: '.env.example',
    language: 'shell',
    description: 'Sample environment variables for process.loadEnvFile()',
    content: `# Node 22 Application Configuration
PORT=3000
NODE_ENV=development
APP_SECRET=your_super_secret_key_here
DATABASE_PATH=:memory:
`,
  });

  // 9. README.md
  files.push({
    path: 'README.md',
    language: 'markdown',
    description: 'Documentation and developer getting started guide',
    content: `# ${name}

> Generated with **Node.js 22 LTS Scaffolding Studio**

## 🚀 Getting Started

\`\`\`bash
# 1. Install dependencies
npm install

# 2. Setup environment
cp .env.example .env

# 3. Start development server with native watch
npm run dev

# 4. Run native test suite
npm test
\`\`\`
`,
  });

  return files;
}
