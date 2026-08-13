create table public.reviewer_access (
  user_id uuid primary key references auth.users(id) on delete cascade,
  granted_at timestamptz not null default now()
);

alter table public.reviewer_access enable row level security;

create policy "reviewer_access_select_own"
on public.reviewer_access for select
to authenticated
using ((select auth.uid()) = user_id);

revoke all on table public.reviewer_access from public, anon, authenticated;
grant select on table public.reviewer_access to authenticated;

comment on table public.reviewer_access is
  'Trusted editorial access. Membership is granted only by a database administrator.';
