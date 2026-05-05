from __future__ import annotations


POSTGRES_SCHEMA_SQL = """
create type channel_type as enum ('web', 'telegram', 'discord', 'qq', 'line', 'whatsapp');
create type speech_kind as enum ('stt', 'tts');
create type session_status as enum ('active', 'archived', 'disabled');

create table if not exists llm_models (
  id text primary key,
  owner_user_id text not null default 'default',
  name text not null,
  provider text not null,
  model text not null,
  base_url text,
  parameters jsonb not null default '{}'::jsonb,
  secret_ref text,
  is_enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists voice_profiles (
  id text primary key,
  owner_user_id text not null default 'default',
  name text not null,
  stt jsonb not null default '{}'::jsonb,
  tts jsonb not null default '{}'::jsonb,
  secret_refs jsonb not null default '{}'::jsonb,
  is_enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists live2d_models (
  id text primary key,
  owner_user_id text not null default 'default',
  name text not null,
  selection_key text not null default '',
  asset_uri text not null default '',
  config jsonb not null default '{}'::jsonb,
  emotion_map jsonb not null default '{}'::jsonb,
  is_enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists channel_integrations (
  id text primary key,
  owner_user_id text not null default 'default',
  type channel_type not null,
  name text not null,
  config jsonb not null default '{}'::jsonb,
  secret_ref text,
  is_enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists characters (
  id text primary key,
  owner_user_id text not null default 'default',
  name text not null,
  prompt text not null,
  llm_model_id text references llm_models(id),
  voice_profile_id text references voice_profiles(id),
  live2d_model_id text references live2d_models(id),
  default_channel_type channel_type,
  default_channel_integration_id text references channel_integrations(id),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists sessions (
  id text primary key,
  owner_user_id text not null default 'default',
  name text not null,
  character_id text references characters(id),
  channel_integration_id text references channel_integrations(id),
  external_conversation_id text,
  route_mode text not null default 'chat_only',
  status session_status not null default 'active',
  state jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(owner_user_id, name)
);

create table if not exists messages (
  id text primary key,
  session_id text not null references sessions(id) on delete cascade,
  role text not null,
  content jsonb not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists attachments (
  id text primary key,
  session_id text references sessions(id) on delete cascade,
  uri text not null,
  content_type text not null,
  size_bytes bigint not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
""".strip()
