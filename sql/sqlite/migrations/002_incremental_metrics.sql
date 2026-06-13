ALTER TABLE pipeline_runs ADD COLUMN records_inserted INTEGER NOT NULL DEFAULT 0;
ALTER TABLE pipeline_runs ADD COLUMN records_updated INTEGER NOT NULL DEFAULT 0;
ALTER TABLE pipeline_runs ADD COLUMN records_unchanged INTEGER NOT NULL DEFAULT 0;
ALTER TABLE pipeline_runs ADD COLUMN records_rejected INTEGER NOT NULL DEFAULT 0;

ALTER TABLE source_readiness ADD COLUMN records_inserted INTEGER NOT NULL DEFAULT 0;
ALTER TABLE source_readiness ADD COLUMN records_updated INTEGER NOT NULL DEFAULT 0;
ALTER TABLE source_readiness ADD COLUMN records_unchanged INTEGER NOT NULL DEFAULT 0;
ALTER TABLE source_readiness ADD COLUMN records_rejected INTEGER NOT NULL DEFAULT 0;
