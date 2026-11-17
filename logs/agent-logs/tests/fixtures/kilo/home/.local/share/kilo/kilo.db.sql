-- Fictional Kilo Code v7 database (user "alice"). Column names follow the kilo-logs spec.
-- Times are epoch ms: 1768003200000 = 2026-01-10T00:00:00Z, 1794268800000 = 2026-11-10T00:00:00Z.

CREATE TABLE `project` (
  `id` text PRIMARY KEY, `worktree` text NOT NULL, `vcs` text, `name` text,
  `icon_url` text, `icon_color` text, `time_created` integer NOT NULL,
  `time_updated` integer NOT NULL, `time_initialized` integer, `sandboxes` text, `commands` text
);
CREATE TABLE `session` (
  `id` text PRIMARY KEY, `project_id` text NOT NULL, `workspace_id` text, `parent_id` text,
  `slug` text NOT NULL, `directory` text NOT NULL, `path` text, `title` text NOT NULL,
  `version` text NOT NULL, `share_url` text, `summary_additions` integer, `summary_deletions` integer,
  `summary_files` integer, `summary_diffs` text, `metadata` text, `cost` real DEFAULT 0 NOT NULL,
  `tokens_input` integer DEFAULT 0 NOT NULL, `tokens_output` integer DEFAULT 0 NOT NULL,
  `tokens_reasoning` integer DEFAULT 0 NOT NULL, `tokens_cache_read` integer DEFAULT 0 NOT NULL,
  `tokens_cache_write` integer DEFAULT 0 NOT NULL, `revert` text, `permission` text, `agent` text,
  `model` text, `time_created` integer NOT NULL, `time_updated` integer NOT NULL,
  `time_compacting` integer, `time_archived` integer
);
CREATE INDEX `session_project_idx` ON `session` (`project_id`);
CREATE INDEX `session_parent_idx` ON `session` (`parent_id`);
CREATE TABLE `message` (
  `id` text PRIMARY KEY, `session_id` text NOT NULL, `time_created` integer NOT NULL,
  `time_updated` integer NOT NULL, `data` text NOT NULL
);
CREATE INDEX `message_session_time_created_id_idx` ON `message` (`session_id`,`time_created`,`id`);
CREATE TABLE `part` (
  `id` text PRIMARY KEY, `message_id` text NOT NULL, `session_id` text NOT NULL,
  `time_created` integer NOT NULL, `time_updated` integer NOT NULL, `data` text NOT NULL
);
CREATE INDEX `part_message_id_id_idx` ON `part` (`message_id`,`id`);
CREATE INDEX `part_session_idx` ON `part` (`session_id`);

-- Secret tables that must never be SELECTed.
CREATE TABLE `account` (`id` text PRIMARY KEY, `email` text, `access_token` text, `refresh_token` text);
INSERT INTO `account` VALUES ('acc_1', 'alice@example.invalid', 'FAKE-SECRET-access-token-kilo', 'FAKE-SECRET-refresh-token-kilo');
CREATE TABLE `credential` (`id` text PRIMARY KEY, `provider` text, `value` text);
INSERT INTO `credential` VALUES ('cred_1', 'example-provider', 'FAKE-SECRET-credential-kilo');

