-- Run as postgres on the agentic_grc database, after backend/tests/sql/supabase_auth_stub.sql.
-- The app role owns public (migrations) and can only read and reference the auth.users stand-in.
ALTER SCHEMA public OWNER TO agentic_grc;
REVOKE ALL ON DATABASE agentic_grc FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE agentic_grc TO agentic_grc;
GRANT USAGE ON SCHEMA auth TO agentic_grc;
GRANT SELECT, REFERENCES ON auth.users TO agentic_grc;
