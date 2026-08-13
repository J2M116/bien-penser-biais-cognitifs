create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create table public.bias_score_summaries (
  bias_id text primary key,
  average_score numeric(5, 1) not null,
  median_score numeric(5, 1) not null,
  ratings_count bigint not null,
  updated_at timestamptz not null default now(),
  constraint bias_score_summaries_count_positive check (ratings_count > 0)
);

alter table public.bias_score_summaries enable row level security;

create policy "bias_score_summaries_public_read"
on public.bias_score_summaries for select
to anon, authenticated
using (true);

revoke all on table public.bias_score_summaries from anon, authenticated;
grant select on table public.bias_score_summaries to anon, authenticated;

create function private.refresh_bias_score_summary(target_bias_id text)
returns void
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
begin
  delete from public.bias_score_summaries where bias_id = target_bias_id;
  insert into public.bias_score_summaries (bias_id, average_score, median_score, ratings_count, updated_at)
  select
    ratings.bias_id,
    round(avg(ratings.score)::numeric, 1),
    round((percentile_cont(0.5) within group (order by ratings.score))::numeric, 1),
    count(*),
    now()
  from public.ratings
  where ratings.bias_id = target_bias_id
  group by ratings.bias_id;
end;
$$;

create function private.sync_bias_score_summary()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public, private
as $$
begin
  if tg_op = 'DELETE' then
    perform private.refresh_bias_score_summary(old.bias_id);
  elsif tg_op = 'UPDATE' then
    perform private.refresh_bias_score_summary(new.bias_id);
    if old.bias_id is distinct from new.bias_id then
      perform private.refresh_bias_score_summary(old.bias_id);
    end if;
  else
    perform private.refresh_bias_score_summary(new.bias_id);
  end if;
  return null;
end;
$$;

revoke all on function private.refresh_bias_score_summary(text) from public, anon, authenticated;
revoke all on function private.sync_bias_score_summary() from public, anon, authenticated;

create trigger ratings_sync_bias_score_summary
after insert or update or delete on public.ratings
for each row execute function private.sync_bias_score_summary();

insert into public.bias_score_summaries (bias_id, average_score, median_score, ratings_count, updated_at)
select
  ratings.bias_id,
  round(avg(ratings.score)::numeric, 1),
  round((percentile_cont(0.5) within group (order by ratings.score))::numeric, 1),
  count(*),
  now()
from public.ratings
group by ratings.bias_id;

drop function public.get_bias_scores();
