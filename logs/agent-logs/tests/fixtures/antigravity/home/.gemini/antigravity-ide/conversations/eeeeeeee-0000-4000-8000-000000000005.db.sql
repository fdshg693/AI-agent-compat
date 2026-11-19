CREATE TABLE trajectory_meta (trajectory_id TEXT PRIMARY KEY, cascade_id TEXT, trajectory_type INTEGER, source INTEGER);
INSERT INTO trajectory_meta VALUES ('t-1', 'eeeeeeee-0000-4000-8000-000000000005', 4, 22);
CREATE TABLE steps (idx INTEGER PRIMARY KEY, step_type INTEGER, status INTEGER, step_payload BLOB, step_format INTEGER);
INSERT INTO steps VALUES (0, 14, 3, X'0801', 0);
