ALTER TABLE signals
ADD COLUMN status TEXT NOT NULL DEFAULT 'open'
CHECK (status IN (
    'open',
    'in_progress',
    'resolved',
    'failed'
));

CREATE INDEX signals_status_idx
ON signals(status);