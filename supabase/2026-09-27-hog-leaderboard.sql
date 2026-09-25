-- Biggest-hog leaderboard. Every hog a player catches is recorded through hd_record_hog, which checks the
-- player's secret, that the hog type is real and that its weight is possible for that type (the heaviest
-- boar of a type plus the most land and upgrade bonuses can add), and allows one catch a minute.
-- The table has RLS on and no policies: nobody writes to it directly, and the board is read through hd_hog_board.
create table if not exists public.hd_hog_catches(
  id bigint generated always as identity primary key,
  player_id uuid not null references public.hd_players(id) on delete cascade,
  ranch_name text not null,
  hog_key text not null,
  hog_name text not null,
  weight integer not null,
  area text not null,
  dogs text not null default '',
  caught_at timestamptz not null default now());
alter table public.hd_hog_catches enable row level security;
create index if not exists hd_hog_catches_weight on public.hd_hog_catches(weight desc);
create index if not exists hd_hog_catches_player on public.hd_hog_catches(player_id, caught_at desc);

create or replace function public.hd_record_hog(p_pid uuid, p_sec text, p_ranch text, p_hog text, p_weight integer, p_area text, p_dogs text)
returns void language plpgsql security definer set search_path = public as $$
declare maxw integer; nm text;
begin
  perform hd_check(p_pid, p_sec);
  select m, n into maxw, nm from (values ('feral',150,'Feral hog'),('razor',220,'Razorback'),('spotted',260,'Spotted boar'),('russian',350,'Russian-cross boar'),('ghost',460,'Ghost boar')) v(k,m,n) where k = p_hog;
  if maxw is null then raise exception 'unknown hog'; end if;
  -- terrain and hunting-access upgrades add at most 17% to a hog's weight
  if p_weight < 20 or p_weight > ceil(maxw * 1.18) then raise exception 'That weight is not possible.'; end if;
  if p_area not in ('creek','pine','swamp','thicket') then raise exception 'unknown area'; end if;
  if exists (select 1 from hd_hog_catches where player_id = p_pid and caught_at > now() - interval '60 seconds') then raise exception 'Too many catches too quickly.'; end if;
  insert into hd_hog_catches(player_id, ranch_name, hog_key, hog_name, weight, area, dogs)
  values (p_pid, left(coalesce(nullif(trim(p_ranch),''),'A ranch'),40), p_hog, nm, p_weight, p_area, left(coalesce(p_dogs,''),80));
end $$;

-- each player's single biggest hog, all time or in the last 7 days
create or replace function public.hd_hog_board(p_period text default 'all', p_limit integer default 50)
returns table(player_id uuid, ranch_name text, hog_name text, hog_key text, weight integer, area text, dogs text, caught_at timestamptz)
language sql stable security definer set search_path = public as $$
  select * from (
    select distinct on (c.player_id) c.player_id, c.ranch_name, c.hog_name, c.hog_key, c.weight, c.area, c.dogs, c.caught_at
    from hd_hog_catches c
    where p_period = 'all' or c.caught_at > now() - interval '7 days'
    order by c.player_id, c.weight desc, c.caught_at asc) best
  order by weight desc, caught_at asc
  limit least(greatest(coalesce(p_limit,50),1),100)
$$;

grant execute on function public.hd_record_hog(uuid, text, text, text, integer, text, text) to anon, authenticated;
grant execute on function public.hd_hog_board(text, integer) to anon, authenticated;
