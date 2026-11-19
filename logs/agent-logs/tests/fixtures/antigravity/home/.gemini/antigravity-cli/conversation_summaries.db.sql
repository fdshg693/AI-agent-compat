CREATE TABLE conversation_summaries (
  conversation_id TEXT PRIMARY KEY,
  title TEXT,
  preview TEXT,
  step_count INTEGER,
  last_modified_time datetime,
  workspace_uris TEXT,
  status TEXT,
  source TEXT,
  project_id TEXT,
  agent_name TEXT,
  parent_conversation_id TEXT,
  nesting_depth INTEGER,
  battle_id TEXT,
  winning_conversation_id TEXT,
  not_fully_idle numeric,
  killed numeric,
  last_user_input_time datetime,
  last_user_input_step_index INTEGER,
  app_data_dir TEXT,
  raw_summary BLOB,
  group_id TEXT
);
INSERT INTO conversation_summaries VALUES
 ('cccccccc-0000-4000-8000-000000000003', 'CLI copy', 'Deploy', 2,
  '2026-01-07 12:00:00.0000000+00:00', '["file:///d%3A/work/old"]', 'CASCADE_RUN_STATUS_IDLE',
  'CORTEX_TRAJECTORY_SOURCE_CLI', '', '', '', 0, '', '', 0, 0,
  '0001-01-01 00:00:00+00:00', 0, 'antigravity-cli', NULL, '');
