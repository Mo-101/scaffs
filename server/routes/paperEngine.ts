import { Router, type Request, type Response } from "express";
import { readFileSync, existsSync, readdirSync, statSync } from "fs";
import path from "path";

/**
 * Authoritative paper-trading routes.
 *
 * This router is a *file server*, deliberately. Every number it returns was
 * produced by `backend/agent/futures_paper_engine.py` and rendered by
 * `backend/paper_runtime/dto.py`; nothing here computes P&L, fees, funding or
 * a performance statistic. If a figure is wrong, it is wrong in the Python
 * ledger, which is the only place it can be fixed.
 *
 * That constraint is the whole point of the split: the previous dashboard
 * derived strategy "results" from counters mutated by an Express timer, so the
 * displayed performance was a property of the web tier rather than of any
 * trade. Keeping this layer incapable of arithmetic makes that class of bug
 * unrepresentable.
 *
 * Regenerate the underlying data with:
 *   cd backend && python3 -m paper_runtime.driver --days 14 --seed 7
 */

const ENGINE_OUT_DIR = path.resolve(process.cwd(), "backend/paper_runtime/out");

interface EngineIndex {
  schema_version: number;
  generated_at: string;
  mode: string;
  sessions: Array<Record<string, unknown>>;
}

function readJson<T>(file: string): T | null {
  try {
    if (!existsSync(file)) return null;
    return JSON.parse(readFileSync(file, "utf-8")) as T;
  } catch {
    return null;
  }
}

/**
 * A 503 with instructions beats an empty array: an unseeded engine and an
 * engine that legitimately holds no sessions must not look identical.
 */
function notGenerated(res: Response) {
  res.status(503).json({
    error: "paper_engine_output_missing",
    message:
      "No engine output found. Generate it with: " +
      "cd backend && python3 -m paper_runtime.driver --days 14 --seed 7",
    expected_dir: ENGINE_OUT_DIR,
  });
}

export function createPaperEngineRouter(): Router {
  const router = Router();

  router.get("/sessions", (_req: Request, res: Response) => {
    const index = readJson<EngineIndex>(path.join(ENGINE_OUT_DIR, "index.json"));
    if (!index) return notGenerated(res);
    res.json(index);
  });

  router.get("/sessions/:id", (req: Request, res: Response) => {
    // Reject traversal before touching the filesystem; ids come from the URL.
    const id = req.params.id;
    if (!/^[A-Za-z0-9_-]+$/.test(id)) {
      return res.status(400).json({ error: "invalid_session_id" });
    }
    const dto = readJson<Record<string, unknown>>(path.join(ENGINE_OUT_DIR, `${id}.json`));
    if (!dto) {
      const index = readJson<EngineIndex>(path.join(ENGINE_OUT_DIR, "index.json"));
      if (!index) return notGenerated(res);
      return res.status(404).json({ error: "unknown_session", session_id: id });
    }
    res.json(dto);
  });

  /** Provenance for the UI banner: which engine, generated when, from what. */
  router.get("/status", (_req: Request, res: Response) => {
    const indexPath = path.join(ENGINE_OUT_DIR, "index.json");
    const index = readJson<EngineIndex>(indexPath);
    if (!index) return notGenerated(res);
    const files = readdirSync(ENGINE_OUT_DIR).filter((f) => f.endsWith(".json"));
    res.json({
      mode: "paper_engine",
      engine: "backend/agent/futures_paper_engine.py",
      renderer: "backend/paper_runtime/dto.py",
      generated_at: index.generated_at,
      output_written_at: statSync(indexPath).mtime.toISOString(),
      session_count: index.sessions.length,
      files: files.length,
      computes_pnl_in_web_tier: false,
    });
  });

  return router;
}
