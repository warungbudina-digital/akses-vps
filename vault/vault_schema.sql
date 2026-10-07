SET ROLE scraper;
CREATE SCHEMA IF NOT EXISTS vault;
CREATE TABLE IF NOT EXISTS vault.profile (
  code          text PRIMARY KEY,
  display_name  text,
  platform      text,
  account_email text,
  notes         text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS vault.session (
  id               bigserial PRIMARY KEY,
  profile_code     text NOT NULL REFERENCES vault.profile(code) ON DELETE CASCADE,
  domain           text NOT NULL,
  cookies_netscape text,
  storage_state    jsonb,
  captured_at      timestamptz NOT NULL DEFAULT now(),
  expires_at       timestamptz,
  source_node      text,
  UNIQUE (profile_code, domain)
);
CREATE TABLE IF NOT EXISTS vault.audit (
  id           bigserial PRIMARY KEY,
  profile_code text, domain text, action text, node text,
  at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS vault_session_profile_idx ON vault.session(profile_code);
