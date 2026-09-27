-- Hunting Pass (seasons). The server keeps each player's Season XP for a season and every reward they have claimed,
-- so a reward can never be collected twice (on any device), and Season XP can't grow faster than real play allows.
--   hd_now()                   server clock for the season timer and the daily/weekly challenge resets
--   hd_season_sync             report Season XP; the server keeps it, capped by elapsed time, and returns its record
--   hd_season_claim_many       claim reward keys: level rewards ('F12' free, 'P12' premium) need enough server XP
--                              (and premium ownership for 'P'); challenge and mission keys ('D:..','W:..','M:..') just
--                              can't repeat. Returns which keys were accepted, already claimed, or must wait.
--   hd_season_premium          record the Premium Hunting Pass for this season
-- RLS on, no policies: only these functions touch the table.
create table if not exists public.hd_season(
  player_id uuid not null references public.hd_players(id) on delete cascade,
  season_id text not null,
  xp integer not null default 0,
  premium boolean not null default false,
  claimed text[] not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key(player_id, season_id));
alter table public.hd_season enable row level security;

create or replace function public.hd_now() returns timestamptz language sql stable as $$ select now() $$;
grant execute on function public.hd_now() to anon, authenticated;

-- level L needs (L-1)*1000 + 25*(L-1)*(L-2)/2 total Season XP (level 2 at 1,000, level 100 at 220,275)
create or replace function public.hd_season_need(p_level integer) returns integer language sql immutable as $$
  select greatest(0, (p_level-1)*1000 + 25*(p_level-1)*(p_level-2)/2) $$;

create or replace function public.hd_season_sync(p_pid uuid, p_sec text, p_season text, p_xp integer)
returns json language plpgsql security definer set search_path = public as $$
declare r hd_season; cap integer; nx integer;
begin
  perform hd_check(p_pid, p_sec);
  if p_season !~ '^s[0-9]{1,3}$' then raise exception 'bad season'; end if;
  insert into hd_season(player_id, season_id) values (p_pid, p_season) on conflict do nothing;
  select * into r from hd_season where player_id = p_pid and season_id = p_season for update;
  -- Season XP can only grow as fast as real play: a 20,000 head start plus 12,000 for every hour since the player
  -- joined this season (measured on the server's clock, so repeated reports can't stack bursts)
  cap := 20000 + (12000 * extract(epoch from now() - r.created_at) / 3600)::integer;
  nx := greatest(r.xp, least(coalesce(p_xp,0), cap, 400000));
  update hd_season set xp = nx, updated_at = now() where player_id = p_pid and season_id = p_season;
  return json_build_object('xp', nx, 'premium', r.premium, 'claimed', r.claimed, 'now', now());
end $$;

create or replace function public.hd_season_claim_many(p_pid uuid, p_sec text, p_season text, p_keys text[])
returns json language plpgsql security definer set search_path = public as $$
declare r hd_season; k text; lv integer; okk text[] := '{}'; dup text[] := '{}'; wt text[] := '{}';
begin
  perform hd_check(p_pid, p_sec);
  insert into hd_season(player_id, season_id) values (p_pid, p_season) on conflict do nothing;
  select * into r from hd_season where player_id = p_pid and season_id = p_season for update;
  foreach k in array coalesce(p_keys, '{}') loop
    if k is null or length(k) > 60 or k !~ '^([FP][0-9]{1,3}|[DWMS]:[A-Za-z0-9_:-]{1,50})$' then continue; end if;
    if k = any(r.claimed) or k = any(okk) then dup := dup || k; continue; end if;
    if k ~ '^[FP][0-9]+$' then
      lv := substr(k, 2)::integer;
      if lv < 1 or lv > 100 or r.xp < hd_season_need(lv) or (left(k,1) = 'P' and not r.premium) then wt := wt || k; continue; end if;
    end if;
    okk := okk || k;
  end loop;
  if array_length(okk, 1) > 0 then update hd_season set claimed = claimed || okk, updated_at = updated_at where player_id = p_pid and season_id = p_season; end if;
  return json_build_object('ok', okk, 'dup', dup, 'wait', wt);
end $$;

create or replace function public.hd_season_premium(p_pid uuid, p_sec text, p_season text)
returns boolean language plpgsql security definer set search_path = public as $$
begin
  perform hd_check(p_pid, p_sec);
  insert into hd_season(player_id, season_id, premium) values (p_pid, p_season, true)
  on conflict (player_id, season_id) do update set premium = true;
  return true;
end $$;

revoke all on function public.hd_season_need(integer) from public, anon, authenticated;
revoke all on function public.hd_season_sync(uuid, text, text, integer) from public;
revoke all on function public.hd_season_claim_many(uuid, text, text, text[]) from public;
revoke all on function public.hd_season_premium(uuid, text, text) from public;
grant execute on function public.hd_season_sync(uuid, text, text, integer) to anon, authenticated;
grant execute on function public.hd_season_claim_many(uuid, text, text, text[]) to anon, authenticated;
grant execute on function public.hd_season_premium(uuid, text, text) to anon, authenticated;
