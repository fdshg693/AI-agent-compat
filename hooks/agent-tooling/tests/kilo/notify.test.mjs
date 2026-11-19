// generated/kilo/notify.ts（TS sidecar）の単体テスト。test_notify_adapters.py から `node --test` で起動する。
// sidecar を一時ディレクトリへコピーし、隣に偽の notify.py（stdin を RESULT に 1 行ずつ追記）を置く。
import { strict as assert } from "node:assert";
import { copyFile, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { afterEach, beforeEach, test } from "node:test";
import { setTimeout as sleep } from "node:timers/promises";

const SIDECAR = process.env.KILO_NOTIFY_TS;
assert.ok(SIDECAR, "KILO_NOTIFY_TS is required");

// permission.asked のときだけ遅らせ、後続の呼び出しが追い越さないことを確かめられるようにする
const fakePython = `import json, os, sys, time
data = sys.stdin.read()
if json.loads(data).get("event") == "permission.asked":
    time.sleep(0.3)
with open(os.environ["RESULT"], "a", encoding="utf-8") as f:
    f.write(data + "\\n")
`;

let dir;
let plugin;

beforeEach(async () => {
  dir = await mkdtemp(join(tmpdir(), "kilo-notify-"));
  await copyFile(SIDECAR, join(dir, "notify.ts"));
  await writeFile(join(dir, "notify.py"), fakePython);
  process.env.RESULT = join(dir, "result");
  ({ default: plugin } = await import(pathToFileURL(join(dir, "notify.ts")).href));
});

afterEach(async () => {
  await rm(dir, { recursive: true, force: true });
});

// ses_root（/project）と、その子 ses_child・孫 ses_grandchild
const sessions = {
  ses_root: { id: "ses_root", directory: "/project" },
  ses_child: { id: "ses_child", directory: "/project", parentID: "ses_root" },
  ses_grandchild: { id: "ses_grandchild", directory: "/project", parentID: "ses_child" },
};

const setup = async () => {
  const calls = { get: 0, messages: 0 };
  const client = {
    session: {
      get: async ({ path }) => {
        calls.get++;
        return { data: sessions[path.id] };
      },
      messages: async () => {
        calls.messages++;
        return {
          data: [
            { info: { role: "assistant" }, parts: [{ type: "text", text: "old" }] },
            { info: { role: "user" }, parts: [{ type: "text", text: "q" }] },
            {
              info: { role: "assistant" },
              parts: [{ type: "text", text: "finished" }, { type: "text", text: "x", synthetic: true }],
            },
          ],
        };
      },
    },
  };
  const hooks = await plugin.server({ client, directory: "/fallback", worktree: "/fallback" });
  const event = (type, properties) => hooks.event({ event: { type, properties } });
  return { hooks, event, calls };
};

const results = async (n) => {
  for (let i = 0; i < 250; i++) {
    const lines = await readFile(process.env.RESULT, "utf8").then(
      (s) => s.trim().split("\n").filter(Boolean),
      () => [],
    );
    if (lines.length >= n) return lines.map((line) => JSON.parse(line));
    await sleep(20);
  }
  assert.fail(`notify.py was not called ${n} times`);
};

// 無視されるイベントのあとに、必ず中継されるイベントを送って、それだけが届くことを確かめる
const sentinel = (event) => event("question.replied", { sessionID: "ses_root", requestID: "sentinel" });

test("plugin id is notify", () => {
  assert.equal(plugin.id, "notify");
});

test("idle is relayed for the root only, with the last assistant text as body", async () => {
  const { event, calls } = await setup();
  await event("session.status", { sessionID: "ses_root", status: { type: "busy" } });
  await event("session.status", { sessionID: "ses_child", status: { type: "idle" } });
  await event("session.status", { sessionID: "ses_root", status: { type: "idle" } });
  const [got] = await results(1);
  assert.deepEqual(
    { event: got.event, id: got.id, root: got.root, cwd: got.cwd, body: got.body },
    { event: "session.status", id: "ses_root", root: true, cwd: "/project", body: "finished" },
  );
  await sentinel(event);
  assert.equal((await results(2)).length, 2);
  assert.equal(calls.messages, 1);
});

test("descendant permission/question use the root ID", async () => {
  const { event } = await setup();
  const permission = { id: "per_1", sessionID: "ses_grandchild", permission: "bash", patterns: ["git push"] };
  await event("permission.asked", permission);
  await event("question.asked", { id: "que_1", sessionID: "ses_child", questions: [{ question: "Q?" }] });
  const [p, q] = await results(2);
  assert.deepEqual(
    { event: p.event, id: p.id, root: p.root, cwd: p.cwd, properties: p.properties },
    { event: "permission.asked", id: "ses_root", root: false, cwd: "/project", properties: permission },
  );
  assert.deepEqual({ event: q.event, id: q.id, root: q.root }, { event: "question.asked", id: "ses_root", root: false });
});

test("a remove right after a post does not overtake it", async () => {
  const { event } = await setup();
  await event("permission.asked", { id: "per_1", sessionID: "ses_child", permission: "edit", patterns: ["a"] });
  await event("permission.replied", { sessionID: "ses_child", requestID: "per_1", reply: "once" });
  await event("question.rejected", { sessionID: "ses_root", requestID: "que_1" });
  const got = await results(3);
  assert.deepEqual(got.map((r) => [r.event, r.id]), [
    ["permission.asked", "ses_root"],
    ["permission.replied", "ses_root"],
    ["question.rejected", "ses_root"],
  ]);
});

test("chat.message is relayed with root (children are ignored by Python)", async () => {
  const { hooks } = await setup();
  await hooks["chat.message"]({ sessionID: "ses_child" }, { message: {}, parts: [] });
  await hooks["chat.message"]({ sessionID: "ses_root" }, { message: {}, parts: [] });
  const got = await results(2);
  assert.deepEqual(got.map((r) => [r.event, r.id, r.root]), [
    ["chat.message", "ses_root", false],
    ["chat.message", "ses_root", true],
  ]);
});

test("session.deleted is judged from info without get", async () => {
  const { event, calls } = await setup();
  await event("session.deleted", { sessionID: "ses_gone", info: { id: "ses_gone", directory: "/gone" } });
  await event("session.deleted", { sessionID: "ses_gone_child", info: { id: "ses_gone_child", parentID: "ses_gone" } });
  const got = await results(2);
  assert.deepEqual(got.map((r) => [r.event, r.id, r.root, r.cwd]), [
    ["session.deleted", "ses_gone", true, "/gone"],
    ["session.deleted", "ses_gone_child", false, "/fallback"],
  ]);
  assert.equal(calls.get, 0);
});

test("session parents are cached", async () => {
  const { event, calls } = await setup();
  await event("permission.asked", { id: "per_1", sessionID: "ses_child", permission: "edit", patterns: [] });
  await event("permission.replied", { sessionID: "ses_child", requestID: "per_1", reply: "once" });
  await results(2);
  assert.equal(calls.get, 2); // ses_child と ses_root を 1 回ずつ
});

test("unrelated events are not relayed", async () => {
  const { event } = await setup();
  await event("message.updated", { info: { sessionID: "ses_root", role: "user" } });
  await event("session.created", { info: { id: "ses_root" } });
  await sentinel(event);
  const got = await results(1);
  assert.deepEqual(got.map((r) => r.event), ["question.replied"]);
});

test("a failed lookup does not stop the queue or throw", async () => {
  const { event } = await setup();
  const original = console.error;
  console.error = () => {};
  try {
    await event("permission.asked", { id: "per_x", sessionID: "ses_unknown", permission: "edit" });
    await event(undefined, undefined);
    await sentinel(event);
    const got = await results(1);
    assert.deepEqual(got.map((r) => r.event), ["question.replied"]);
  } finally {
    console.error = original;
  }
});
