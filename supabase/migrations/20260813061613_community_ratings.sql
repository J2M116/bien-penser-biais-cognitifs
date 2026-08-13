create extension if not exists citext with schema extensions;

create table public.profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name extensions.citext not null unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint profiles_display_name_length check (char_length(trim(display_name::text)) between 2 and 40)
);

create table public.ratings (
  user_id uuid not null references auth.users(id) on delete cascade,
  bias_id text not null,
  score smallint not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, bias_id),
  constraint ratings_bias_id_format check (bias_id ~ '^[0-9]{3}-[a-z0-9-]+$'),
  constraint ratings_score_range check (score between 1 and 100)
);

create index ratings_bias_id_idx on public.ratings (bias_id);

create function public.set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger profiles_set_updated_at
before update on public.profiles
for each row execute function public.set_updated_at();

create trigger ratings_set_updated_at
before update on public.ratings
for each row execute function public.set_updated_at();

create function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public, extensions
as $$
declare
  requested_name text;
  final_name text;
begin
  requested_name := trim(coalesce(new.raw_user_meta_data ->> 'display_name', ''));
  if char_length(requested_name) < 2 or char_length(requested_name) > 40 then
    requested_name := 'Membre';
  end if;
  final_name := requested_name;
  if exists (select 1 from public.profiles where display_name = final_name) then
    final_name := left(requested_name, 31) || '-' || left(new.id::text, 8);
  end if;
  insert into public.profiles (user_id, display_name)
  values (new.id, final_name);
  return new;
end;
$$;

create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_new_user();

alter table public.profiles enable row level security;
alter table public.ratings enable row level security;

create policy "profiles_select_own"
on public.profiles for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "profiles_update_own"
on public.profiles for update
to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy "ratings_select_own"
on public.ratings for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "ratings_insert_own"
on public.ratings for insert
to authenticated
with check ((select auth.uid()) = user_id);

create policy "ratings_update_own"
on public.ratings for update
to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy "ratings_delete_own"
on public.ratings for delete
to authenticated
using ((select auth.uid()) = user_id);

create function public.get_bias_scores()
returns table (
  bias_id text,
  average_score numeric,
  median_score numeric,
  ratings_count bigint
)
language sql
stable
security definer
set search_path = pg_catalog, public
as $$
  select
    ratings.bias_id,
    round(avg(ratings.score)::numeric, 1) as average_score,
    round((percentile_cont(0.5) within group (order by ratings.score))::numeric, 1) as median_score,
    count(*) as ratings_count
  from public.ratings
  group by ratings.bias_id;
$$;

revoke all on table public.profiles from anon, authenticated;
revoke all on table public.ratings from anon, authenticated;
grant select, update on table public.profiles to authenticated;
grant select, insert, update, delete on table public.ratings to authenticated;

revoke all on function public.get_bias_scores() from public;
grant execute on function public.get_bias_scores() to anon, authenticated;

comment on table public.ratings is 'One editable 1-100 importance rating per user and cognitive bias.';
comment on function public.get_bias_scores() is 'Public aggregate scores without exposing user identifiers or individual ratings.';
