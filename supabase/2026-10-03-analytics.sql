-- Game analytics. The game reports a handful of key moments (first session, first hunt, first litter, coming
-- back on later days ...). Admins read the funnel through hd_funnel. RLS on, no policies: only these functions touch it.
create table if not exists public.hd_events(
  id bigint generated always as identity primary key,
  player_id uuid not null references public.hd_players(id) on delete cascade,
  name text not null,
  props jsonb not null default '{}'::jsonb,
  at timestamptz not null default now());
create index if not exists hd_events_name_at on public.hd_events(name, at desc);
create index if not exists hd_events_player on public.hd_events(player_id, at desc);
alter table public.hd_events enable row level security;

create or replace function public.hd_track(p_pid uuid, p_sec text, p_name text, p_props jsonb default '{}'::jsonb)
returns void language plpgsql security definer set search_path = public as $$
begin
  perform hd_check(p_pid, p_sec);
  if p_name !~ '^[a-z][a-z0-9_]{1,39}$' then raise exception 'bad event name'; end if;
  if (select count(*) from hd_events where player_id = p_pid and at > now() - interval '1 day') >= 300 then return; end if;
  insert into hd_events(player_id, name, props) values (p_pid, p_name, case when length(coalesce(p_props,'{}'::jsonb)::text) > 2000 then '{}'::jsonb else coalesce(p_props,'{}'::jsonb) end);
end $$;

-- admin only: how many players reached each step, and how many came back
create or replace function public.hd_funnel(p_pid uuid, p_sec text, p_days integer default 30)
returns json language plpgsql security definer set search_path = public as $$
declare since timestamptz := now() - make_interval(days => least(greatest(coalesce(p_days,30),1),365)); out json;
begin
  perform hd_check(p_pid, p_sec);
  if not exists(select 1 from hd_admins where player_id = p_pid) then raise exception 'Admins only.'; end if;
  with starters as (select player_id, min(at) t0 from hd_events where name = 'session_start' group by player_id having min(at) >= since),
  steps as (select e.name, count(distinct e.player_id) n from hd_events e join starters s using(player_id) group by e.name),
  back as (select count(distinct s.player_id) filter (where exists(select 1 from hd_events e where e.player_id = s.player_id and e.name = 'session_start' and e.at >= s.t0 + interval '20 hours' and e.at < s.t0 + interval '48 hours'))::int d1,
                  count(distinct s.player_id) filter (where exists(select 1 from hd_events e where e.player_id = s.player_id and e.name = 'session_start' and e.at >= s.t0 + interval '6 days'))::int d7,
                  count(*)::int total from starters s),
  daily as (select to_char(date_trunc('day', at), 'YYYY-MM-DD') d, count(distinct player_id) n from hd_events where name = 'session_start' and at >= now() - interval '14 days' group by 1 order by 1)
  select json_build_object('players', (select total from back), 'day1', (select d1 from back), 'day7', (select d7 from back),
    'steps', coalesce((select json_object_agg(name, n) from steps), '{}'::json),
    'daily', coalesce((select json_agg(json_build_object('day', d, 'players', n)) from daily), '[]'::json)) into out;
  return out;
end $$;

revoke all on function public.hd_track(uuid, text, text, jsonb) from public;
revoke all on function public.hd_funnel(uuid, text, integer) from public;
grant execute on function public.hd_track(uuid, text, text, jsonb) to anon, authenticated;
grant execute on function public.hd_funnel(uuid, text, integer) to anon, authenticated;
