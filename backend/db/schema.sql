create extension if not exists "pgcrypto";

create table if not exists doctors (
  id text primary key,
  name text not null,
  avatar_url text not null default '',
  created_at timestamptz not null default now()
);

create table if not exists patients (
  id uuid primary key default gen_random_uuid(),
  doctor_id text not null references doctors(id) on delete cascade,
  name text not null,
  age integer,
  sex text,
  summary text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists sessions (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid not null references patients(id) on delete cascade,
  title text not null,
  status text not null default 'active' check (status in ('active', 'completed')),
  summary text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists recordings (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references sessions(id) on delete cascade,
  transcript text not null,
  duration_seconds integer not null default 0,
  created_at timestamptz not null default now()
);

create table if not exists analyses (
  id uuid primary key default gen_random_uuid(),
  recording_id uuid not null references recordings(id) on delete cascade,
  session_id uuid not null references sessions(id) on delete cascade,
  pioneer jsonb not null default '{}'::jsonb,
  pioneer_finetuned jsonb,
  openai jsonb not null default '{}'::jsonb,
  tavily_cards jsonb not null default '[]'::jsonb,
  winner text not null default 'pioneer',
  created_at timestamptz not null default now()
);

create table if not exists follow_up_questions (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references sessions(id) on delete cascade,
  recording_id uuid references recordings(id) on delete cascade,
  question text not null,
  reason text not null default '',
  priority text not null default 'medium' check (priority in ('high', 'medium', 'low')),
  answered boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists idx_patients_doctor_id on patients(doctor_id);
create index if not exists idx_sessions_patient_id on sessions(patient_id);
create index if not exists idx_recordings_session_id on recordings(session_id);
create index if not exists idx_analyses_session_id on analyses(session_id);
create index if not exists idx_follow_up_questions_session_id on follow_up_questions(session_id);

insert into doctors (id, name, avatar_url)
values ('doctor_demo', 'Dr. Youssef', '/doctor-avatar.jpg')
on conflict (id) do update
set name = excluded.name,
    avatar_url = excluded.avatar_url;

insert into patients (id, doctor_id, name, age, sex, summary)
values
  ('11111111-1111-1111-1111-111111111111', 'doctor_demo', 'Amal Benali', 42, 'female', 'Chest pain follow-up'),
  ('22222222-2222-2222-2222-222222222222', 'doctor_demo', 'Karim Haddad', 58, 'male', 'Diabetes medication review'),
  ('33333333-3333-3333-3333-333333333333', 'doctor_demo', 'Nora Mansour', 35, 'female', 'Migraine and pain medication intake')
on conflict (id) do update
set name = excluded.name,
    age = excluded.age,
    sex = excluded.sex,
    summary = excluded.summary,
    updated_at = now();

insert into sessions (id, patient_id, title, status, summary)
values
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '11111111-1111-1111-1111-111111111111', 'Chest pain intake', 'active', 'Awaiting first recording.'),
  ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', '22222222-2222-2222-2222-222222222222', 'Medication review', 'active', 'Awaiting first recording.'),
  ('cccccccc-cccc-cccc-cccc-cccccccccccc', '33333333-3333-3333-3333-333333333333', 'Migraine intake', 'active', 'Awaiting first recording.')
on conflict (id) do update
set title = excluded.title,
    status = excluded.status,
    summary = excluded.summary,
    updated_at = now();
