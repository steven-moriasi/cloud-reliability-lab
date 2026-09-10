CREATE TABLE IF NOT EXISTS orders (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL CHECK (tenant_id > 0),
    status text NOT NULL CHECK (status IN ('pending', 'completed', 'failed')),
    created_at timestamptz NOT NULL,
    total_cents integer NOT NULL CHECK (total_cents >= 0)
);

CREATE TABLE IF NOT EXISTS remediation_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    action text NOT NULL,
    target_pid integer,
    outcome text NOT NULL,
    details jsonb NOT NULL DEFAULT '{}'::jsonb
);
