-- Hunting clubs: the hunting groups grow a club chat, a weekly club leaderboard (total pounds of hog the members
-- catch that week) and prizes for the top three clubs, paid to every member once the week is over.
alter table public.hd_groups add column if not exists motto text;

create table if not exists public.hd_club_chat(
  id bigint generated always as identity primary key,
  group_id bigint not null references public.hd_groups(id) on delete cascade,
  player_id uuid not null references public.hd_players(id) on delete cascade,
  ranch text not null, msg text not null, at timestamptz not null default now());
create index if not exists hd_club_chat_group on public.hd_club_chat(group_id, id desc);
alter table public.hd_club_chat enable row level security;

create table if not exists public.hd_club_claims(
  player_id uuid not null references public.hd_players(id) on delete cascade,
  week date not null, group_id bigint, place integer not null, prize integer not null,
  claimed_at timestamptz not null default now(), primary key(player_id, week));
alter table public.hd_club_claims enable row level security;

create or replace function public.hd_club_member(p_pid uuid, p_gid bigint) returns boolean language sql stable security definer set search_path = public as $$
  select exists(select 1 from hd_group_members where group_id = p_gid and player_id = p_pid) $$;
revoke all on function public.hd_club_member(uuid, bigint) from public, anon, authenticated;

create or replace function public.hd_club_post(p_pid uuid, p_sec text, p_gid bigint, p_ranch text, p_msg text)
returns void language plpgsql security definer set search_path = public as $$
declare m text := left(trim(coalesce(p_msg,'')), 300); gname text; r uuid;
begin
  perform hd_check(p_pid, p_sec);
  if not hd_club_member(p_pid, p_gid) then raise exception 'You are not in that club.'; end if;
  if length(m) < 1 then return; end if;
  if exists(select 1 from hd_club_chat where player_id = p_pid and at > now() - interval '2 seconds') then raise exception 'Slow down a little.'; end if;
  if (select count(*) from hd_club_chat where player_id = p_pid and at > now() - interval '1 day') >= 300 then raise exception 'That is enough chat for today.'; end if;
  insert into hd_club_chat(group_id, player_id, ranch, msg) values (p_gid, p_pid, left(coalesce(nullif(trim(p_ranch),''),'A ranch'),40), m);
  delete from hd_club_chat where group_id = p_gid and id < (select min(id) from (select id from hd_club_chat where group_id = p_gid order by id desc limit 200) k);
  select name into gname from hd_groups where id = p_gid;
  for r in select player_id from hd_group_members where group_id = p_gid and player_id <> p_pid loop
    perform hd_push_queue_add(r, 'club:'||p_gid, coalesce(gname,'Your club'), left(coalesce(nullif(trim(p_ranch),''),'A ranch'),40)||': '||left(m,120));
  end loop;
end $$;

create or replace function public.hd_club_chat_read(p_pid uuid, p_sec text, p_gid bigint, p_after bigint default 0)
returns json language plpgsql security definer set search_path = public as $$
begin
  perform hd_check(p_pid, p_sec);
  if not hd_club_member(p_pid, p_gid) then raise exception 'You are not in that club.'; end if;
  return coalesce((select json_agg(x order by x.id) from (select id, player_id, ranch, msg, at from hd_club_chat where group_id = p_gid and id > coalesce(p_after,0) order by id desc limit 60) x), '[]'::json);
end $$;

-- one week's club standings: pounds of hog caught by the members that week
create or replace function public.hd_club_board(p_week_offset integer default 0, p_limit integer default 30)
returns table(group_id bigint, name text, members bigint, hogs bigint, pounds bigint, place bigint)
language plpgsql stable security definer set search_path = public as $$
declare ws timestamptz := date_trunc('week', now() at time zone 'utc') at time zone 'utc' + make_interval(weeks => coalesce(p_week_offset,0)); we timestamptz := ws + interval '7 days';
begin
  return query select g.id, g.name, (select count(*) from hd_group_members m2 where m2.group_id = g.id),
    count(c.id), coalesce(sum(c.weight),0)::bigint, rank() over (order by coalesce(sum(c.weight),0) desc, count(c.id) desc)
  from hd_groups g join hd_group_members m on m.group_id = g.id and m.joined_at < we
  join hd_hog_catches c on c.player_id = m.player_id and c.caught_at >= ws and c.caught_at < we
  group by g.id, g.name order by 6 limit least(greatest(coalesce(p_limit,30),1),100);
end $$;

-- prizes for the last four finished weeks: every member of a top-three club (joined before the week ended), once a week
create or replace function public.hd_club_claim(p_pid uuid, p_sec text)
returns json language plpgsql security definer set search_path = public as $$
declare w integer; wk date; r record; acc jsonb := '[]'::jsonb; prize integer;
begin
  perform hd_check(p_pid, p_sec);
  for w in 1..4 loop
    wk := (date_trunc('week', now() at time zone 'utc') - make_interval(weeks => w))::date;
    select b.* into r from hd_club_board(-w, 3) b join hd_group_members m on m.group_id = b.group_id and m.player_id = p_pid
      where b.place <= 3 and b.members >= 2 and m.joined_at < (wk + 7)::timestamptz order by b.place limit 1;
    if found then prize := (array[3000,1500,750])[r.place];
      insert into hd_club_claims(player_id, week, group_id, place, prize) values (p_pid, wk, r.group_id, r.place, prize) on conflict do nothing;
      if found then acc := acc || jsonb_build_object('week', wk, 'club', r.name, 'place', r.place, 'prize', prize, 'pounds', r.pounds); end if;
    end if;
  end loop;
  return acc::json;
end $$;

create or replace function public.hd_club_motto(p_pid uuid, p_sec text, p_gid bigint, p_motto text)
returns void language plpgsql security definer set search_path = public as $$
begin
  perform hd_check(p_pid, p_sec);
  update hd_groups set motto = left(trim(coalesce(p_motto,'')),80) where id = p_gid and owner = p_pid;
  if not found then raise exception 'Only the club leader can change that.'; end if;
end $$;

revoke all on function public.hd_club_post(uuid, text, bigint, text, text) from public;
revoke all on function public.hd_club_chat_read(uuid, text, bigint, bigint) from public;
revoke all on function public.hd_club_claim(uuid, text) from public;
revoke all on function public.hd_club_motto(uuid, text, bigint, text) from public;
grant execute on function public.hd_club_post(uuid, text, bigint, text, text) to anon, authenticated;
grant execute on function public.hd_club_chat_read(uuid, text, bigint, bigint) to anon, authenticated;
grant execute on function public.hd_club_board(integer, integer) to anon, authenticated;
grant execute on function public.hd_club_claim(uuid, text) to anon, authenticated;
grant execute on function public.hd_club_motto(uuid, text, bigint, text) to anon, authenticated;
