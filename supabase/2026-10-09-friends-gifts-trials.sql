-- Online working trials, friends and gifts.
-- 1) The daily online events take the three working trials too (tracking, field hunt, dog team): same rules as the
--    show, race and bay trial (one entry a day, prizes for yesterday's top finishers through hd_claim_prize).
-- 2) Friends: a player keeps a list of other ranches (by player id) to visit and send gifts to.
-- 3) Gifts: send a friend a pup, feed bags or a stud service; they claim it when they next play.
create or replace function public.hd_enter_event(p_pid uuid, p_sec text, p_key text, p_ranch text, p_dog jsonb, p_score numeric)
 returns void language plpgsql security definer set search_path to 'public' as $function$
declare st jsonb := p_dog->'stats';
begin
  perform hd_check(p_pid, p_sec);
  if p_key !~ '^(show|race|bay|track|field|team)-\d{4}-\d{2}-\d{2}$' then raise exception 'bad event'; end if;
  if substring(p_key from '\d{4}-\d{2}-\d{2}')::date <> (now() at time zone 'utc')::date then raise exception 'That event is closed.'; end if;
  if p_score < 0 or p_score > 200 then raise exception 'bad score'; end if;
  if not hd_dog_ok(p_dog) then raise exception 'That dog''s stats are not valid.'; end if;
  -- a race score is speed/stamina/smarts plus up to 15 points of luck, so it can't beat that
  if p_key like 'race-%' and p_score > (st->>'spd')::numeric*.6 + (st->>'sta')::numeric*.3 + (st->>'int')::numeric*.1 + 15.05 then
    raise exception 'bad score';
  end if;
  -- a working-trial score is built from 0-100 ratings plus bonuses; nothing honest gets past 140
  if p_key ~ '^(track|field|team)-' and p_score > 140 then raise exception 'bad score'; end if;
  insert into hd_entries(event_key,event_date,player_id,ranch_name,dog,dog_name,score) values (p_key, (now() at time zone 'utc')::date, p_pid, left(p_ranch,40), p_dog, left(p_dog->>'name',30), p_score);
end $function$;

