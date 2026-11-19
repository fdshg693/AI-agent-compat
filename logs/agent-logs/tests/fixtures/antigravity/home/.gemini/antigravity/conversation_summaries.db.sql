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
 ('aaaaaaaa-0000-4000-8000-000000000001', 'Summary title A', 'Summarize', 8,
  '2026-01-10 09:00:10.1234567+00:00', '["file:///c%3A/Users/alice/proj"]', 'CASCADE_RUN_STATUS_IDLE',
  '', '00000000-0000-4000-8000-0000000000f1', '', '', 0, '', '', 0, 0,
  '2026-01-10 09:00:00.0000000+00:00', 0, 'antigravity', NULL, ''),
 ('bbbbbbbb-0000-4000-8000-000000000002', 'Research subagent', 'Look up', 12,
  '2026-01-12 10:30:00.5000000+00:00', '[]', 'CASCADE_RUN_STATUS_IDLE',
  'CORTEX_TRAJECTORY_SOURCE_CLI', '00000000-0000-4000-8000-0000000000f1', 'research',
  'aaaaaaaa-0000-4000-8000-000000000001', 1, '', '', 0, 0,
  '0001-01-01 00:00:00+00:00', 0, 'antigravity', NULL, ''),
 ('cccccccc-0000-4000-8000-000000000003', '', 'Deploy the site
second line', 3,
  '2026-01-08 12:00:00.0000000+00:00', '["file:///d%3A/work/site/"]', 'CASCADE_RUN_STATUS_IDLE',
  '', '', '', '', 0, '', '', 0, 0, '0001-01-01 00:00:00+00:00', 0, 'antigravity', NULL, '');
CREATE TABLE conversation_parents (conversation_id TEXT, parent_id TEXT);
