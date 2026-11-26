-- Read-only summary of an agentic_grc database, used to compare a restored backup with the live one.
-- Run as postgres: psql -d <database> -XAt -F ' | ' -f restore-check.sql
SELECT 'alembic version', version_num FROM alembic_version
UNION ALL
SELECT 'tables in ' || table_schema, count(*)::text
FROM information_schema.tables
WHERE table_schema IN ('public', 'auth', 'agentic_grc_private')
GROUP BY table_schema
UNION ALL
SELECT 'user triggers', count(*)::text FROM pg_trigger WHERE NOT tgisinternal
UNION ALL SELECT 'auth.users', count(*)::text FROM auth.users
UNION ALL SELECT 'organizations', count(*)::text FROM public.organizations
UNION ALL SELECT 'assessments', count(*)::text FROM public.assessments
UNION ALL SELECT 'assessment_controls', count(*)::text FROM public.assessment_controls
UNION ALL SELECT 'control_results', count(*)::text FROM public.control_results
UNION ALL SELECT 'control_result_reviews', count(*)::text FROM public.control_result_reviews
UNION ALL SELECT 'decision_traces', count(*)::text FROM public.decision_traces
UNION ALL SELECT 'assessment_sessions', count(*)::text FROM public.assessment_sessions
UNION ALL SELECT 'interview_turns', count(*)::text FROM public.interview_turns
UNION ALL SELECT 'evidence_files', count(*)::text FROM public.evidence_files
UNION ALL SELECT 'checkpoints', count(*)::text FROM agentic_grc_private.checkpoints
UNION ALL SELECT 'newest assessment', coalesce(max(created_at)::text, '-') FROM public.assessments
UNION ALL SELECT 'newest control result', coalesce(max(created_at)::text, '-') FROM public.control_results
UNION ALL SELECT 'newest interview turn', coalesce(max(created_at)::text, '-') FROM public.interview_turns;
