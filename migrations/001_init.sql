-- ==========================================
-- card-pack-agent — initial schema
-- Apply via scripts/init_db.py
-- ==========================================

create extension if not exists "uuid-ossp";

-- --- Cases: one row per generated pack ---
create table if not exists cases (
    pack_id            uuid primary key,
    topic              text not null,
    topic_l1           text not null,
    topic_l2           text not null,
    topic_l3           text[] not null default '{}',
    strategy_doc       jsonb not null,
    cards              jsonb not null,
    script             jsonb not null,
    metrics            jsonb,
    tier               text,                  -- viral | good | mid | bad
    extracted_patterns jsonb default '[]'::jsonb,
    is_exploration     boolean not null default false,
    is_synthetic       boolean not null default false,
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now()
);

create index if not exists cases_l1_l2_idx on cases (topic_l1, topic_l2);
create index if not exists cases_tier_idx on cases (tier);
create index if not exists cases_created_at_idx on cases (created_at desc);
create index if not exists cases_l3_gin on cases using gin (topic_l3);

-- Auto-update updated_at
create or replace function touch_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists cases_touch on cases;
create trigger cases_touch
    before update on cases
    for each row
    execute function touch_updated_at();

-- --- Eval runs: regression history ---
create table if not exists eval_runs (
    run_id      uuid primary key default uuid_generate_v4(),
    suite       text not null,            -- classify | retrieve | generate | inject | all
    git_sha     text,
    started_at  timestamptz not null default now(),
    finished_at timestamptz,
    scores      jsonb not null default '{}'::jsonb,
    passed      boolean,
    notes       text
);

create index if not exists eval_runs_suite_idx on eval_runs (suite, started_at desc);

-- --- Tier calibration history ---
create table if not exists tier_calibrations (
    id              serial primary key,
    calibrated_at   timestamptz not null default now(),
    sample_size     int not null,
    viral_threshold double precision not null,
    good_threshold  double precision not null,
    mid_threshold   double precision not null,
    notes           text
);