INSERT INTO `project` VALUES
  ('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'C:/Users/alice/proj', 'git', 'proj', NULL, NULL, 1768003200000, 1768003200000, NULL, '[]', NULL),
  ('global', '/', NULL, NULL, NULL, NULL, 1768003200000, 1768003200000, NULL, '[]', NULL);

-- Session IDs sort descending: the newest has the smallest id.
INSERT INTO `session` (id, project_id, parent_id, slug, directory, path, title, version, metadata, cost,
  tokens_input, tokens_output, tokens_reasoning, tokens_cache_read, tokens_cache_write, agent, model,
  time_created, time_updated) VALUES
  ('ses_0000000000000000000000000c', 'global', NULL, 'quiet-fox', 'c:/Users/alice/scratch', '', 'Scratch notes',
   '7.8.27', '{}', 0, 0, 0, 0, 0, 0, 'code', '{"id":"example-model-b","providerID":"example-provider"}',
   1794268800000, 1794268860000),
  ('ses_0000000000000000000000000x', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'ses_0000000000000000000000000y',
   'brave-owl', 'C:/Users/alice/proj', '', 'Find TODOs (@explore subagent)', '7.8.27', '{}', 0,
   200, 20, 0, 0, 0, 'explore', '{"id":"example-model","providerID":"example-provider"}',
   1768003230000, 1768003240000),
  ('ses_0000000000000000000000000y', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', NULL, 'calm-cat',
   'C:/Users/alice/proj/sub', 'sub', 'List files', '7.8.27', '{"kilocode.sandbox":false}', 0.12,
   1500, 60, 10, 800, 40, 'code', '{"id":"example-model","providerID":"example-provider","variant":"high"}',
   1768003200000, 1768003290000);

-- Main session: user prompt, two assistant steps.
INSERT INTO `message` VALUES
  ('msg_0001', 'ses_0000000000000000000000000y', 1768003200000, 1768003200000,
   '{"role":"user","time":{"created":1768003200000},"agent":"code","model":{"providerID":"example-provider","modelID":"example-model"}}'),
  ('msg_0002', 'ses_0000000000000000000000000y', 1768003210000, 1768003220000,
   '{"role":"assistant","parentID":"msg_0001","agent":"code","mode":"code","providerID":"example-provider","modelID":"example-model","path":{"cwd":"C:/Users/alice/proj/sub","root":"C:/Users/alice/proj"},"time":{"created":1768003210000,"completed":1768003220000},"tokens":{"input":1000,"output":40,"reasoning":10,"total":1850,"cache":{"read":800,"write":0}},"cost":0.1,"finish":"tool-calls"}'),
  ('msg_0003', 'ses_0000000000000000000000000y', 1768003250000, 1768003290000,
   '{"role":"assistant","parentID":"msg_0001","agent":"code","mode":"code","providerID":"example-provider","modelID":"example-model","time":{"created":1768003250000,"completed":1768003290000},"tokens":{"input":500,"output":20,"reasoning":0,"total":560,"cache":{"read":0,"write":40}},"cost":0.02,"finish":"stop"}');

INSERT INTO `part` VALUES
  ('prt_0001', 'msg_0001', 'ses_0000000000000000000000000y', 1768003200000, 1768003200000,
   '{"type":"text","text":"Please list the files in this folder"}'),
  ('prt_0002', 'msg_0001', 'ses_0000000000000000000000000y', 1768003200000, 1768003200000,
   '{"type":"file","filename":"notes.txt","mime":"text/plain","url":"data:text/plain;base64,RkFLRS1TRUNSRVQtaW4tZGF0YS11cmw="}'),
  ('prt_0003', 'msg_0002', 'ses_0000000000000000000000000y', 1768003210000, 1768003210000,
   '{"type":"step-start","time":{"start":1768003210000}}'),
  ('prt_0004', 'msg_0002', 'ses_0000000000000000000000000y', 1768003211000, 1768003211000,
   '{"type":"reasoning","text":"I should run ls.","time":{"start":1768003211000,"end":1768003212000},"metadata":{}}'),
  ('prt_0005', 'msg_0002', 'ses_0000000000000000000000000y', 1768003213000, 1768003215000,
   '{"type":"tool","tool":"bash","callID":"call_1","state":{"status":"completed","input":{"command":"ls"},"output":"README.md\nsrc","title":"ls","metadata":{"truncated":false},"time":{"start":1768003213000,"end":1768003215000}}}'),
  ('prt_0006', 'msg_0002', 'ses_0000000000000000000000000y', 1768003216000, 1768003216000,
   '{"type":"tool","tool":"task","callID":"call_2","state":{"status":"completed","input":{"description":"Find TODOs","subagent_type":"explore"},"output":"none found","metadata":{"sessionId":"ses_0000000000000000000000000x"},"time":{"start":1768003216000,"end":1768003245000}}}'),
  ('prt_0007', 'msg_0002', 'ses_0000000000000000000000000y', 1768003220000, 1768003220000,
   '{"type":"step-finish","reason":"tool-calls","cost":0.1,"tokens":{"input":1000,"output":40,"reasoning":10,"total":1850,"cache":{"read":800,"write":0}},"time":{"start":1768003210000,"end":1768003220000,"elapsed":10000}}'),
  ('prt_0008', 'msg_0003', 'ses_0000000000000000000000000y', 1768003250000, 1768003250000,
   '{"type":"step-start","time":{"start":1768003250000}}'),
  ('prt_0009', 'msg_0003', 'ses_0000000000000000000000000y', 1768003260000, 1768003260000,
   '{"type":"tool","tool":"read","callID":"call_3","state":{"status":"error","input":{"filePath":"C:/Users/alice/proj/missing.md"},"error":"File not found","time":{"start":1768003260000,"end":1768003261000}}}'),
  ('prt_0010', 'msg_0003', 'ses_0000000000000000000000000y', 1768003280000, 1768003280000,
   '{"type":"text","text":"The folder has README.md and src.","time":{"start":1768003280000,"end":1768003285000}}'),
  ('prt_0011', 'msg_0003', 'ses_0000000000000000000000000y', 1768003290000, 1768003290000,
   '{"type":"step-finish","reason":"stop","cost":0.02,"tokens":{"input":500,"output":20,"reasoning":0,"total":560,"cache":{"read":0,"write":40}},"time":{"start":1768003250000,"end":1768003290000,"elapsed":40000}}'),
  ('prt_0012', 'msg_0003', 'ses_0000000000000000000000000y', 1768003290000, 1768003290000,
   '{"type":"brand-new-part-type","value":1}');

-- Subagent session.
INSERT INTO `message` VALUES
  ('msg_0101', 'ses_0000000000000000000000000x', 1768003230000, 1768003230000,
   '{"role":"user","time":{"created":1768003230000},"agent":"explore"}'),
  ('msg_0102', 'ses_0000000000000000000000000x', 1768003235000, 1768003240000,
   '{"role":"assistant","parentID":"msg_0101","providerID":"example-provider","modelID":"example-model","time":{"created":1768003235000,"completed":1768003240000},"tokens":{"input":200,"output":20,"reasoning":0,"total":220,"cache":{"read":0,"write":0}},"cost":0,"finish":"stop"}');
INSERT INTO `part` VALUES
  ('prt_0101', 'msg_0101', 'ses_0000000000000000000000000x', 1768003230000, 1768003230000,
   '{"type":"text","text":"Find TODO comments"}'),
  ('prt_0102', 'msg_0102', 'ses_0000000000000000000000000x', 1768003238000, 1768003238000,
   '{"type":"text","text":"none found"}');

-- Recent session: assistant message that failed before producing parts.
INSERT INTO `message` VALUES
  ('msg_0201', 'ses_0000000000000000000000000c', 1794268800000, 1794268800000,
   '{"role":"user","time":{"created":1794268800000}}'),
  ('msg_0202', 'ses_0000000000000000000000000c', 1794268810000, 1794268860000,
   '{"role":"assistant","parentID":"msg_0201","providerID":"example-provider","modelID":"example-model-b","time":{"created":1794268810000},"tokens":{"input":0,"output":0,"reasoning":0,"total":0,"cache":{"read":0,"write":0}},"cost":0,"error":{"name":"APIError","data":{"message":"rate limited"}}}');
INSERT INTO `part` VALUES
  ('prt_0201', 'msg_0201', 'ses_0000000000000000000000000c', 1794268800000, 1794268800000,
   '{"type":"text","text":"Summarize the scratch notes"}'),
  ('prt_0202', 'msg_0201', 'ses_0000000000000000000000000c', 1794268800000, 1794268800000,
   '{"type":"text","text":"(synthetic editor context)","synthetic":true}');
