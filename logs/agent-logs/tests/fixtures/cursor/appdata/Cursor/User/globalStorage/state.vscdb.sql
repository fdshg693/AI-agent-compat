-- Fictional IDE globalStorage/state.vscdb (same table shapes as Cursor 3.30).
CREATE TABLE ItemTable (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB);
CREATE TABLE cursorDiskKV (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB);
CREATE TABLE composerHeaders (composerId TEXT PRIMARY KEY, workspaceId TEXT, createdAt INTEGER, lastUpdatedAt INTEGER, isArchived INTEGER, isSubagent INTEGER, recency INTEGER, checkpointAt INTEGER, value TEXT, subagentTypeName TEXT);

INSERT INTO ItemTable VALUES ('secret:fake-provider', 'FAKE-SECRET-SHOULD-NOT-LEAK');
INSERT INTO ItemTable VALUES ('composer.composerHeaders.migratedToTable', 'true');

INSERT INTO composerHeaders VALUES ('e3e3e3e3-0000-4000-8000-000000000003', 'ws-web-0001', 1794888300000, 1794888600000, 0, 0, 2, NULL,
  '{"composerId":"e3e3e3e3-0000-4000-8000-000000000003","name":"Dark mode","unifiedMode":"agent","workspaceIdentifier":{"id":"ws-web-0001","uri":{"fsPath":"c:\\Users\\alice\\web","path":"/c:/Users/alice/web","scheme":"file"}}}', NULL);
INSERT INTO composerHeaders VALUES ('a5a5a5a5-0000-4000-8000-000000000005', 'ws-docs-0001', 1794800000000, NULL, 0, 0, 1, NULL,
  '{"composerId":"a5a5a5a5-0000-4000-8000-000000000005","workspaceIdentifier":{"id":"ws-docs-0001"}}', NULL);
INSERT INTO composerHeaders VALUES ('empty-state-draft', 'empty-window', 1794700000000, NULL, 0, 0, 0, NULL, 'not json', NULL);

INSERT INTO cursorDiskKV VALUES ('composerData:e3e3e3e3-0000-4000-8000-000000000003',
  '{"_v":18,"composerId":"e3e3e3e3-0000-4000-8000-000000000003","name":"Dark mode","modelConfig":{"modelName":"claude-fake-1","maxMode":false},"blobEncryptionKey":"FAKE-KEY-SHOULD-NOT-LEAK","speculativeSummarizationEncryptionKey":"FAKE-KEY-SHOULD-NOT-LEAK"}');
INSERT INTO cursorDiskKV VALUES ('composerData:a5a5a5a5-0000-4000-8000-000000000005', NULL);
INSERT INTO cursorDiskKV VALUES ('bubbleId:e3e3e3e3-0000-4000-8000-000000000003:b1', '{"type":1,"text":"BUBBLE-BODY-NOT-READ"}');
