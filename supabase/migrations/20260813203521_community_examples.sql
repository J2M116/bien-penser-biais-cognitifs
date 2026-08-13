create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create table private.bias_catalog (
  bias_id text primary key,
  constraint bias_catalog_id_format
    check (bias_id ~ '^[0-9]{3}-[a-z0-9-]+$')
);

alter table private.bias_catalog enable row level security;
revoke all on table private.bias_catalog from public, anon, authenticated;

insert into private.bias_catalog (bias_id) values
  ('005-affect-heuristic'),
  ('007-anchoring-effect'),
  ('013-attentional-bias'),
  ('016-authority-bias'),
  ('017-automation-bias'),
  ('019-availability-cascade'),
  ('020-availability-heuristic'),
  ('021-backfire-effect'),
  ('022-bandwagon-effect'),
  ('023-barnum-effect'),
  ('024-base-rate-fallacy'),
  ('025-belief-bias'),
  ('033-choice-supportive-bias'),
  ('036-compassion-fade'),
  ('037-confirmation-bias'),
  ('040-conjunction-fallacy'),
  ('041-conservatism-bias'),
  ('042-consistency-bias'),
  ('046-courtesy-bias'),
  ('050-declinism'),
  ('058-dunning-kruger-effect'),
  ('077-framing-effect'),
  ('078-fundamental-attribution-error'),
  ('082-google-effect'),
  ('088-hindsight-bias'),
  ('089-hostile-attribution-bias'),
  ('100-illusion-of-validity'),
  ('101-illusory-correlation'),
  ('103-illusory-truth-effect'),
  ('107-ingroup-bias'),
  ('111-just-world-hypothesis'),
  ('138-optimism-bias'),
  ('139-ostrich-effect'),
  ('140-outcome-bias'),
  ('142-overconfidence-effect'),
  ('161-proportionality-bias'),
  ('176-salience-bias'),
  ('193-stereotypical-bias'),
  ('203-telescoping-effect');

create table public.bias_examples (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  bias_id text not null references private.bias_catalog(bias_id),
  example_text text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint bias_examples_user_bias_unique unique (user_id, bias_id),
  constraint bias_examples_text_trimmed check (example_text = btrim(example_text)),
  constraint bias_examples_text_length check (char_length(example_text) between 10 and 600)
);

create index bias_examples_bias_id_idx on public.bias_examples (bias_id);

create table public.bias_example_summaries (
  example_id uuid primary key references public.bias_examples(id) on delete cascade,
  bias_id text not null references private.bias_catalog(bias_id),
  example_text text not null,
  heart_count bigint not null default 0,
  created_at timestamptz not null,
  updated_at timestamptz not null,
  constraint bias_example_summaries_heart_count_nonnegative check (heart_count >= 0)
);

create index bias_example_summaries_bias_rank_idx
  on public.bias_example_summaries (bias_id, heart_count desc, created_at asc);

create table public.bias_example_hearts (
  user_id uuid not null references auth.users(id) on delete cascade,
  example_id uuid not null references public.bias_examples(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (user_id, example_id)
);

create index bias_example_hearts_example_id_idx
  on public.bias_example_hearts (example_id);

create trigger bias_examples_set_updated_at
before update on public.bias_examples
for each row execute function public.set_updated_at();

create function private.sync_bias_example_summary()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
begin
  if tg_op = 'INSERT' then
    insert into public.bias_example_summaries (
      example_id, bias_id, example_text, heart_count, created_at, updated_at
    )
    values (
      new.id, new.bias_id, new.example_text, 0, new.created_at, new.updated_at
    );
  else
    update public.bias_example_summaries
       set example_text = new.example_text,
           updated_at = new.updated_at
     where example_id = new.id;
  end if;
  return null;
end;
$$;

create trigger bias_examples_sync_summary
after insert or update of example_text
on public.bias_examples
for each row execute function private.sync_bias_example_summary();

create function private.sync_bias_example_heart_count()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
begin
  if tg_op = 'INSERT' then
    update public.bias_example_summaries
       set heart_count = heart_count + 1
     where example_id = new.example_id;
    if not found then
      raise exception using
        errcode = '23503',
        message = 'Public example summary is missing';
    end if;
  else
    update public.bias_example_summaries
       set heart_count = greatest(heart_count - 1, 0)
     where example_id = old.example_id;
  end if;
  return null;
end;
$$;

create trigger bias_example_hearts_sync_count
after insert or delete
on public.bias_example_hearts
for each row execute function private.sync_bias_example_heart_count();

revoke all on function private.sync_bias_example_summary()
  from public, anon, authenticated;
revoke all on function private.sync_bias_example_heart_count()
  from public, anon, authenticated;

alter table public.bias_examples enable row level security;
alter table public.bias_example_hearts enable row level security;
alter table public.bias_example_summaries enable row level security;

create policy "bias_examples_select_own"
on public.bias_examples for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "bias_examples_insert_own"
on public.bias_examples for insert
to authenticated
with check ((select auth.uid()) = user_id);

create policy "bias_examples_update_own"
on public.bias_examples for update
to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy "bias_examples_delete_own"
on public.bias_examples for delete
to authenticated
using ((select auth.uid()) = user_id);

create policy "bias_example_hearts_select_own"
on public.bias_example_hearts for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "bias_example_hearts_insert_own"
on public.bias_example_hearts for insert
to authenticated
with check ((select auth.uid()) = user_id);

create policy "bias_example_hearts_delete_own"
on public.bias_example_hearts for delete
to authenticated
using ((select auth.uid()) = user_id);

create policy "bias_example_summaries_public_read"
on public.bias_example_summaries for select
to anon, authenticated
using (true);

revoke all on table public.bias_examples
  from public, anon, authenticated;
revoke all on table public.bias_example_hearts
  from public, anon, authenticated;
revoke all on table public.bias_example_summaries
  from public, anon, authenticated;

grant select, delete
  on table public.bias_examples to authenticated;
grant insert (user_id, bias_id, example_text)
  on table public.bias_examples to authenticated;
grant update (example_text)
  on table public.bias_examples to authenticated;

grant select, delete
  on table public.bias_example_hearts to authenticated;
grant insert (user_id, example_id)
  on table public.bias_example_hearts to authenticated;

grant select
  on table public.bias_example_summaries to anon, authenticated;

comment on table public.bias_examples is
  'One editable public community example per authenticated user and cognitive bias.';
comment on table public.bias_example_hearts is
  'Individual hearts; rows are visible only to the voter.';
comment on table public.bias_example_summaries is
  'Public examples and aggregate heart counts without user identifiers.';
