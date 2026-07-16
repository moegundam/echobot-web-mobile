from __future__ import annotations


POSTGRES_SCHEMA_VERSION = 2

POSTGRES_SCHEMA_SQL = """
begin;

create table if not exists echobot_schema_migrations (
  version integer primary key,
  name text not null,
  applied_at timestamptz not null default now()
);

do $$
declare
  legacy_table text;
begin
  foreach legacy_table in array array[
    'llm_models',
    'voice_profiles',
    'live2d_models',
    'channel_integrations',
    'characters',
    'sessions',
    'messages',
    'attachments'
  ]
  loop
    if to_regclass(legacy_table) is not null and not exists (
      select 1
      from pg_constraint
      where conrelid = to_regclass(legacy_table)
        and contype = 'p'
        and replace(pg_get_constraintdef(oid), ' ', '') =
          'PRIMARYKEY(owner_user_id,id)'
    ) then
      raise exception
        'legacy non-tenant schema detected for table %; export data and migrate into a fresh schema-v2 database',
        legacy_table;
    end if;
  end loop;
end
$$;

do $$
begin
  create type channel_type as enum ('web', 'telegram', 'discord', 'qq', 'line', 'whatsapp');
exception
  when duplicate_object then null;
end
$$;

do $$
begin
  create type speech_kind as enum ('stt', 'tts');
exception
  when duplicate_object then null;
end
$$;

do $$
begin
  create type session_status as enum ('active', 'archived', 'disabled');
exception
  when duplicate_object then null;
end
$$;

create table if not exists llm_models (
  owner_user_id text not null,
  id text not null,
  name text not null,
  provider text not null,
  model text not null,
  base_url text,
  parameters jsonb not null default '{}'::jsonb,
  secret_ref text,
  is_enabled boolean not null default true,
  revision bigint not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (owner_user_id, id)
);

create table if not exists voice_profiles (
  owner_user_id text not null,
  id text not null,
  name text not null,
  stt jsonb not null default '{}'::jsonb,
  tts jsonb not null default '{}'::jsonb,
  secret_refs jsonb not null default '{}'::jsonb,
  is_enabled boolean not null default true,
  revision bigint not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (owner_user_id, id)
);

create table if not exists live2d_models (
  owner_user_id text not null,
  id text not null,
  name text not null,
  selection_key text not null default '',
  asset_uri text not null default '',
  config jsonb not null default '{}'::jsonb,
  emotion_map jsonb not null default '{}'::jsonb,
  is_enabled boolean not null default true,
  revision bigint not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (owner_user_id, id)
);

create table if not exists channel_integrations (
  owner_user_id text not null,
  id text not null,
  type channel_type not null,
  name text not null,
  config jsonb not null default '{}'::jsonb,
  secret_ref text,
  is_enabled boolean not null default true,
  revision bigint not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (owner_user_id, id),
  unique (owner_user_id, type, name)
);

create table if not exists characters (
  owner_user_id text not null,
  id text not null,
  name text not null,
  prompt text not null,
  llm_model_id text,
  voice_profile_id text,
  live2d_model_id text,
  default_channel_type channel_type,
  default_channel_integration_id text,
  metadata jsonb not null default '{}'::jsonb,
  revision bigint not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (owner_user_id, id),
  unique (owner_user_id, name),
  foreign key (owner_user_id, llm_model_id) references llm_models(owner_user_id, id),
  foreign key (owner_user_id, voice_profile_id) references voice_profiles(owner_user_id, id),
  foreign key (owner_user_id, live2d_model_id) references live2d_models(owner_user_id, id),
  foreign key (owner_user_id, default_channel_integration_id) references channel_integrations(owner_user_id, id)
);

create table if not exists sessions (
  owner_user_id text not null,
  id text not null,
  name text not null,
  session_kind text not null default 'conversation',
  character_id text,
  channel_type channel_type,
  channel_integration_id text,
  external_conversation_id text,
  route_mode text not null default 'chat_only',
  status session_status not null default 'active',
  compressed_summary text not null default '',
  state jsonb not null default '{}'::jsonb,
  revision bigint not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (owner_user_id, id),
  unique (owner_user_id, name),
  foreign key (owner_user_id, character_id) references characters(owner_user_id, id),
  foreign key (owner_user_id, channel_integration_id) references channel_integrations(owner_user_id, id)
);

alter table sessions
  add column if not exists channel_type channel_type;

create table if not exists session_pointers (
  owner_user_id text not null,
  pointer_kind text not null,
  session_id text not null,
  updated_at timestamptz not null default now(),
  primary key (owner_user_id, pointer_kind),
  foreign key (owner_user_id, session_id) references sessions(owner_user_id, id) on delete cascade
);

create table if not exists messages (
  owner_user_id text not null,
  id text not null,
  session_id text not null,
  sequence_no bigint not null,
  role text not null,
  content jsonb not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  primary key (owner_user_id, id),
  unique (owner_user_id, session_id, sequence_no),
  foreign key (owner_user_id, session_id) references sessions(owner_user_id, id) on delete cascade
);

create table if not exists attachments (
  owner_user_id text not null,
  id text not null,
  session_id text,
  uri text not null,
  content_type text not null,
  size_bytes bigint not null check (size_bytes >= 0),
  sha256 text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  primary key (owner_user_id, id),
  foreign key (owner_user_id, session_id) references sessions(owner_user_id, id) on delete cascade
);

create table if not exists conversation_jobs (
  owner_user_id text not null,
  id text not null,
  session_id text not null,
  status text not null,
  payload jsonb not null default '{}'::jsonb,
  revision bigint not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (owner_user_id, id),
  foreign key (owner_user_id, session_id) references sessions(owner_user_id, id) on delete cascade
);

create table if not exists cron_jobs (
  owner_user_id text not null,
  id text not null,
  session_id text,
  enabled boolean not null default true,
  schedule jsonb not null default '{}'::jsonb,
  payload jsonb not null default '{}'::jsonb,
  state jsonb not null default '{}'::jsonb,
  revision bigint not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (owner_user_id, id),
  foreign key (owner_user_id, session_id) references sessions(owner_user_id, id)
);

create table if not exists agent_trace_events (
  owner_user_id text not null,
  session_id text not null,
  run_id text not null,
  event_sequence bigint not null,
  event_type text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  primary key (owner_user_id, session_id, run_id, event_sequence),
  foreign key (owner_user_id, session_id) references sessions(owner_user_id, id) on delete cascade
);

create table if not exists runtime_documents (
  owner_user_id text not null,
  document_key text not null,
  payload jsonb not null default '{}'::jsonb,
  revision bigint not null default 1,
  updated_at timestamptz not null default now(),
  primary key (owner_user_id, document_key)
);

create or replace function echobot_normalize_channel_binding(value text)
returns text
language sql
immutable
parallel safe
as $$
  select lower(
    btrim(
      coalesce(value, ''),
      U&'\\0009\\000A\\000B\\000C\\000D\\001C\\001D\\001E' ||
        U&'\\001F\\0020\\0085\\00A0\\1680' ||
        U&'\\2000\\2001\\2002\\2003\\2004\\2005\\2006' ||
        U&'\\2007\\2008\\2009\\200A\\2028\\2029\\202F' ||
        U&'\\205F\\3000'
    )
  )
$$;

create or replace function echobot_enforce_session_channel_binding_uniqueness()
returns trigger
language plpgsql
as $$
declare
  normalized_type text := echobot_normalize_channel_binding(new.channel_type::text);
  normalized_integration_id text := echobot_normalize_channel_binding(new.channel_integration_id);
  conflicting_session_id text;
begin
  if normalized_type = '' and normalized_integration_id = '' then
    return new;
  end if;

  if current_setting('transaction_isolation') = 'repeatable read' then
    raise exception using
      errcode = '25000',
      message = 'session channel bindings do not support repeatable read transactions';
  end if;

  perform pg_advisory_xact_lock(
    hashtextextended('echobot-session-binding:' || new.owner_user_id, 0)
  );

  select existing.id
  into conflicting_session_id
  from sessions as existing
  where existing.owner_user_id = new.owner_user_id
    and existing.id <> new.id
    and (
      (
        echobot_normalize_channel_binding(existing.channel_integration_id) <> ''
        and echobot_normalize_channel_binding(existing.channel_integration_id) in (
          normalized_integration_id,
          normalized_type
        )
      )
      or (
        echobot_normalize_channel_binding(existing.channel_integration_id) = ''
        and echobot_normalize_channel_binding(existing.channel_type::text) <> ''
        and echobot_normalize_channel_binding(existing.channel_type::text) = normalized_type
      )
      or (
        normalized_integration_id <> ''
        and normalized_integration_id in (
          echobot_normalize_channel_binding(existing.channel_integration_id),
          echobot_normalize_channel_binding(existing.channel_type::text)
        )
      )
      or (
        normalized_integration_id = ''
        and normalized_type <> ''
        and normalized_type = echobot_normalize_channel_binding(
          existing.channel_type::text
        )
      )
    )
  limit 1;

  if conflicting_session_id is not null then
    raise exception using
      errcode = '23505',
      message = format(
        'channel binding conflicts with session %s',
        conflicting_session_id
      );
  end if;
  return new;
end
$$;

drop trigger if exists sessions_channel_binding_unique_trigger on sessions;
create trigger sessions_channel_binding_unique_trigger
before insert or update of owner_user_id, channel_type, channel_integration_id
on sessions
for each row
execute function echobot_enforce_session_channel_binding_uniqueness();

create index if not exists sessions_owner_updated_idx
  on sessions (owner_user_id, updated_at desc);
drop index if exists sessions_owner_channel_integration_unique_idx;
create unique index if not exists sessions_owner_channel_integration_unique_idx
  on sessions (
    owner_user_id,
    echobot_normalize_channel_binding(channel_integration_id)
  )
  where echobot_normalize_channel_binding(channel_integration_id) <> '';
create index if not exists sessions_owner_channel_type_idx
  on sessions (owner_user_id, channel_type)
  where channel_type is not null;
create index if not exists messages_session_order_idx
  on messages (owner_user_id, session_id, sequence_no);
create index if not exists attachments_session_idx
  on attachments (owner_user_id, session_id);
create index if not exists conversation_jobs_session_status_idx
  on conversation_jobs (owner_user_id, session_id, status);
create index if not exists agent_trace_events_run_idx
  on agent_trace_events (owner_user_id, session_id, run_id, event_sequence);

insert into echobot_schema_migrations (version, name)
values (2, 'session-centered-foundation-v2')
on conflict (version) do nothing;

commit;
""".strip()
