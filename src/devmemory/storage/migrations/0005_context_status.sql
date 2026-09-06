-- 0005_context_status: context completeness tracking for Track 1 Privacy Boundary.
-- Versions and checkpoints record whether context is COMPLETE, PARTIAL, or MISSING,
-- plus which fields were detected as redacted or unavailable.

ALTER TABLE versions ADD COLUMN context_status TEXT NOT NULL DEFAULT 'COMPLETE';
ALTER TABLE versions ADD COLUMN redacted_fields_json TEXT NOT NULL DEFAULT '[]';

ALTER TABLE entire_checkpoints ADD COLUMN context_status TEXT NOT NULL DEFAULT 'COMPLETE';
ALTER TABLE entire_checkpoints ADD COLUMN redacted_fields_json TEXT NOT NULL DEFAULT '[]';
