-- Reference DEVELOPMENT schema only. Not executed by application/startup/build.
-- After an approved development migration, Replit Publish manages its production
-- schema diff. Do not run a custom production schema migration.
CREATE TABLE public.sprintpulse_memory_ingestion (
    finding_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    owner_scope TEXT NOT NULL,
    environment TEXT NOT NULL CHECK (environment IN ('development', 'production')),
    payload JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'reserved', 'pending', 'unknown')),
    event_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
