At line:1 char:25
+ ... s\activate; alembic upgrade 13e123a398eb:head --sql > supabase_upgrad ...
+                 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (INFO  [alembic....PostgresqlImpl.:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
BEGIN;

-- Running upgrade 13e123a398eb -> a1c4e9f27b30

CREATE TABLE place_questions (
    id UUID NOT NULL, 
    location_id UUID NOT NULL, 
    question_text TEXT NOT NULL, 
    normalized_text TEXT NOT NULL, 
    display_order INTEGER DEFAULT '0' NOT NULL, 
    source_urls JSONB, 
    research_batch_id UUID, 
    active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT fk_place_questions_location_id_locations FOREIGN KEY(location_id) REFERENCES locations (id) ON DELETE CASCADE
);

ALTER TABLE place_questions ADD CONSTRAINT uq_place_questions_location_normalized UNIQUE (location_id, normalized_text);

CREATE TABLE place_question_research (
    id UUID NOT NULL, 
    location_id UUID NOT NULL, 
    status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
    provider VARCHAR(50) DEFAULT 'anthropic' NOT NULL, 
    model VARCHAR(100), 
    error_message TEXT, 
    attempt_count INTEGER DEFAULT '0' NOT NULL, 
    researched_at TIMESTAMP WITH TIME ZONE, 
    started_at TIMESTAMP WITH TIME ZONE, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT fk_place_question_research_location_id_locations FOREIGN KEY(location_id) REFERENCES locations (id) ON DELETE CASCADE
);

ALTER TABLE place_question_research ADD CONSTRAINT uq_place_question_research_location_id UNIQUE (location_id);

CREATE INDEX ix_place_question_research_status ON place_question_research (status);

CREATE TABLE reward_rules (
    id UUID NOT NULL, 
    rule_key VARCHAR(100) NOT NULL, 
    points INTEGER NOT NULL, 
    description TEXT, 
    active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
);

ALTER TABLE reward_rules ADD CONSTRAINT uq_reward_rules_rule_key UNIQUE (rule_key);

CREATE TABLE reward_ledger (
    id UUID NOT NULL, 
    guide_id UUID NOT NULL, 
    points INTEGER NOT NULL, 
    rule_key VARCHAR(100) NOT NULL, 
    idempotency_key VARCHAR(255) NOT NULL, 
    source_type VARCHAR(50) NOT NULL, 
    source_id UUID, 
    awarded_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT fk_reward_ledger_guide_id_guides FOREIGN KEY(guide_id) REFERENCES guides (id) ON DELETE CASCADE
);

ALTER TABLE reward_ledger ADD CONSTRAINT uq_reward_ledger_idempotency_key UNIQUE (idempotency_key);

CREATE INDEX ix_reward_ledger_guide_id_awarded_at ON reward_ledger (guide_id, awarded_at);

ALTER TABLE submissions ADD COLUMN source_place_question_id UUID;

ALTER TABLE submissions ADD CONSTRAINT fk_submissions_source_place_question_id_place_questions FOREIGN KEY(source_place_question_id) REFERENCES place_questions (id) ON DELETE SET NULL;

CREATE INDEX ix_submissions_source_place_question_id ON submissions (source_place_question_id);

INSERT INTO reward_rules (id, rule_key, points, description, active, created_at, updated_at)
        VALUES
          (gen_random_uuid(), 'question_answer', 25,
           'Answering a question from your priority queue', true, now(), now()),
          (gen_random_uuid(), 'question_answer_safety_critical', 40,
           'Answering a safety-critical question from your priority queue', true, now(), now()),
          (gen_random_uuid(), 'place_question_answer', 15,
           'Answering a popular question about a place', true, now(), now()),
          (gen_random_uuid(), 'explore_contribution', 20,
           'Sharing a discovery from the Explore tab', true, now(), now()),
          (gen_random_uuid(), 'explore_contribution_media_bonus', 30,
           'Bonus for adding a photo or voice note to an Explore discovery', true, now(), now());

UPDATE alembic_version SET version_num='a1c4e9f27b30' WHERE alembic_version.version_num = '13e123a398eb';

location-specific contribution invitations
-- Running upgrade a1c4e9f27b30 -> c3f7a91d4e28

ALTER TABLE place_questions ADD COLUMN contribution_kind VARCHAR(20) DEFAULT 'observation' NOT NULL;

ALTER TABLE place_questions ADD COLUMN context_note TEXT;

UPDATE place_questions SET active = false;

UPDATE place_question_research SET researched_at = NULL;

INSERT INTO reward_rules (id, rule_key, points, description, active)
                VALUES (gen_random_uuid(), 'place_question_photo', 50, 'Photographing a specific place you''re standing at', true)
                ON CONFLICT (rule_key) DO NOTHING;

INSERT INTO reward_rules (id, rule_key, points, description, active)
                VALUES (gen_random_uuid(), 'place_question_voice', 45, 'Recording your experience of a specific place', true)
                ON CONFLICT (rule_key) DO NOTHING;

INSERT INTO reward_rules (id, rule_key, points, description, active)
                VALUES (gen_random_uuid(), 'place_question_experience', 35, 'Describing what a specific place is really like', true)
                ON CONFLICT (rule_key) DO NOTHING;

INSERT INTO reward_rules (id, rule_key, points, description, active)
                VALUES (gen_random_uuid(), 'place_question_observation', 25, 'Reporting what you can see at a specific place', true)
                ON CONFLICT (rule_key) DO NOTHING;

INSERT INTO reward_rules (id, rule_key, points, description, active)
                VALUES (gen_random_uuid(), 'place_question_status', 15, 'Confirming whether a place is open or accessible right now', true)
                ON CONFLICT (rule_key) DO NOTHING;

UPDATE alembic_version SET version_num='c3f7a91d4e28' WHERE alembic_version.version_num = 'a1c4e9f27b30';
locations, plus a discovery lifecycle table
for every generated invitation.
date provenance, plus the 'memory'
capture type.

-- Running upgrade c3f7a91d4e28 -> d5b1c8e37a94

ALTER TABLE locations ADD COLUMN source VARCHAR(20) DEFAULT 'manual' NOT NULL;

ALTER TABLE locations ADD COLUMN place_kind VARCHAR(50);

ALTER TABLE locations ADD COLUMN source_urls JSONB;

ALTER TABLE locations ADD COLUMN discovery_cell_key VARCHAR(32);

CREATE INDEX ix_locations_discovery_cell_key ON locations (discovery_cell_key);

CREATE TABLE poi_discovery (
    id UUID NOT NULL, 
    cell_key VARCHAR(32) NOT NULL, 
    center_latitude NUMERIC(9, 6) NOT NULL, 
    center_longitude NUMERIC(9, 6) NOT NULL, 
    status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
    provider VARCHAR(50) DEFAULT 'anthropic' NOT NULL, 
    model VARCHAR(100), 
    error_message TEXT, 
    attempt_count INTEGER DEFAULT '0' NOT NULL, 
    discovered_count INTEGER DEFAULT '0' NOT NULL, 
    discovered_at TIMESTAMP WITH TIME ZONE, 
    started_at TIMESTAMP WITH TIME ZONE, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (cell_key)
);

CREATE INDEX ix_poi_discovery_status ON poi_discovery (status);

UPDATE alembic_version SET version_num='d5b1c8e37a94' WHERE alembic_version.version_num = 'c3f7a91d4e28';

-- Running upgrade d5b1c8e37a94 -> e7a2c5f81b60

ALTER TABLE locations ADD COLUMN locality VARCHAR(255);

CREATE TABLE place_research_findings (
    id UUID NOT NULL, 
    location_id UUID NOT NULL, 
    research_id UUID, 
    topic VARCHAR(30) NOT NULL, 
    query_text TEXT NOT NULL, 
    provider VARCHAR(50) NOT NULL, 
    model VARCHAR(100), 
    summary TEXT NOT NULL, 
    source_urls JSONB, 
    source_titles JSONB, 
    retrieved_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(location_id) REFERENCES locations (id) ON DELETE CASCADE, 
    FOREIGN KEY(research_id) REFERENCES place_question_research (id) ON DELETE SET NULL
);

CREATE INDEX ix_place_research_findings_location ON place_research_findings (location_id, retrieved_at);

ALTER TABLE place_questions ADD COLUMN source_finding_id UUID;

ALTER TABLE place_questions ADD CONSTRAINT fk_place_questions_source_finding FOREIGN KEY(source_finding_id) REFERENCES place_research_findings (id) ON DELETE SET NULL;

UPDATE place_questions SET active = false;

UPDATE place_question_research SET researched_at = NULL;

UPDATE alembic_version SET version_num='e7a2c5f81b60' WHERE alembic_version.version_num = 'd5b1c8e37a94';

-- Running upgrade e7a2c5f81b60 -> a4d9e6c1f708

ALTER TABLE submissions ADD COLUMN location_source VARCHAR(30) DEFAULT 'unknown' NOT NULL;

ALTER TABLE submissions ADD COLUMN location_accuracy_meters NUMERIC(10, 2);

ALTER TABLE submissions ADD COLUMN location_captured_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE submissions ADD COLUMN location_label VARCHAR(255);

ALTER TABLE submissions ADD COLUMN location_evidence TEXT;

ALTER TABLE submissions ADD COLUMN occurred_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE submissions ADD COLUMN occurred_at_precision VARCHAR(20) DEFAULT 'unknown' NOT NULL;

ALTER TABLE submissions ADD COLUMN date_source VARCHAR(20) DEFAULT 'unknown' NOT NULL;

ALTER TABLE observations ADD COLUMN location_source VARCHAR(30);

ALTER TABLE observations ADD COLUMN location_evidence TEXT;

UPDATE alembic_version SET version_num='a4d9e6c1f708' WHERE alembic_version.version_num = 'e7a2c5f81b60';

COMMIT;

