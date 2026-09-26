-- Weekly tournament. Weeks run Monday 00:00 UTC to the next Monday. Three boards:
--   heaviest: each ranch's heaviest verified catch of the week (hd_hog_catches, recorded through hd_record_hog)
--   most:     how many verified catches each ranch made that week
--   breeder:  each ranch's best pup of the week, by its overall genetic potential (hd_record_litter)
-- The top three of each board win a prize, collected once through hd_tourney_claim after the week ends.
-- RLS on, no policies: only these functions touch the tables.
create table if not exists public.hd_litters(
  id bigint generated always as identity primary key,
  player_id uuid not null references public.hd_players(id) on delete cascade,
  ranch_name text not null,
  breed text not null,
  pup_name text not null,
  score integer not null,
  bred_at timestamptz not null default now());
create index if not exists hd_litters_when on public.hd_litters(bred_at desc);
alter table public.hd_litters enable row level security;

create table if not exists public.hd_tourney_claims(
  player_id uuid not null references public.hd_players(id) on delete cascade,
  week date not null,
  event text not null,
  place integer not null,
  claimed_at timestamptz not null default now(),
  primary key(player_id, week, event));
alter table public.hd_tourney_claims enable row level security;

create or replace function public.hd_record_litter(p_pid uuid, p_sec text, p_ranch text, p_breed text, p_pup text, p_score integer)
returns void language plpgsql security definer set search_path = public as $$
begin
  perform hd_check(p_pid, p_sec);
  if p_score < 0 or p_score > 99 then raise exception 'That score is not possible.'; end if;
  if exists (select 1 from hd_litters where player_id = p_pid and bred_at > now() - interval '30 seconds') then raise exception 'Too many litters too quickly.'; end if;
  if (select count(*) from hd_litters where player_id = p_pid and bred_at > now() - interval '1 day') >= 40 then raise exception 'Too many litters today.'; end if;
  insert into hd_litters(player_id, ranch_name, breed, pup_name, score)
  values (p_pid, left(coalesce(nullif(trim(p_ranch),''),'A ranch'),40), left(coalesce(p_breed,''),40), left(coalesce(p_pup,''),30), p_score);
end $$;

-- one board for one week: p_week_offset 0 = this week, -1 = last week ...
create or replace function public.hd_tourney_board(p_event text, p_week_offset integer default 0, p_limit integer default 20)
returns table(player_id uuid, ranch_name text, value integer, detail text, place bigint)
language plpgsql stable security definer set search_path = public as $$
declare ws timestamptz := date_trunc('week', now() at time zone 'utc') at time zone 'utc' + make_interval(weeks => coalesce(p_week_offset,0));
        we timestamptz := ws + interval '7 days'; lim integer := least(greatest(coalesce(p_limit,20),1),100);
begin
  if p_event = 'heaviest' then
    return query select b.player_id, b.ranch_name, b.weight, b.hog_name, rank() over (order by b.weight desc, b.caught_at asc) from (
      select distinct on (c.player_id) c.player_id, c.ranch_name, c.weight, c.hog_name, c.caught_at from hd_hog_catches c
      where c.caught_at >= ws and c.caught_at < we order by c.player_id, c.weight desc, c.caught_at asc) b order by 5 limit lim;
  elsif p_event = 'most' then
    return query select c.player_id, (array_agg(c.ranch_name order by c.caught_at desc))[1], count(*)::integer, ('biggest '||max(c.weight)||' lb')::text,
      rank() over (order by count(*) desc, max(c.weight) desc) from hd_hog_catches c where c.caught_at >= ws and c.caught_at < we group by c.player_id order by 5 limit lim;
  elsif p_event = 'breeder' then
    return query select b.player_id, b.ranch_name, b.score, (b.pup_name||', '||b.breed)::text, rank() over (order by b.score desc, b.bred_at asc) from (
      select distinct on (l.player_id) l.player_id, l.ranch_name, l.score, l.pup_name, l.breed, l.bred_at from hd_litters l
      where l.bred_at >= ws and l.bred_at < we order by l.player_id, l.score desc, l.bred_at asc) b order by 5 limit lim;
  else raise exception 'unknown event'; end if;
end $$;

-- prizes: every top-three finish in the last eight finished weeks that hasn't been collected yet
create or replace function public.hd_tourney_claim(p_pid uuid, p_sec text)
returns json language plpgsql security definer set search_path = public as $$
declare w integer; e text; r record; out json := '[]'::json; acc jsonb := '[]'::jsonb; wk date;
begin
  perform hd_check(p_pid, p_sec);
  for w in 1..8 loop
    wk := (date_trunc('week', now() at time zone 'utc') - make_interval(weeks => w))::date;
    foreach e in array array['heaviest','most','breeder'] loop
      for r in select * from hd_tourney_board(e, -w, 3) b where b.player_id = p_pid and b.place <= 3 loop
        insert into hd_tourney_claims(player_id, week, event, place) values (p_pid, wk, e, r.place) on conflict do nothing;
        if found then acc := acc || jsonb_build_object('week', wk, 'event', e, 'place', r.place, 'value', r.value, 'detail', r.detail); end if;
      end loop;
    end loop;
  end loop;
  return acc::json;
end $$;

revoke all on function public.hd_record_litter(uuid, text, text, text, text, integer) from public;
revoke all on function public.hd_tourney_claim(uuid, text) from public;
grant execute on function public.hd_record_litter(uuid, text, text, text, text, integer) to anon, authenticated;
grant execute on function public.hd_tourney_board(text, integer, integer) to anon, authenticated;
grant execute on function public.hd_tourney_claim(uuid, text) to anon, authenticated;
