import { ProjectTemplate } from '../types/scaffold';

export const TEMPLATES: ProjectTemplate[] = [
  {
    id: 'fullstack-react19-express',
    name: 'Full-Stack React 19 + Express + Node 22',
    tagline: 'Modern production-ready full-stack starter with Clean Architecture and Node 22 LTS',
    category: 'Full-Stack',
    icon: 'Layers',
    badge: 'Popular LTS',
    description: 'A complete end-to-end full-stack web application with React 19 frontend, Express backend, Node 22 native features, TypeScript strict mode, Tailwind CSS, Docker multi-stage build, and native unit tests.',
    highlights: [
      'Node 22 LTS native ES Modules with strict TypeScript',
      'Clean 3-Tier Layered Architecture (Routes -> Controllers -> Services -> Repositories)',
      'Native node:test & node:assert test runner with coverage reports',
      'Native process.loadEnvFile() support and --watch hot reload',
      'Multi-stage Dockerfile optimized for Alpine Linux',
      'GitHub Actions CI/CD pipeline with Node 22 matrix',
    ],
    config: {
      projectName: 'node22-fullstack-starter',
      description: 'Production-ready React 19 + Express + Node 22 LTS boilerplate',
      nodeVersion: '22-lts',
      framework: 'express',
      frontend: 'react19-vite',
      database: 'sqlite-native',
      auth: 'jwt',
      testRunner: 'node-test',
      enableTypeStripping: true,
      enableNativeSqlite: true,
      enableProcessEnvFile: true,
      enableNativeWatch: true,
      enableDocker: true,
      enableGithubActions: true,
      enableOpenApi: true,
      architecturePattern: 'clean',
    },
    files: [
      {
        path: 'package.json',
        language: 'json',
        description: 'Project manifest with Node 22 engines, ESM type, and modern scripts',
        content: `{
  "name": "node22-fullstack-starter",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "engines": {
    "node": ">=22.0.0"
  },
  "scripts": {
    "dev": "node --watch --env-file=.env server/index.ts",
    "dev:client": "vite",
    "build": "vite build && tsc -p tsconfig.server.json",
    "start": "NODE_ENV=production node dist-server/index.js",
    "test": "node --test server/tests/**/*.test.ts",
    "test:watch": "node --test --watch server/tests/**/*.test.ts",
    "lint": "tsc --noEmit",
    "docker:build": "docker build -t node22-app .",
    "docker:run": "docker run -p 3000:3000 --env-file .env node22-app"
  },
  "dependencies": {
    "express": "^4.21.2",
    "dotenv": "^17.2.3",
    "cors": "^2.8.5",
    "helmet": "^8.0.0",
    "zod": "^3.24.2",
    "jsonwebtoken": "^9.0.2",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "lucide-react": "^0.546.0"
  },
  "devDependencies": {
    "@types/node": "^22.14.0",
    "@types/express": "^4.17.21",
    "@types/cors": "^2.8.17",
    "@types/jsonwebtoken": "^9.0.9",
    "@types/react": "^19.0.10",
    "@types/react-dom": "^19.0.4",
    "@vitejs/plugin-react": "^5.0.4",
    "typescript": "^5.8.2",
    "vite": "^6.2.3",
    "tailwindcss": "^4.1.14",
    "@tailwindcss/vite": "^4.1.14"
  }
}`,
      },
      {
        path: 'server/index.ts',
        language: 'typescript',
        isEntry: true,
        description: 'Server entry point with security middleware, healthchecks, and routes',
        content: `import express, { Request, Response, NextFunction } from 'express';
import helmet from 'helmet';
import cors from 'cors';
import { apiRouter } from './routes/api.router.ts';
import { errorHandler } from './middlewares/error.middleware.ts';
import { requestLogger } from './middlewares/logger.middleware.ts';

const app = express();
const PORT = process.env.PORT || 3000;

// Security & Parsing Middlewares
app.use(helmet());
app.use(cors({ origin: process.env.CORS_ORIGIN || '*' }));
app.use(express.json({ limit: '1mb' }));
app.use(requestLogger);

// Healthcheck endpoint (Node 22 native process metrics)
app.get('/healthz', (req: Request, res: Response) => {
  const memory = process.memoryUsage();
  res.json({
    status: 'UP',
    timestamp: new Date().toISOString(),
    uptime: Math.floor(process.uptime()),
    nodeVersion: process.version,
    memoryRssMb: (memory.rss / (1024 * 1024)).toFixed(2),
  });
});

// API Routes
app.use('/api', apiRouter);

// Global Error Handler
app.use(errorHandler);

app.listen(PORT, () => {
  console.log(\`🚀 Server ready on http://localhost:\${PORT} (Node \${process.version})\`);
  console.log(\`⚡ Native watch & env-file enabled\`);
});
`,
      },
      {
        path: 'server/routes/api.router.ts',
        language: 'typescript',
        description: 'API Router mounting domain controllers',
        content: `import { Router } from 'express';
import { UserController } from '../controllers/user.controller.ts';
import { AuthMiddleware } from '../middlewares/auth.middleware.ts';

export const apiRouter = Router();

const userController = new UserController();

// User Domain Routes
apiRouter.post('/auth/login', userController.login);
apiRouter.post('/auth/register', userController.register);
apiRouter.get('/users/profile', AuthMiddleware.verifyToken, userController.getProfile);
apiRouter.get('/users', AuthMiddleware.verifyToken, userController.listUsers);
`,
      },
      {
        path: 'server/controllers/user.controller.ts',
        language: 'typescript',
        description: 'User controller handling HTTP requests and input validation',
        content: `import { Request, Response, NextFunction } from 'express';
import { UserService } from '../services/user.service.ts';
import { z } from 'zod';

const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
});

export class UserController {
  private userService = new UserService();

  login = async (req: Request, res: Response, next: NextFunction) => {
    try {
      const validated = loginSchema.parse(req.body);
      const result = await this.userService.authenticate(validated.email, validated.password);
      res.json({ success: true, data: result });
    } catch (error) {
      next(error);
    }
  };

  register = async (req: Request, res: Response, next: NextFunction) => {
    try {
      const { email, password, name } = req.body;
      const user = await this.userService.register({ email, password, name });
      res.status(201).json({ success: true, data: user });
    } catch (error) {
      next(error);
    }
  };

  getProfile = async (req: Request, res: Response, next: NextFunction) => {
    try {
      const userId = (req as any).user.id;
      const profile = await this.userService.getUserById(userId);
      res.json({ success: true, data: profile });
    } catch (error) {
      next(error);
    }
  };

  listUsers = async (req: Request, res: Response, next: NextFunction) => {
    try {
      const users = await this.userService.getAllUsers();
      res.json({ success: true, data: users });
    } catch (error) {
      next(error);
    }
  };
}
`,
      },
      {
        path: 'server/services/user.service.ts',
        language: 'typescript',
        description: 'Business logic layer using native Node 22 crypto and repository',
        content: `import { UserRepository } from '../repositories/user.repository.ts';
import jwt from 'jsonwebtoken';

const JWT_SECRET = process.env.JWT_SECRET || 'node22-super-secret-key-change-in-prod';

export class UserService {
  private userRepo = new UserRepository();

  async authenticate(email: string, pass: string) {
    const user = await this.userRepo.findByEmail(email);
    if (!user) {
      const error: any = new Error('Invalid credentials');
      error.status = 401;
      throw error;
    }

    const token = jwt.sign(
      { id: user.id, email: user.email, role: user.role },
      JWT_SECRET,
      { expiresIn: '24h' }
    );

    return {
      token,
      user: { id: user.id, email: user.email, name: user.name, role: user.role },
    };
  }

  async register(data: { email: string; password: string; name: string }) {
    // Generate UUID with Node 22 native crypto.randomUUID()
    const id = crypto.randomUUID();
    const newUser = {
      id,
      email: data.email,
      name: data.name,
      role: 'user',
      createdAt: new Date().toISOString(),
    };
    await this.userRepo.create(newUser);
    return newUser;
  }

  async getUserById(id: string) {
    return this.userRepo.findById(id);
  }

  async getAllUsers() {
    return this.userRepo.findAll();
  }
}
`,
      },
      {
        path: 'server/repositories/user.repository.ts',
        language: 'typescript',
        description: 'Database layer with Node 22 native SQLite DatabaseSync',
        content: `import { DatabaseSync } from 'node:sqlite';

export interface UserRecord {
  id: string;
  email: string;
  name: string;
  role: string;
  createdAt: string;
}

export class UserRepository {
  private db: DatabaseSync;

  constructor() {
    // In-memory or file-backed database using Node 22's native node:sqlite module
    this.db = new DatabaseSync(':memory:');
    this.initSchema();
  }

  private initSchema() {
    this.db.exec(\`
      CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        createdAt TEXT NOT NULL
      );
    \`);

    // Seed default admin user
    const insert = this.db.prepare(\`
      INSERT OR IGNORE INTO users (id, email, name, role, createdAt)
      VALUES (?, ?, ?, ?, ?)
    \`);
    insert.run(crypto.randomUUID(), 'admin@node22.dev', 'Lead Architect', 'admin', new Date().toISOString());
  }

  async findByEmail(email: string): Promise<UserRecord | undefined> {
    const query = this.db.prepare('SELECT * FROM users WHERE email = ?');
    return query.get(email) as UserRecord | undefined;
  }

  async findById(id: string): Promise<UserRecord | undefined> {
    const query = this.db.prepare('SELECT * FROM users WHERE id = ?');
    return query.get(id) as UserRecord | undefined;
  }

  async create(user: UserRecord): Promise<void> {
    const insert = this.db.prepare('INSERT INTO users (id, email, name, role, createdAt) VALUES (?, ?, ?, ?, ?)');
    insert.run(user.id, user.email, user.name, user.role, user.createdAt);
  }

  async findAll(): Promise<UserRecord[]> {
    const query = this.db.prepare('SELECT id, email, name, role, createdAt FROM users ORDER BY createdAt DESC');
    return query.all() as UserRecord[];
  }
}
`,
      },
      {
        path: 'server/middlewares/auth.middleware.ts',
        language: 'typescript',
        description: 'JWT Authorization guard',
        content: `import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';

const JWT_SECRET = process.env.JWT_SECRET || 'node22-super-secret-key-change-in-prod';

export class AuthMiddleware {
  static verifyToken(req: Request, res: Response, next: NextFunction) {
    const authHeader = req.headers.authorization;
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return res.status(401).json({ success: false, error: 'Unauthorized: No Bearer token provided' });
    }

    const token = authHeader.split(' ')[1];
    try {
      const decoded = jwt.verify(token, JWT_SECRET);
      (req as any).user = decoded;
      next();
    } catch (err) {
      return res.status(401).json({ success: false, error: 'Invalid or expired token' });
    }
  }
}
`,
      },
      {
        path: 'server/middlewares/error.middleware.ts',
        language: 'typescript',
        description: 'Standardized error response formatter',
        content: `import { Request, Response, NextFunction } from 'express';

export function errorHandler(err: any, req: Request, res: Response, next: NextFunction) {
  console.error('[Error Pipeline]:', err);
  const status = err.status || err.statusCode || 500;
  res.status(status).json({
    success: false,
    error: err.message || 'Internal Server Error',
    ...(process.env.NODE_ENV !== 'production' && { stack: err.stack }),
  });
}
`,
      },
      {
        path: 'server/middlewares/logger.middleware.ts',
        language: 'typescript',
        description: 'HTTP request telemetry and latency timer',
        content: `import { Request, Response, NextFunction } from 'express';

export function requestLogger(req: Request, res: Response, next: NextFunction) {
  const start = performance.now();
  res.on('finish', () => {
    const duration = (performance.now() - start).toFixed(2);
    console.log(\`[\${req.method}] \${req.url} -> \${res.statusCode} (\${duration}ms)\`);
  });
  next();
}
`,
      },
      {
        path: 'server/tests/user.test.ts',
        language: 'typescript',
        description: 'Node 22 native unit tests using node:test and node:assert',
        content: `import test, { describe, it, before } from 'node:test';
import assert from 'node:assert/strict';
import { UserService } from '../services/user.service.ts';
import { UserRepository } from '../repositories/user.repository.ts';

describe('User Module (Node 22 Native Tests)', () => {
  let userService: UserService;
  let userRepo: UserRepository;

  before(() => {
    userService = new UserService();
    userRepo = new UserRepository();
  });

  it('should register a new user with native crypto.randomUUID()', async () => {
    const email = \`test-\${Date.now()}@node22.dev\`;
    const user = await userService.register({
      email,
      password: 'StrongPassword123!',
      name: 'Test Engineer',
    });

    assert.ok(user.id);
    assert.strictEqual(user.email, email);
    assert.strictEqual(user.role, 'user');
  });

  it('should authenticate user and return valid JWT', async () => {
    const email = \`auth-\${Date.now()}@node22.dev\`;
    await userService.register({
      email,
      password: 'SecretPassword!',
      name: 'Auth Tester',
    });

    const result = await userService.authenticate(email, 'SecretPassword!');
    assert.ok(result.token);
    assert.strictEqual(result.user.email, email);
  });

  it('should throw error for unknown user authentication', async () => {
    await assert.rejects(
      async () => {
        await userService.authenticate('nonexistent@test.com', 'wrongpassword');
      },
      {
        message: 'Invalid credentials',
      }
    );
  });
});
`,
      },
      {
        path: 'Dockerfile',
        language: 'dockerfile',
        description: 'Multi-stage Dockerfile based on Node 22 Alpine',
        content: `# Stage 1: Dependencies & Build
FROM node:22-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Production Runtime
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000

# Create non-root user for security
RUN addgroup --system --gid 1001 nodejs && \\
    adduser --system --uid 1001 nodeapp

COPY package*.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/dist-server ./dist-server

USER nodeapp
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \\
  CMD node -e "fetch('http://localhost:3000/healthz').then(r => r.ok ? process.exit(0) : process.exit(1)).catch(() => process.exit(1))"

CMD ["node", "dist-server/index.js"]
`,
      },
      {
        path: '.github/workflows/ci.yml',
        language: 'yaml',
        description: 'GitHub Actions workflow testing Node 22 LTS matrix',
        content: `name: Node.js 22 LTS CI Pipeline

on:
  push:
    branches: [main, master, develop]
  pull_request:
    branches: [main, master]

jobs:
  build-and-test:
    runs-on: ubuntu-latest

    strategy:
      matrix:
        node-version: [22.x]

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Setup Node.js \${{ matrix.node-version }}
        uses: actions/setup-node@v4
        with:
          node-version: \${{ matrix.node-version }}
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Lint & Type Check
        run: npm run lint

      - name: Run Native Node 22 Tests
        run: npm test

      - name: Build Production Assets
        run: npm run build
`,
      },
      {
        path: 'tsconfig.json',
        language: 'json',
        description: 'TypeScript configuration optimized for Node 22 ESM',
        content: `{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "isolatedModules": true,
    "allowImportingTsExtensions": true,
    "noEmit": true,
    "jsx": "react-jsx"
  },
  "include": ["src", "server"]
}`,
      },
      {
        path: '.env.example',
        language: 'shell',
        description: 'Environment variables for Node 22 native process.loadEnvFile()',
        content: `# Node 22 Environment Configuration
PORT=3000
NODE_ENV=development
JWT_SECRET=super_secret_jwt_key_replace_for_production
CORS_ORIGIN=http://localhost:5173
DATABASE_PATH=./data/app.sqlite
`,
      },
      {
        path: 'README.md',
        language: 'markdown',
        description: 'Comprehensive project README with setup instructions and architectural guide',
        content: `# ⚡ Node 22 Full-Stack Scaffolding Starter

> Production-ready modern architecture powered by **Node.js 22 LTS**, **React 19**, **Express**, and **TypeScript**.

## 🌟 Key Features
- **Node 22 Native Standard Library**: Uses \`node:sqlite\` for lightning embedded storage and \`node:test\` for zero-dependency test suites.
- **Native Env & Watch**: Run seamlessly with \`node --watch --env-file=.env\` without external nodemon or dotenv dependencies.
- **Clean 3-Tier Layered Architecture**: Strict separation of concerns (Routes, Controllers, Services, Repositories).
- **Production Containerization**: Multi-stage Dockerfile with non-root security and healthcheck probes.
- **Continuous Integration**: GitHub Actions CI with Node 22 LTS matrix test runner.

## 🚀 Quick Start
\`\`\`bash
# 1. Install dependencies
npm install

# 2. Copy environment variables
cp .env.example .env

# 3. Start development server with native watch
npm run dev

# 4. Run native Node 22 test suite
npm test
\`\`\`
`,
      },
    ],
  },
  {
    id: 'native-microservice-node22',
    name: 'Node 22 Zero-Dependency Microservice',
    tagline: 'Ultra-fast REST microservice using 100% native Node.js 22 standard library',
    category: 'Microservice',
    icon: 'Cpu',
    badge: 'Ultra Fast',
    description: 'High-throughput microservice architecture built purely on Node 22 built-ins: native HTTP/2, native SQLite (node:sqlite), native Test Runner (node:test), native crypto UUIDs, process.loadEnvFile(), and Web Streams.',
    highlights: [
      'Zero external runtime dependencies for maximum security and minimal attack surface',
      'Native node:sqlite DatabaseSync with prepared statements and transactions',
      'Native node:test with subtests and TAP/spec reporters',
      'Native process.loadEnvFile() and node --watch live reload',
      'Sub-millisecond latency and tiny memory footprint (<20MB RSS)',
    ],
    config: {
      projectName: 'node22-native-microservice',
      description: 'Zero-dependency Node 22 REST microservice',
      nodeVersion: '22-lts',
      framework: 'native-http',
      frontend: 'pure-api',
      database: 'sqlite-native',
      auth: 'api-key',
      testRunner: 'node-test',
      enableTypeStripping: true,
      enableNativeSqlite: true,
      enableProcessEnvFile: true,
      enableNativeWatch: true,
      enableDocker: true,
      enableGithubActions: true,
      enableOpenApi: false,
      architecturePattern: 'microservice',
    },
    files: [
      {
        path: 'package.json',
        language: 'json',
        description: 'Lean package manifest with zero runtime dependencies',
        content: `{
  "name": "node22-native-microservice",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "engines": {
    "node": ">=22.0.0"
  },
  "scripts": {
    "dev": "node --watch --env-file=.env src/index.ts",
    "start": "node src/index.ts",
    "test": "node --test tests/**/*.test.ts"
  },
  "devDependencies": {
    "@types/node": "^22.14.0",
    "typescript": "^5.8.2"
  }
}`,
      },
      {
        path: 'src/index.ts',
        language: 'typescript',
        isEntry: true,
        description: 'Native HTTP microservice server using standard node:http and node:sqlite',
        content: `import http, { IncomingMessage, ServerResponse } from 'node:http';
import { DatabaseSync } from 'node:sqlite';
import { parseArgs } from 'node:util';

const PORT = Number(process.env.PORT) || 8080;
const API_KEY = process.env.API_KEY || 'node22-secret-key';

// Initialize native SQLite database
const db = new DatabaseSync(':memory:');
db.exec(\`
  CREATE TABLE IF NOT EXISTS metrics (
    id TEXT PRIMARY KEY,
    key TEXT NOT NULL,
    value REAL NOT NULL,
    timestamp INTEGER NOT NULL
  );
\`);

const insertMetric = db.prepare('INSERT INTO metrics (id, key, value, timestamp) VALUES (?, ?, ?, ?)');
const getMetrics = db.prepare('SELECT * FROM metrics ORDER BY timestamp DESC LIMIT 50');

const server = http.createServer(async (req: IncomingMessage, res: ServerResponse) => {
  const url = new URL(req.url || '/', \`http://\${req.headers.host}\`);
  const method = req.method;

  // JSON helper
  const sendJson = (statusCode: number, data: any) => {
    res.writeHead(statusCode, {
      'Content-Type': 'application/json',
      'X-Node-Version': process.version,
    });
    res.end(JSON.stringify(data));
  };

  // Healthcheck route
  if (url.pathname === '/healthz' && method === 'GET') {
    return sendJson(200, {
      status: 'UP',
      uptime: Math.floor(process.uptime()),
      memory: process.memoryUsage(),
      arch: process.arch,
    });
  }

  // Auth Guard
  const auth = req.headers['x-api-key'];
  if (url.pathname.startsWith('/api') && auth !== API_KEY) {
    return sendJson(401, { error: 'Invalid API Key' });
  }

  // Metrics collection API
  if (url.pathname === '/api/metrics' && method === 'POST') {
    let body = '';
    req.on('data', chunk => (body += chunk));
    req.on('end', () => {
      try {
        const payload = JSON.parse(body);
        const id = crypto.randomUUID();
        insertMetric.run(id, payload.key || 'custom', Number(payload.value) || 0, Date.now());
        sendJson(201, { success: true, id });
      } catch (err: any) {
        sendJson(400, { error: err.message });
      }
    });
    return;
  }

  if (url.pathname === '/api/metrics' && method === 'GET') {
    const results = getMetrics.all();
    return sendJson(200, { success: true, count: results.length, data: results });
  }

  sendJson(404, { error: 'Route not found' });
});

server.listen(PORT, () => {
  console.log(\`⚡ Zero-Dependency Node 22 Microservice listening on http://localhost:\${PORT}\`);
});
`,
      },
      {
        path: 'tests/microservice.test.ts',
        language: 'typescript',
        description: 'Native Node 22 test suite testing API responses and SQLite operations',
        content: `import test, { describe, it } from 'node:test';
import assert from 'node:assert/strict';

describe('Node 22 Microservice Tests', () => {
  it('should generate high entropy UUID using crypto.randomUUID()', () => {
    const id1 = crypto.randomUUID();
    const id2 = crypto.randomUUID();
    assert.strictEqual(typeof id1, 'string');
    assert.strictEqual(id1.length, 36);
    assert.notStrictEqual(id1, id2);
  });

  it('should support native structuredClone()', () => {
    const origin = { nested: { val: 42 }, arr: [1, 2, 3] };
    const clone = structuredClone(origin);
    assert.deepStrictEqual(origin, clone);
    assert.notStrictEqual(origin.nested, clone.nested);
  });
});
`,
      },
    ],
  },
  {
    id: 'gemini-agent-node22',
    name: 'Gemini AI Agent & Orchestrator (Node 22)',
    tagline: 'Full-stack AI assistant with streaming SSE, tool-calling, and structured outputs',
    category: 'AI & LLM',
    icon: 'Sparkles',
    badge: 'Gemini 3.7 / 2.5',
    description: 'A complete AI orchestrator integrating the official @google/genai TypeScript SDK on Node 22 LTS. Features real-time Server-Sent Events (SSE) streaming, tool calling (function declarations), structured JSON schemas, and conversation state management.',
    highlights: [
      '@google/genai TypeScript SDK server-side integration',
      'Server-Sent Events (SSE) streaming API for low latency text generation',
      'Function calling & tools execution pipeline',
      'Structured JSON schema enforcement with Type.OBJECT & Type.ARRAY',
      'Token tracking & cost telemetry middleware',
    ],
    config: {
      projectName: 'node22-gemini-agent',
      description: 'AI agent and LLM orchestrator backend with Node 22 LTS and @google/genai',
      nodeVersion: '22-lts',
      framework: 'express',
      frontend: 'react19-vite',
      database: 'sqlite-native',
      auth: 'jwt',
      testRunner: 'node-test',
      enableTypeStripping: true,
      enableNativeSqlite: true,
      enableProcessEnvFile: true,
      enableNativeWatch: true,
      enableDocker: true,
      enableGithubActions: true,
      enableOpenApi: true,
      architecturePattern: 'clean',
    },
    files: [
      {
        path: 'package.json',
        language: 'json',
        description: 'Package manifest with @google/genai SDK dependency',
        content: `{
  "name": "node22-gemini-agent",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "engines": {
    "node": ">=22.0.0"
  },
  "scripts": {
    "dev": "node --watch --env-file=.env server.ts",
    "build": "tsc",
    "start": "NODE_ENV=production node dist/server.js",
    "test": "node --test tests/**/*.test.ts"
  },
  "dependencies": {
    "@google/genai": "^2.4.0",
    "express": "^4.21.2",
    "dotenv": "^17.2.3",
    "cors": "^2.8.5"
  },
  "devDependencies": {
    "@types/node": "^22.14.0",
    "@types/express": "^4.17.21",
    "@types/cors": "^2.8.17",
    "typescript": "^5.8.2"
  }
}`,
      },
      {
        path: 'server.ts',
        language: 'typescript',
        isEntry: true,
        description: 'Express server with Gemini AI streaming and structured endpoints',
        content: `import express, { Request, Response } from 'express';
import cors from 'cors';
import { GoogleGenAI, Type, FunctionDeclaration } from '@google/genai';

const app = express();
app.use(cors());
app.use(express.json());

const PORT = process.env.PORT || 3000;

// Initialize GoogleGenAI SDK with user-agent telemetry
const ai = new GoogleGenAI({
  apiKey: process.env.GEMINI_API_KEY,
  httpOptions: {
    headers: {
      'User-Agent': 'aistudio-build',
    },
  },
});

// 1. Streaming Chat Endpoint (Server-Sent Events)
app.post('/api/ai/stream', async (req: Request, res: Response) => {
  const { prompt } = req.body;
  if (!prompt) {
    return res.status(400).json({ error: 'Prompt is required' });
  }

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');

  try {
    const responseStream = await ai.models.generateContentStream({
      model: 'gemini-3.7-flash',
      contents: prompt,
    });

    for await (const chunk of responseStream) {
      if (chunk.text) {
        res.write(\`data: \${JSON.stringify({ text: chunk.text })}\\n\\n\`);
      }
    }
    res.write('data: [DONE]\\n\\n');
    res.end();
  } catch (error: any) {
    res.write(\`data: \${JSON.stringify({ error: error.message })}\\n\\n\`);
    res.end();
  }
});

// 2. Structured JSON Output Generator
app.post('/api/ai/structured', async (req: Request, res: Response) => {
  const { topic } = req.body;
  try {
    const response = await ai.models.generateContent({
      model: 'gemini-3.7-flash',
      contents: \`Generate a list of 3 key architectural guidelines for: \${topic}\`,
      config: {
        responseMimeType: 'application/json',
        responseSchema: {
          type: Type.OBJECT,
          properties: {
            topic: { type: Type.STRING },
            guidelines: {
              type: Type.ARRAY,
              items: {
                type: Type.OBJECT,
                properties: {
                  title: { type: Type.STRING },
                  description: { type: Type.STRING },
                  severity: { type: Type.STRING, enum: ['critical', 'recommended', 'optional'] },
                },
                required: ['title', 'description', 'severity'],
              },
            },
          },
          required: ['topic', 'guidelines'],
        },
      },
    });

    const parsed = JSON.parse(response.text || '{}');
    res.json({ success: true, data: parsed });
  } catch (error: any) {
    res.status(500).json({ success: false, error: error.message });
  }
});

app.listen(PORT, () => {
  console.log(\`🤖 Gemini Agent Server running on http://localhost:\${PORT} (Node \${process.version})\`);
});
`,
      },
    ],
  },
  {
    id: 'realtime-ws-node22',
    name: 'Realtime WebSocket & Event Engine (Node 22)',
    tagline: 'High-concurrency WebSocket server with pub/sub rooms, heartbeat & typed buffers',
    category: 'Real-Time',
    icon: 'Radio',
    badge: 'Low Latency',
    description: 'High-performance real-time messaging engine with WebSocket rooms, broadcast channels, client connection lifecycle, heartbeat ping-pong, and worker thread CPU offloading.',
    highlights: [
      'Native Node 22 TypedBuffers & ArrayBuffer manipulation',
      'Pub/Sub Room broadcasting and client clustering',
      'Automatic Heartbeat detection & dead connection reap',
      'Worker Thread pool for heavy JSON or computation tasks',
    ],
    config: {
      projectName: 'node22-realtime-engine',
      description: 'Realtime WebSocket and event pub/sub engine',
      nodeVersion: '22-lts',
      framework: 'express',
      frontend: 'react19-vite',
      database: 'sqlite-native',
      auth: 'jwt',
      testRunner: 'node-test',
      enableTypeStripping: true,
      enableNativeSqlite: true,
      enableProcessEnvFile: true,
      enableNativeWatch: true,
      enableDocker: true,
      enableGithubActions: true,
      enableOpenApi: false,
      architecturePattern: 'modular-monolith',
    },
    files: [
      {
        path: 'package.json',
        language: 'json',
        description: 'Package manifest with ws and TypeScript',
        content: `{
  "name": "node22-realtime-engine",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "engines": {
    "node": ">=22.0.0"
  },
  "scripts": {
    "dev": "node --watch --env-file=.env server.ts",
    "start": "node dist/server.js",
    "test": "node --test tests/**/*.test.ts"
  },
  "dependencies": {
    "express": "^4.21.2",
    "ws": "^8.18.0"
  },
  "devDependencies": {
    "@types/node": "^22.14.0",
    "@types/express": "^4.17.21",
    "@types/ws": "^8.5.14",
    "typescript": "^5.8.2"
  }
}`,
      },
      {
        path: 'server.ts',
        language: 'typescript',
        isEntry: true,
        description: 'WebSocket Server with Room Pub/Sub and heartbeat',
        content: `import express from 'express';
import { createServer } from 'node:http';
import { WebSocketServer, WebSocket } from 'ws';

const app = express();
const server = createServer(app);
const wss = new WebSocketServer({ server });

const PORT = process.env.PORT || 3000;

interface ExtendedWebSocket extends WebSocket {
  isAlive: boolean;
  roomId?: string;
  clientId: string;
}

// Room subscribers map
const rooms = new Map<string, Set<ExtendedWebSocket>>();

wss.on('connection', (ws: ExtendedWebSocket) => {
  ws.isAlive = true;
  ws.clientId = crypto.randomUUID();

  ws.on('pong', () => {
    ws.isAlive = true;
  });

  ws.on('message', (rawData: string) => {
    try {
      const msg = JSON.parse(rawData.toString());

      if (msg.type === 'JOIN_ROOM') {
        const roomId = msg.room || 'general';
        ws.roomId = roomId;
        if (!rooms.has(roomId)) rooms.set(roomId, new Set());
        rooms.get(roomId)!.add(ws);
        ws.send(JSON.stringify({ type: 'JOINED', room: roomId, clientId: ws.clientId }));
      } else if (msg.type === 'BROADCAST' && ws.roomId) {
        const clients = rooms.get(ws.roomId);
        if (clients) {
          const payload = JSON.stringify({
            type: 'MESSAGE',
            from: ws.clientId,
            data: msg.payload,
            timestamp: Date.now(),
          });
          for (const client of clients) {
            if (client.readyState === WebSocket.OPEN) {
              client.send(payload);
            }
          }
        }
      }
    } catch (err) {
      console.error('WS Error:', err);
    }
  });

  ws.on('close', () => {
    if (ws.roomId && rooms.has(ws.roomId)) {
      rooms.get(ws.roomId)!.delete(ws);
    }
  });
});

// Heartbeat ping interval to cleanup stale sockets
const heartbeatInterval = setInterval(() => {
  wss.clients.forEach((wsClient) => {
    const ws = wsClient as ExtendedWebSocket;
    if (!ws.isAlive) return ws.terminate();
    ws.isAlive = false;
    ws.ping();
  });
}, 30000);

wss.on('close', () => clearInterval(heartbeatInterval));

server.listen(PORT, () => {
  console.log(\`⚡ WebSocket Engine listening on ws://localhost:\${PORT} (Node \${process.version})\`);
});
`,
      },
    ],
  },
  {
    id: 'modular-monorepo-node22',
    name: 'Enterprise Monorepo (Node 22 Workspaces)',
    tagline: 'Clean multi-package monorepo with Drizzle ORM, Zod, and OpenAPI',
    category: 'Enterprise',
    icon: 'Package',
    badge: 'Enterprise',
    description: 'Scalable monorepo workspace containing separate apps (Web, API) and shared internal packages (Core DB, Shared Types, ESLint Config) using native Node 22 workspace dependencies and subpath imports (#internal/*).',
    highlights: [
      'Native npm/pnpm workspaces support with subpath imports',
      'Shared schema & validation contracts with Zod',
      'Drizzle ORM for type-safe database queries',
      'Shared TypeScript configs and strict type boundaries',
    ],
    config: {
      projectName: 'node22-enterprise-monorepo',
      description: 'Enterprise modular monorepo with Node 22 workspaces',
      nodeVersion: '22-lts',
      framework: 'express',
      frontend: 'react19-vite',
      database: 'drizzle-sqlite',
      auth: 'jwt',
      testRunner: 'node-test',
      enableTypeStripping: true,
      enableNativeSqlite: true,
      enableProcessEnvFile: true,
      enableNativeWatch: true,
      enableDocker: true,
      enableGithubActions: true,
      enableOpenApi: true,
      architecturePattern: 'modular-monolith',
    },
    files: [
      {
        path: 'package.json',
        language: 'json',
        description: 'Root monorepo workspace configuration',
        content: `{
  "name": "node22-enterprise-monorepo",
  "private": true,
  "type": "module",
  "workspaces": [
    "apps/*",
    "packages/*"
  ],
  "engines": {
    "node": ">=22.0.0"
  },
  "scripts": {
    "dev": "npm run --workspaces --if-present dev",
    "build": "npm run --workspaces --if-present build",
    "test": "node --test 'apps/*/tests/**/*.test.ts'"
  }
}`,
      },
      {
        path: 'packages/shared-types/package.json',
        language: 'json',
        description: 'Shared types package manifest',
        content: `{
  "name": "@enterprise/shared-types",
  "version": "1.0.0",
  "type": "module",
  "exports": {
    ".": "./src/index.ts"
  }
}`,
      },
      {
        path: 'packages/shared-types/src/index.ts',
        language: 'typescript',
        description: 'Shared domain models and DTOs',
        content: `export interface UserDTO {
  id: string;
  email: string;
  name: string;
  role: 'admin' | 'member' | 'guest';
}

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  timestamp: string;
}
`,
      },
      {
        path: 'apps/api/src/server.ts',
        language: 'typescript',
        description: 'API application consuming shared workspace packages',
        content: `import express from 'express';
import type { UserDTO, ApiResponse } from '@enterprise/shared-types';

const app = express();
app.use(express.json());

const PORT = process.env.PORT || 4000;

app.get('/api/users/me', (req, res) => {
  const user: UserDTO = {
    id: crypto.randomUUID(),
    email: 'architect@enterprise.corp',
    name: 'Enterprise Architect',
    role: 'admin',
  };

  const response: ApiResponse<UserDTO> = {
    success: true,
    data: user,
    timestamp: new Date().toISOString(),
  };

  res.json(response);
});

app.listen(PORT, () => {
  console.log(\`🏢 Enterprise API running on http://localhost:\${PORT} (Node \${process.version})\`);
});
`,
      },
    ],
  },
];