create table if not exists public.hd_friends(
  player_id uuid not null references public.hd_players(id) on delete cascade,
  friend_id uuid not null references public.hd_players(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key(player_id, friend_id));
alter table public.hd_friends enable row level security;

create table if not exists public.hd_gifts(
  id bigint generated always as identity primary key,
  from_id uuid not null references public.hd_players(id) on delete cascade,
  to_id uuid not null references public.hd_players(id) on delete cascade,
  from_ranch text not null,
  kind text not null check (kind in ('pup','feed','stud')),
  payload jsonb not null,
  note text,
  created_at timestamptz not null default now(),
  claimed_at timestamptz);
create index if not exists hd_gifts_to on public.hd_gifts(to_id) where claimed_at is null;
alter table public.hd_gifts enable row level security;

create or replace function public.hd_friend_add(p_pid uuid, p_sec text, p_friend uuid)
returns void language plpgsql security definer set search_path = public as $$
begin
  perform hd_check(p_pid, p_sec);
  if p_friend is null or p_friend = p_pid then raise exception 'Pick another ranch.'; end if;
  if not exists(select 1 from hd_players where id = p_friend) then raise exception 'That ranch was not found.'; end if;
  if (select count(*) from hd_friends where player_id = p_pid) >= 100 then raise exception 'That is a lot of friends already.'; end if;
  insert into hd_friends(player_id, friend_id) values (p_pid, p_friend) on conflict do nothing;
end $$;

create or replace function public.hd_friend_remove(p_pid uuid, p_sec text, p_friend uuid)
returns void language plpgsql security definer set search_path = public as $$
begin
  perform hd_check(p_pid, p_sec);
  delete from hd_friends where player_id = p_pid and friend_id = p_friend;
end $$;

-- my friends, with their ranch card, and whether they have me on their list too
create or replace function public.hd_friend_list(p_pid uuid, p_sec text)
returns json language plpgsql security definer set search_path = public as $$
begin
  perform hd_check(p_pid, p_sec);
  return coalesce((select json_agg(json_build_object('id', f.friend_id, 'name', r.name, 'level', r.level, 'dogs', r.dog_count, 'hogs', r.hogs,
      'seen', p.last_seen, 'mutual', exists(select 1 from hd_friends x where x.player_id = f.friend_id and x.friend_id = p_pid)) order by p.last_seen desc nulls last)
    from hd_friends f join hd_players p on p.id = f.friend_id left join hd_ranches r on r.player_id = f.friend_id where f.player_id = p_pid), '[]'::json);
end $$;

create or replace function public.hd_gift_send(p_pid uuid, p_sec text, p_to uuid, p_ranch text, p_kind text, p_payload jsonb, p_note text default null)
returns bigint language plpgsql security definer set search_path = public as $$
declare gid bigint; n integer;
begin
  perform hd_check(p_pid, p_sec);
  if p_to is null or p_to = p_pid then raise exception 'Pick another ranch.'; end if;
  if not exists(select 1 from hd_friends where player_id = p_pid and friend_id = p_to) then raise exception 'Add them as a friend first.'; end if;
  if (select count(*) from hd_gifts where from_id = p_pid and created_at > now() - interval '1 day') >= 10 then raise exception 'That is enough gifts for today.'; end if;
  if (select count(*) from hd_gifts where to_id = p_to and claimed_at is null) >= 30 then raise exception 'Their gift box is full.'; end if;
  if p_kind = 'feed' then
    n := coalesce((p_payload->>'n')::integer, 0);
    if n < 1 or n > 30 then raise exception 'Send 1 to 30 bags of feed.'; end if;
  elsif p_kind in ('pup','stud') then
    if not hd_dog_ok(p_payload) then raise exception 'That dog''s stats are not valid.'; end if;
    if p_kind = 'pup' and coalesce((p_payload->>'age')::integer, 99) > 12 then raise exception 'Only pups can be gifted.'; end if;
  else raise exception 'bad gift'; end if;
  insert into hd_gifts(from_id, to_id, from_ranch, kind, payload, note) values (p_pid, p_to, left(coalesce(nullif(trim(p_ranch),''),'A ranch'),40), p_kind, p_payload, left(p_note,140)) returning id into gid;
  begin
    perform hd_push_queue_add(p_to, 'gift:'||gid, 'A gift for your ranch', left(coalesce(nullif(trim(p_ranch),''),'A ranch'),40)||' sent you '||case p_kind when 'pup' then 'a pup' when 'feed' then 'feed' else 'a stud service' end||'.');
  exception when others then null; end;
  return gid;
end $$;

create or replace function public.hd_gift_inbox(p_pid uuid, p_sec text)
returns json language plpgsql security definer set search_path = public as $$
begin
  perform hd_check(p_pid, p_sec);
  return coalesce((select json_agg(json_build_object('id', id, 'from', from_ranch, 'from_id', from_id, 'kind', kind, 'payload', payload, 'note', note, 'at', created_at) order by id)
    from hd_gifts where to_id = p_pid and claimed_at is null), '[]'::json);
end $$;

create or replace function public.hd_gift_claim(p_pid uuid, p_sec text, p_id bigint)
returns json language plpgsql security definer set search_path = public as $$
declare g hd_gifts;
begin
  perform hd_check(p_pid, p_sec);
  update hd_gifts set claimed_at = now() where id = p_id and to_id = p_pid and claimed_at is null returning * into g;
  if g.id is null then return null; end if;
  return json_build_object('id', g.id, 'from', g.from_ranch, 'kind', g.kind, 'payload', g.payload, 'note', g.note);
end $$;

grant execute on function public.hd_friend_add(uuid, text, uuid) to anon, authenticated;
grant execute on function public.hd_friend_remove(uuid, text, uuid) to anon, authenticated;
grant execute on function public.hd_friend_list(uuid, text) to anon, authenticated;
grant execute on function public.hd_gift_send(uuid, text, uuid, text, text, jsonb, text) to anon, authenticated;
grant execute on function public.hd_gift_inbox(uuid, text) to anon, authenticated;
grant execute on function public.hd_gift_claim(uuid, text, bigint) to anon, authenticated;
