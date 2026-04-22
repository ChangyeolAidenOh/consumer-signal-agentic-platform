-- =============================================================================
-- HNS Consumer Signal Detection Platform — Database Schema
-- Based on actual CSV column output from check_columns.py (2026-04-17)
-- =============================================================================


-- Layer 1: VoC documents with causal signals (hns_causal_signals.csv, 1744 rows)
CREATE TABLE IF NOT EXISTS voc_documents (
    id                   SERIAL PRIMARY KEY,
    source               TEXT,
    date                 TEXT,
    query                TEXT,
    raw_text             TEXT,
    unigram              TEXT,
    bigram               TEXT,
    unibi_mix            TEXT,
    adj_noun             TEXT,
    video_title          TEXT,
    likes                REAL,
    churn_score          INTEGER DEFAULT 0,
    churn_signals        TEXT,
    positive_score       INTEGER DEFAULT 0,
    positive_signals     TEXT,
    net_signal           INTEGER DEFAULT 0,
    signal_type          TEXT,
    competitor_mentioned BOOLEAN DEFAULT FALSE,
    created_at           TIMESTAMP DEFAULT NOW()
);

-- Layer 1: Monthly churn/positive trend (hns_temporal_signals.csv, 43 rows)
CREATE TABLE IF NOT EXISTS temporal_signals (
    id             SERIAL PRIMARY KEY,
    month          TEXT,
    total          INTEGER,
    churn          INTEGER,
    positive       INTEGER,
    competitor     INTEGER,
    churn_rate     REAL,
    positive_rate  REAL,
    created_at     TIMESTAMP DEFAULT NOW()
);

-- Layer 1: LDA topic results (hns_lda_results.csv, 56 rows)
CREATE TABLE IF NOT EXISTS lda_topics (
    id          SERIAL PRIMARY KEY,
    scope       TEXT,
    source      TEXT,
    mode        TEXT,
    topic_id    INTEGER,
    optimal_k   INTEGER,
    coherence   REAL,
    keywords    TEXT,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- Layer 1: BERTopic document mapping (hns_bertopic_documents.csv, 1742 rows)
CREATE TABLE IF NOT EXISTS bertopic_documents (
    id           SERIAL PRIMARY KEY,
    source       TEXT,
    date         TEXT,
    query        TEXT,
    raw_text     TEXT,
    unigram      TEXT,
    bigram       TEXT,
    unibi_mix    TEXT,
    adj_noun     TEXT,
    video_title  TEXT,
    likes        REAL,
    bertopic_id  INTEGER,
    created_at   TIMESTAMP DEFAULT NOW()
);

-- Layer 1: LDA x BERTopic consensus signals (hns_lda_bertopic_consensus.csv, 12 rows)
CREATE TABLE IF NOT EXISTS lda_bertopic_consensus (
    id               SERIAL PRIMARY KEY,
    lda_topic        TEXT,
    bertopic_id      INTEGER,
    overlap_keywords TEXT,
    bertopic_count   INTEGER,
    confidence       TEXT,
    created_at       TIMESTAMP DEFAULT NOW()
);

-- Layer 2: Monthly trend features (trend_features.csv, 76 rows x 17 cols)
-- Korean column names require double quotes in SQL
CREATE TABLE IF NOT EXISTS trend_monthly (
    id                     SERIAL PRIMARY KEY,
    date                   TEXT,
    category_click         REAL,
    "헤드앤숄더샴푸"           REAL,
    "헤드앤숄더차콜"           REAL,
    "헤드앤숄더"              REAL,
    "헤드앤숄더프로페셔널"       REAL,
    "헤드앤숄더클리니컬스트렝스"  REAL,
    "비듬샴푸"               REAL,
    "지루성두피샴푸"           REAL,
    "안티트로샴푸"             REAL,
    "지성두피샴푸"             REAL,
    "비듬"                  REAL,
    "팬틴"                  REAL,
    "헤드앤숄더_경쟁"          REAL,
    "닥터그루트"              REAL,
    "케라시스"               REAL,
    "두피케어카테고리"          REAL,
    created_at             TIMESTAMP DEFAULT NOW()
);

-- Layer 2: Chronos 12-month forecast (chronos_forecast.csv, 12 rows)
CREATE TABLE IF NOT EXISTS chronos_forecast (
    id              SERIAL PRIMARY KEY,
    date            TEXT,
    forecast_median REAL,
    forecast_low    REAL,
    forecast_high   REAL,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Layer 3: Segment-level switching probability (switching_prob_regression.csv, 4 rows)
CREATE TABLE IF NOT EXISTS segment_summary (
    id                     SERIAL PRIMARY KEY,
    segment                TEXT,
    n_docs                 INTEGER,
    churn_rate             REAL,
    competitor_rate        REAL,
    medical_rate           REAL,
    ingredient_rate        REAL,
    base_prob              REAL,
    switching_probability  REAL,
    created_at             TIMESTAMP DEFAULT NOW()
);

-- Layer 3: Intervention plan per segment (switching_implications.csv, 4 rows)
CREATE TABLE IF NOT EXISTS switching_implications (
    id                     SERIAL PRIMARY KEY,
    segment                TEXT,
    n_docs                 INTEGER,
    switching_probability  REAL,
    risk_level             TEXT,
    primary_channel        TEXT,
    intervention_timing    TEXT,
    recommended_action     TEXT,
    created_at             TIMESTAMP DEFAULT NOW()
);

-- Layer 3: Competitive timeline (timeline_analysis.csv, 1 row)
CREATE TABLE IF NOT EXISTS timeline_analysis (
    id                         SERIAL PRIMARY KEY,
    antitro_first_entry        TEXT,
    antitro_reversal_point     TEXT,
    antitro_acceleration_point TEXT,
    antitro_acceleration_delta REAL,
    current_antitro_ratio      REAL,
    current_hns_momentum       REAL,
    strategic_window           TEXT,
    created_at                 TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_voc_source ON voc_documents(source);
CREATE INDEX IF NOT EXISTS idx_voc_signal ON voc_documents(signal_type);
CREATE INDEX IF NOT EXISTS idx_voc_competitor ON voc_documents(competitor_mentioned);
CREATE INDEX IF NOT EXISTS idx_voc_date ON voc_documents(date);
CREATE INDEX IF NOT EXISTS idx_trend_date ON trend_monthly(date);
CREATE INDEX IF NOT EXISTS idx_temporal_month ON temporal_signals(month);
CREATE INDEX IF NOT EXISTS idx_bertopic_id ON bertopic_documents(bertopic_id);
