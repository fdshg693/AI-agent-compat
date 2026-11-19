import { spawn } from "node:child_process";
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
  const source = path.join(pluginDir(), "stop_alert.py");
  return existsSync(source) ? source : null;
}

// Fire-and-forget: the sound plays synchronously inside Python, so do not
// block Kilo's event loop. Try the next interpreter only if spawning fails.
function runPython(script: string, stdin: string, cmds: string[]): void {
  const [cmd, ...rest] = cmds;
  if (!cmd) {
    return;
  }
  try {
    const child = spawn(cmd, [script], {
      stdio: ["pipe", "ignore", "ignore"],
      windowsHide: true,
    });
    child.on("error", () => runPython(script, stdin, rest));
    child.stdin?.on("error", () => {});
    child.stdin?.end(stdin);
  } catch {
    runPython(script, stdin, rest);
  }
}

function idleSessionId(event: unknown): string | null {
  const typed = event as
    | { type?: string; properties?: { sessionID?: unknown } }
    | null
    | undefined;
  if (typed?.type !== "session.idle") {
    return null;
  }
  const id = typed.properties?.sessionID;
  return typeof id === "string" && id ? id : null;
}

// Subagent (task) sessions also go idle; only alert for top-level sessions.
// If the lookup fails, alert anyway.
async function sessionInfo(
  client: unknown,
  id: string,
): Promise<{ parentID?: unknown; directory?: unknown } | null> {
  try {
    const api = client as {
      session?: { get?: (opts: unknown) => Promise<{ data?: unknown }> };
    };
    const result = await api.session?.get?.({ path: { id } });
    const data = result?.data as { parentID?: unknown; directory?: unknown } | undefined;
    return data ?? null;
  } catch {
    return null;
  }
}

const stopAlert: Plugin = async ({ client, directory, worktree }) => {
  const fallbackCwd = directory || worktree || process.cwd();
  const script = pythonScript();
  const cmds =
    process.platform === "win32" ? ["python", "python3"] : ["python3", "python"];

  return {
    event: async ({ event }) => {
      try {
        if (!script) {
          return;
        }
        const id = idleSessionId(event);
        if (!id) {
          return;
        }
        const info = await sessionInfo(client, id);
        if (info && typeof info.parentID === "string" && info.parentID) {
          return;
        }
        const cwd =
          typeof info?.directory === "string" && info.directory
            ? info.directory
            : fallbackCwd;
        runPython(
          script,
          JSON.stringify({ session_id: id, cwd, event: "session.idle" }),
          cmds,
        );
      } catch {
        // Notification hook: never fail the session.
      }
    },
  };
};

export default { id: "stop-alert", server: stopAlert };
