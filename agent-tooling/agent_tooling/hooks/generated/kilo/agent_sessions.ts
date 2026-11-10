import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Plugin } from "@kilocode/plugin";

function pluginDir(): string {
  try {
    return path.dirname(fileURLToPath(import.meta.url));
  } catch {
    return process.cwd();
  }
}

function pythonScript(): string | null {
  const source = path.join(pluginDir(), "agent_sessions.py");
  return existsSync(source) ? source : null;
}

function runPython(script: string, stdin: string) {
  const cmds =
    process.platform === "win32" ? ["python", "python3"] : ["python3", "python"];
  for (const cmd of cmds) {
    const result = spawnSync(cmd, [script], {
      input: stdin,
      encoding: "utf8",
      timeout: 15_000,
      windowsHide: true,
    });
    if (!result.error && result.status === 0) {
      return result;
    }
  }
  return null;
}

interface SessionInfo {
  id?: unknown;
  directory?: unknown;
}

function sessionPayload(
  event: unknown,
  fallbackCwd: string,
): Record<string, unknown> | null {
  const typed = event as
    | { type?: string; properties?: { info?: SessionInfo } }
    | null
    | undefined;
  const type = typed?.type;
  const info = typed?.properties?.info;
  const id = info?.id;
  if (typeof id !== "string" || !id) {
    return null;
  }
  const directory =
    typeof info?.directory === "string" && info.directory
      ? info.directory
      : fallbackCwd;
  const base = {
    session_id: id,
    pid: process.pid,
    pid_source: "host",
    event: type,
  };
  if (type === "session.created") {
    return { ...base, action: "start", cwd: directory };
  }
  if (type === "session.deleted") {
    return { ...base, action: "end" };
  }
  if (type === "session.updated" && typeof info?.directory === "string" && info.directory) {
    return { ...base, action: "cwd", cwd: info.directory };
  }
  return null;
}

const agentSessions: Plugin = async ({ directory, worktree }) => {
  const fallbackCwd = directory || worktree || process.cwd();
  const script = pythonScript();

  return {
    event: async ({ event }) => {
      try {
        if (!script) {
          return;
        }
        const payload = sessionPayload(event, fallbackCwd);
        if (!payload) {
          return;
        }
        runPython(script, JSON.stringify(payload));
      } catch {
        // Observational hook: never fail the session.
      }
    },
  };
};

export default { id: "agent-sessions", server: agentSessions };
