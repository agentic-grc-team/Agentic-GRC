-- Minimal stand-in for Supabase's auth.users table, used only by CI and local
-- integration tests on a plain PostgreSQL database. Never run this on Supabase.
CREATE SCHEMA IF NOT EXISTS auth;

CREATE TABLE IF NOT EXISTS auth.users (
    id                 uuid PRIMARY KEY,
    aud                varchar(255),
    role               varchar(255),
    email              varchar(255),
    encrypted_password varchar(255),
    email_confirmed_at timestamptz,
    raw_app_meta_data  jsonb,
    raw_user_meta_data jsonb,
    created_at         timestamptz,
    updated_at         timestamptz
);
