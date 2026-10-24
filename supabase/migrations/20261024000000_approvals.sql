create table if not exists public.approvals (
  id bigserial primary key,
  approval_id text not null,
  answer text not null check (answer in ('yes', 'no')),
  from_number text,
  received_at timestamptz not null default now()
);
create index if not exists approvals_approval_id_idx on public.approvals (approval_id);
-- Only the edge function (service role) touches this table.
alter table public.approvals enable row level security;
