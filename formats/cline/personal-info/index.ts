// なぜか以下のエラーが発生して解消できない
// Error: JSON.stringify cannot serialize cyclic structures.

import { type AgentPlugin, createTool } from "@cline/sdk"

const personalInfoPlugin: AgentPlugin = {
  name: "personal-info",
  manifest: { capabilities: ["tools"] },
  setup(api) {
    api.registerTool(
      createTool({
        name: "get_personal_info",
        description:
          "Returns fictional personal information as JSON and a marker confirming that this tool was called.",
        inputSchema: {
          type: "object",
          properties: {},
          additionalProperties: false,
        },
        execute: async () => {
          return {
            name: "Cline Plugin Tester",
            email: "cline-tester@example.test",
            timezone: "Asia/Tokyo",
          }
        },
      })
    )
  },
}

export { personalInfoPlugin };
export default personalInfoPlugin
