// Real location: .kilo/plugin/env-guard.ts (global: ~/.config/kilo/plugin/). Auto-discovered, no manifest.
import type { Plugin } from "@kilocode/plugin";

const envGuard: Plugin = async () => ({
  "tool.execute.before": async (input, output) => {
    if (input.tool === "read" && String(output.args.filePath).includes(".env")) {
      throw new Error("reading .env files is blocked");
    }
  },
});

export default { id: "env-guard", server: envGuard };
