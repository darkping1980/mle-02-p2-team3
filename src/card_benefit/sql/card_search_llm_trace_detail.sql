-- Opt-in GraphRAG LLM diagnostics. Apply only after reviewing the schema proposal.
-- Existing db_pipeline.app_log columns and rows are not altered.
BEGIN;

CREATE TABLE IF NOT EXISTS db_pipeline.app_log_llm_trace (
    app_log_llm_trace_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    app_log_id bigint NOT NULL
        REFERENCES db_pipeline.app_log (app_log_id) ON DELETE CASCADE,
    trace_seq smallint NOT NULL CHECK (trace_seq > 0),
    stage text NOT NULL CHECK (stage IN (
        'SEARCH', 'INTERPRET', 'INTERPRET_FILTER', 'RETRIEVE',
        'ANSWER', 'ANSWER_VALIDATE', 'PIPELINE_ERROR'
    )),
    question_id text,
    source_revision text,
    model_name text,
    response_schema jsonb,
    prompt_text text,
    prompt_sha256 char(64),
    prompt_redacted boolean NOT NULL DEFAULT false,
    input_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    raw_output jsonb,
    output_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    usage jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamp with time zone NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT app_log_llm_trace_request_seq_uk UNIQUE (app_log_id, trace_seq)
);

CREATE INDEX IF NOT EXISTS ix_app_log_llm_trace_stage
    ON db_pipeline.app_log_llm_trace (app_log_id, stage, trace_seq);

COMMIT;
