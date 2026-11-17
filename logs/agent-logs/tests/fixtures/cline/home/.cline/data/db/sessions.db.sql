CREATE TABLE sessions (
  session_id TEXT PRIMARY KEY, source TEXT, pid INTEGER, started_at TEXT, ended_at TEXT,
  exit_code INTEGER, status TEXT, status_lock INTEGER, interactive INTEGER, provider TEXT,
  model TEXT, cwd TEXT, workspace_root TEXT, team_name TEXT, enable_tools INTEGER,
  enable_spawn INTEGER, enable_teams INTEGER, parent_session_id TEXT, parent_agent_id TEXT,
  agent_id TEXT, conversation_id TEXT, is_subagent INTEGER, prompt TEXT, metadata_json TEXT,
  transcript_path TEXT, hook_path TEXT, messages_path TEXT, updated_at TEXT
);
CREATE TABLE subagent_spawn_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT);
CREATE TABLE schedules (id TEXT PRIMARY KEY);
CREATE TABLE schedule_executions (id TEXT PRIMARY KEY, tokens_used INTEGER, cost_usd REAL);
INSERT INTO sessions (session_id, source, started_at, cwd, workspace_root, is_subagent, metadata_json)
  VALUES ('1780000000000_aaaaa', 'cli', '2026-05-28T20:26:40.000Z', 'C:\Users\alice\proj\sub', 'c:\Users\alice\proj', 0, '{}');
INSERT INTO sessions (session_id, source, started_at, cwd, is_subagent, metadata_json)
  VALUES ('1780000100000_bbbbb', 'vscode', '2026-05-29T00:15:00.000Z', 'c:\Users\alice\other', 0, '{}');
INSERT INTO sessions (session_id, source, started_at, cwd, is_subagent, parent_session_id, metadata_json)
  VALUES ('1780000200000_ccccc', 'cli', '2026-05-29T04:03:20.000Z', 'C:\Users\alice\proj', 1, '1780000000000_aaaaa', '{}');
INSERT INTO sessions (session_id, source, started_at, ended_at, model, cwd, workspace_root, is_subagent, prompt, metadata_json, messages_path)
  VALUES ('1780000300000_ddddd', 'cli', '2026-05-29T07:50:00.000Z', '2026-05-29T07:55:00.000Z', 'example-model',
          'C:\Users\alice\gone', 'C:\Users\alice\gone', 0, 'Gone prompt',
          '{"title":"Gone session","usage":{"inputTokens":5,"outputTokens":2,"cacheReadTokens":0,"cacheWriteTokens":0,"totalCost":0.0005}}',
          'C:\Users\alice\.cline\data\sessions\1780000300000_ddddd\1780000300000_ddddd.messages.json');
