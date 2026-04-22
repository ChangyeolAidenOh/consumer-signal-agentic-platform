-- =============================================================================
-- Verification and analysis queries (based on actual column names)
-- =============================================================================


-- 1. Row count per table (run after load to verify)
SELECT 'voc_documents' AS t, COUNT(*) AS n FROM voc_documents
UNION ALL SELECT 'temporal_signals', COUNT(*) FROM temporal_signals
UNION ALL SELECT 'lda_topics', COUNT(*) FROM lda_topics
UNION ALL SELECT 'bertopic_documents', COUNT(*) FROM bertopic_documents
UNION ALL SELECT 'lda_bertopic_consensus', COUNT(*) FROM lda_bertopic_consensus
UNION ALL SELECT 'trend_monthly', COUNT(*) FROM trend_monthly
UNION ALL SELECT 'chronos_forecast', COUNT(*) FROM chronos_forecast
UNION ALL SELECT 'segment_summary', COUNT(*) FROM segment_summary
UNION ALL SELECT 'switching_implications', COUNT(*) FROM switching_implications
UNION ALL SELECT 'timeline_analysis', COUNT(*) FROM timeline_analysis;


-- 2. Signal type distribution by source
SELECT
    source,
    signal_type,
    COUNT(*) AS cnt,
    ROUND(COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER (PARTITION BY source) * 100, 1) AS pct
FROM voc_documents
GROUP BY source, signal_type
ORDER BY source, signal_type;


-- 3. Churn rate: competitor-mentioned vs overall
SELECT
    competitor_mentioned,
    COUNT(*) AS total,
    SUM(CASE WHEN signal_type = '이탈위험' THEN 1 ELSE 0 END) AS churn_cnt,
    ROUND(
        SUM(CASE WHEN signal_type = '이탈위험' THEN 1 ELSE 0 END)::NUMERIC
        / COUNT(*) * 100, 1
    ) AS churn_pct
FROM voc_documents
GROUP BY competitor_mentioned;


-- 4. Monthly churn trend (most recent 12 months)
SELECT
    month,
    total,
    churn,
    positive,
    ROUND(churn_rate * 100, 1) AS churn_pct,
    ROUND(positive_rate * 100, 1) AS positive_pct
FROM temporal_signals
ORDER BY month DESC
LIMIT 12;


-- 5. Antitro vs HNS Core search volume (reversal period)
SELECT
    date,
    "헤드앤숄더샴푸" AS hns_core,
    "안티트로샴푸" AS antitro,
    CASE WHEN "헤드앤숄더샴푸" > 0
         THEN ROUND(("안티트로샴푸" / "헤드앤숄더샴푸")::NUMERIC, 3)
    END AS ratio
FROM trend_monthly
WHERE "안티트로샴푸" > 0
ORDER BY date;


-- 6. HNS product line: latest vs 2020 baseline
WITH baseline AS (
    SELECT
        ROUND(AVG("헤드앤숄더샴푸")::NUMERIC, 1) AS avg_core,
        ROUND(AVG("헤드앤숄더차콜")::NUMERIC, 1) AS avg_charcoal,
        ROUND(AVG("헤드앤숄더클리니컬스트렝스")::NUMERIC, 1) AS avg_clinical
    FROM trend_monthly
    WHERE date LIKE '2020%'
),
latest AS (
    SELECT "헤드앤숄더샴푸", "헤드앤숄더차콜", "헤드앤숄더클리니컬스트렝스"
    FROM trend_monthly ORDER BY date DESC LIMIT 1
)
SELECT 'HNS Core' AS line, b.avg_core AS baseline, l."헤드앤숄더샴푸" AS latest,
    ROUND(((l."헤드앤숄더샴푸" - b.avg_core) / NULLIF(b.avg_core, 0) * 100)::NUMERIC, 1) AS chg_pct
FROM baseline b, latest l
UNION ALL
SELECT 'Clinical', b.avg_clinical, l."헤드앤숄더클리니컬스트렝스",
    ROUND(((l."헤드앤숄더클리니컬스트렝스" - b.avg_clinical) / NULLIF(b.avg_clinical, 0) * 100)::NUMERIC, 1)
FROM baseline b, latest l;


-- 7. Segment switching probability
SELECT
    segment,
    n_docs,
    ROUND(churn_rate::NUMERIC, 3) AS churn,
    ROUND(competitor_rate::NUMERIC, 3) AS competitor,
    ROUND(switching_probability::NUMERIC, 4) AS p_switch
FROM segment_summary
ORDER BY switching_probability DESC;


-- 8. Intervention strategy per segment
SELECT
    segment,
    risk_level,
    intervention_timing,
    recommended_action
FROM switching_implications
ORDER BY switching_probability DESC;


-- 9. Cross-layer: VoC churn rate x Antitro search volume
SELECT
    ts.month,
    ts.churn_rate,
    tm."안티트로샴푸" AS antitro,
    tm."헤드앤숄더샴푸" AS hns_core
FROM temporal_signals ts
JOIN trend_monthly tm
    ON ts.month = SUBSTRING(tm.date, 1, 7)
WHERE tm."안티트로샴푸" > 0
ORDER BY ts.month;


-- 10. LDA x BERTopic consensus signals
SELECT
    lda_topic,
    bertopic_id,
    overlap_keywords,
    bertopic_count,
    confidence
FROM lda_bertopic_consensus
ORDER BY bertopic_count DESC;
