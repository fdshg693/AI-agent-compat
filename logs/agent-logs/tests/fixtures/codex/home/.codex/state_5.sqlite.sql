CREATE TABLE threads (
  id TEXT PRIMARY KEY,
  rollout_path TEXT,
  created_at INTEGER,
  updated_at INTEGER,
  source TEXT,
  cwd TEXT,
  title TEXT,
  name TEXT,
  model TEXT,
  tokens_used INTEGER,
  archived INTEGER,
  first_user_message TEXT
);
INSERT INTO threads VALUES ('00000000-0000-7000-8000-000000000001', 'C:\work\fake\rollout-1.jsonl', 1767323045, 1767323105, 'cli', 'C:\work\demo', 'Fix the demo build', NULL, 'gpt-fake-codex-mini', 300, 0, 'Fix the build in demo');
INSERT INTO threads VALUES ('00000000-0000-7000-8000-000000000002', 'C:\work\fake\rollout-2.jsonl', 1767430800, 1767430807, 'subagent', 'c:/work/demo/sub', 'db title for 2', 'db name for 2', 'gpt-fake-codex', 90, 0, 'Search for TODO comments');
INSERT INTO threads VALUES ('00000000-0000-7000-8000-000000000099', 'C:\work\fake\missing.jsonl', 1767430800, 1767430800, 'cli', 'C:\work\other', 'No rollout', NULL, 'gpt-fake', 0, 0, NULL);
