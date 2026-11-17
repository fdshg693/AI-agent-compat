// Kilo sidecar for the `notify` scenario: relays Kilo events to the sibling
// notify.py, which decides whether to post or remove a macOS notification.
//
// This file only relays events, resolves the root session ID (the notification
// identifier) and fetches the last assistant reply on idle. Python gets one
// JSON object on stdin: { event, id, root, cwd, body, properties }.
// Payloads arrive in the v2 SDK shape; the Event type of @kilocode/plugin is the
// older v1 definition, so this file does not rely on it.
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Plugin } from "@kilocode/plugin";

// Events whose properties are relayed as-is (root resolved from properties.sessionID).
const RELAYED = new Set([
  "permission.asked",
  "permission.replied",
  "question.asked",
  "question.replied",
  "question.rejected",
]);

// Upper bound for one Python run, so a stuck child never stalls the queue.
const PYTHON_TIMEOUT_MS = 15_000;
const BODY_LIMIT = 500;

interface Resolved {
  id: string;
  root: boolean;
  cwd: string;
}

function pluginDir(): string {
  try {
    return path.dirname(fileURLToPath(import.meta.url));
  } catch {
    return process.cwd();
  }
}

function pythonScript(): string | null {
  const source = path.join(pluginDir(), "notify.py");
  return existsSync(source) ? source : null;
}

function pythonCommands(): string[] {
  return process.platform === "win32" ? ["python", "python3"] : ["python3", "python"];
}

// Run notify.py once and wait for it to exit. Falls back to the next command
// only when the interpreter itself cannot be started. Never rejects.
function runOnce(cmd: string, script: string, stdin: string): Promise<"ok" | "missing"> {
  return new Promise((resolve) => {
    let child: ReturnType<typeof spawn>;
    try {
      child = spawn(cmd, [script], {
        stdio: ["pipe", "ignore", "pipe"],
        timeout: PYTHON_TIMEOUT_MS,
        windowsHide: true,
      });
    } catch {
      resolve("missing");
      return;
    }
    let stderr = "";
    let settled = false;
    const done = (value: "ok" | "missing") => {
      if (!settled) {
        settled = true;
        resolve(value);
      }
    };
    child.stderr?.on("data", (chunk) => (stderr += chunk));
    child.on("error", (error: NodeJS.ErrnoException) => {
      done(error.code === "ENOENT" ? "missing" : "ok");
    });
    child.on("close", () => {
      if (stderr) console.error("notify:", stderr.trimEnd());
      done("ok");
    });
    child.stdin?.on("error", () => {});
    child.stdin?.end(stdin);
  });
}

async function runPython(script: string, payload: Record<string, unknown>): Promise<void> {
  const stdin = JSON.stringify(payload);
  for (const cmd of pythonCommands()) {
    if ((await runOnce(cmd, script, stdin)) === "ok") return;
  }
  console.error("notify: python3 / python not found");
}

const notify: Plugin = async ({ client, directory, worktree }) => {
  const fallbackCwd = directory || worktree || process.cwd();
  const script = pythonScript();
  // The SDK client is typed for v1 payloads; use it loosely.
  const sdk = client as any;

  // session ID -> { id: root ID, root: is itself the root, cwd: root directory }.
  // Parent links and directories never change, so the promise is cached.
  const sessions = new Map<string, Promise<Resolved>>();
  const resolveSession = (sessionID: string): Promise<Resolved> => {
    let entry = sessions.get(sessionID);
    if (!entry) {
      entry = (async (): Promise<Resolved> => {
        const { data: session } = await sdk.session.get({ path: { id: sessionID } });
        if (!session) throw new Error(`session not found: ${sessionID}`);
        if (!session.parentID) {
          return { id: sessionID, root: true, cwd: session.directory || fallbackCwd };
        }
        return { ...(await resolveSession(session.parentID)), root: false };
      })();
      entry.catch(() => sessions.delete(sessionID));
      sessions.set(sessionID, entry);
    }
    return entry;
  };

  // Every event goes through one serial queue: root resolution is async, so
  // per-ID handling could let permission.replied overtake permission.asked.
  // Handlers never await the queue, so Kilo is not blocked.
  let queue: Promise<void> = Promise.resolve();
  const enqueue = (task: () => Promise<void>) => {
    queue = queue.then(task).catch((error) => console.error("notify:", error));
  };

  const lastAssistantText = async (sessionID: string): Promise<string> => {
    const { data: messages } = await sdk.session.messages({ path: { id: sessionID } });
    const list: any[] = Array.isArray(messages) ? messages : [];
    const last = [...list].reverse().find((message) => message?.info?.role === "assistant");
    const parts: any[] = Array.isArray(last?.parts) ? last.parts : [];
    const text = parts
      .filter((part) => part?.type === "text" && !part.synthetic)
      .map((part) => String(part.text ?? ""))
      .join("\n");
    return Array.from(text).slice(0, BODY_LIMIT).join("");
  };

  const relay = (payload: Record<string, unknown>) =>
    script ? runPython(script, payload) : Promise.resolve();

  return {
    event: async ({ event }) => {
      try {
        if (!script) return;
        const { type, properties } = (event ?? {}) as { type?: string; properties?: any };
        const props = properties ?? {};
        if (type === "session.status") {
          // Frequent; anything other than idle never starts Python.
          if (props.status?.type !== "idle") return;
          enqueue(async () => {
            const session = await resolveSession(props.sessionID);
            // Child idles are not notified, so skip fetching the body as well.
            if (!session.root) return;
            const body = await lastAssistantText(props.sessionID);
            await relay({ event: type, ...session, body, properties: props });
          });
        } else if (type && RELAYED.has(type)) {
          enqueue(async () =>
            relay({ event: type, ...(await resolveSession(props.sessionID)), properties: props }),
          );
        } else if (type === "session.deleted") {
          // Already deleted, so it cannot be fetched: judge from info.
          const info = props.info ?? {};
          const sessionID = props.sessionID || info.id;
          if (!sessionID) return;
          sessions.delete(sessionID);
          enqueue(() =>
            relay({
              event: type,
              id: sessionID,
              root: !info.parentID,
              cwd: info.directory || fallbackCwd,
              properties: {},
            }),
          );
        }
      } catch (error) {
        console.error("notify:", error);
      }
    },
    // Called once per user request. Spawning a subagent also calls it with the
    // child sessionID; Python ignores non-root ones.
    "chat.message": async (input) => {
      try {
        if (!script) return;
        const sessionID = (input as { sessionID?: string })?.sessionID;
        if (!sessionID) return;
        enqueue(async () =>
          relay({ event: "chat.message", ...(await resolveSession(sessionID)), properties: {} }),
        );
      } catch (error) {
        console.error("notify:", error);
      }
    },
  };
};

export default { id: "notify", server: notify };
