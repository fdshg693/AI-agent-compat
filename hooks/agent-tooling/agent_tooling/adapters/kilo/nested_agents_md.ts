import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Plugin } from "@kilocode/plugin";

const TARGET_TOOLS = new Set([
  "read",
  "edit",
  "write",
  "apply_patch",
  "bash",
  "glob",
  "grep",
]);

function pluginDir(): string {
  try {
    return path.dirname(fileURLToPath(import.meta.url));
  } catch {
    return process.cwd();
  }
}

function pythonScript(): string | null {
  const here = pluginDir();
  const completeName = path.join(here, "inject_nested_agents_md.py");
  if (existsSync(completeName)) {
    return completeName;
  }
  const sourceName = path.join(here, "nested_agents_md.py");
  return existsSync(sourceName) ? sourceName : null;
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

const nestedAgentsMd: Plugin = async ({ directory, worktree }) => {
  const cwd = directory || worktree || process.cwd();
  const script = pythonScript();

  return {
    "tool.execute.after": async (input, output) => {
      try {
        if (!script || !TARGET_TOOLS.has(String(input.tool))) {
          return;
        }
        const sessionID =
          (input as { sessionID?: string }).sessionID || "unknown";
        const args =
          (input as { args?: Record<string, unknown> }).args ??
          (output as { args?: Record<string, unknown> }).args ??
          {};
        const result = runPython(
          script,
          JSON.stringify({
            session_id: sessionID,
            cwd,
            tool_name: input.tool,
            tool_input: args,
          }),
        );
        if (!result) {
          return;
        }
        const stdout = (result.stdout || "").trim();
        if (!stdout) {
          return;
        }
        let parsed: { additionalContext?: unknown };
        try {
          parsed = JSON.parse(stdout) as { additionalContext?: unknown };
        } catch {
          return;
        }
        const extra = parsed.additionalContext;
        if (typeof extra !== "string" || !extra.trim()) {
          return;
        }
        const current = typeof output.output === "string" ? output.output : "";
        output.output =
          current +
          "\n\n<system-reminder>\n" +
          extra +
          "\n</system-reminder>\n";
      } catch {
        // Observational hook: never fail the tool.
      }
    },
  };
};

export default { id: "nested-agents-md", server: nestedAgentsMd };
