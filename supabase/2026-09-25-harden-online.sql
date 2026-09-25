-- Tighten the online RPCs so a player can't mint money or post impossible dogs.

-- payer of a group-hunt payout, so we can cap how much one player sends
alter table public.hd_payouts add column if not exists payer uuid;

-- a dog's stats and potentials must be numbers from 0 to 99
create or replace function public.hd_dog_ok(d jsonb) returns boolean
language sql immutable set search_path = public as $$
  select jsonb_typeof(d) = 'object'
     and jsonb_typeof(d->'stats') = 'object' and jsonb_typeof(d->'pot') = 'object'
     and not exists (
       select 1 from (select value from jsonb_each(d->'stats') union all select value from jsonb_each(d->'pot')) v
       where jsonb_typeof(v.value) <> 'number' or v.value::numeric < 0 or v.value::numeric > 99)
$$;

create or replace function public.hd_pay_guest(p_pid uuid, p_sec text, p_owner uuid, p_amount integer, p_reason text)
returns void language plpgsql security definer set search_path = public as $$
begin
  perform hd_check(p_pid, p_sec);
  if p_owner = p_pid then return; end if;
  if p_amount < 1 or p_amount > 5000 then raise exception 'bad amount'; end if;
  -- only dogs from someone in one of your hunting groups can earn a share
  if not exists (select 1 from hd_group_members a join hd_group_members b on a.group_id = b.group_id
                 where a.player_id = p_pid and b.player_id = p_owner) then
    raise exception 'You are not in a hunting group with that ranch.';
  end if;
  if (select count(*) from hd_payouts where payer = p_pid and created_at > now() - interval '1 day') >= 20 then return; end if;
  if (select count(*) from hd_payouts where reason like 'Group hunt%' and created_at > now() - interval '1 hour' and player_id = p_owner) > 30 then return; end if;
  insert into hd_payouts(player_id, amount, reason, payer) values (p_owner, p_amount, left('Group hunt: ' || coalesce(p_reason,''),120), p_pid);
end $$;

create or replace function public.hd_list_dog(p_pid uuid, p_sec text, p_kind text, p_dog jsonb, p_price integer, p_ranch text)
returns bigint language plpgsql security definer set search_path = public as $$
declare lid bigint;
begin
  perform hd_check(p_pid, p_sec);
  if p_kind not in ('sale','stud') then raise exception 'bad listing type'; end if;
  if p_price is null or p_price < 1 or p_price > 1000000 then raise exception 'Prices must be between $1 and $1,000,000.'; end if;
  if not hd_dog_ok(p_dog) then raise exception 'That dog''s stats are not valid.'; end if;
  if (select count(*) from hd_listings where seller = p_pid and status = 'open') >= 12 then raise exception 'too many open listings'; end if;
  if pg_column_size(p_dog) > 60000 then raise exception 'dog too large'; end if;
  insert into hd_listings(seller,seller_ranch,kind,dog,dog_name,breed,price) values (p_pid, left(p_ranch,40), p_kind, p_dog, left(p_dog->>'name',30), left(coalesce(p_dog->>'cross',p_dog->>'breed'),40), p_price) returning id into lid;
  return lid;
end $$;

create or replace function public.hd_offer_trade(p_pid uuid, p_sec text, p_to uuid, p_offer jsonb, p_money integer, p_want jsonb, p_from_ranch text, p_to_ranch text)
returns bigint language plpgsql security definer set search_path = public as $$
declare tid bigint;
begin
  perform hd_check(p_pid, p_sec);
  if p_to = p_pid then raise exception 'cannot trade with yourself'; end if;
  if jsonb_typeof(coalesce(p_offer,'[]'::jsonb)) <> 'array' or jsonb_array_length(coalesce(p_offer,'[]'::jsonb)) > 3 then raise exception 'bad offer'; end if;
  if exists (select 1 from jsonb_array_elements(coalesce(p_offer,'[]'::jsonb)) o where not hd_dog_ok(o)) then raise exception 'One of the offered dogs has invalid stats.'; end if;
  if coalesce(p_money,0) > 10000000 then raise exception 'bad amount'; end if;
  if (select count(*) from hd_trades where from_user = p_pid and status = 'pending') >= 10 then raise exception 'too many pending offers'; end if;
  if pg_column_size(p_offer) > 200000 then raise exception 'offer too large'; end if;
  insert into hd_trades(from_user,from_ranch,to_user,to_ranch,offer,money,want_dog,want_dog_id) values (p_pid, left(p_from_ranch,40), p_to, left(p_to_ranch,40), coalesce(p_offer,'[]'::jsonb), greatest(0,coalesce(p_money,0)), p_want, p_want->>'id') returning id into tid;
  return tid;
end $$;

create or replace function public.hd_enter_event(p_pid uuid, p_sec text, p_key text, p_ranch text, p_dog jsonb, p_score numeric)
returns void language plpgsql security definer set search_path = public as $$
declare st jsonb := p_dog->'stats';
begin
  perform hd_check(p_pid, p_sec);
  if p_key !~ '^(show|race)-\d{4}-\d{2}-\d{2}$' then raise exception 'bad event'; end if;
  if substring(p_key from '\d{4}-\d{2}-\d{2}')::date <> (now() at time zone 'utc')::date then raise exception 'That event is closed.'; end if;
  if p_score < 0 or p_score > 200 then raise exception 'bad score'; end if;
  if not hd_dog_ok(p_dog) then raise exception 'That dog''s stats are not valid.'; end if;
  -- a race score is speed/stamina/smarts plus up to 15 points of luck, so it can't beat that
  if p_key like 'race-%' and p_score > (st->>'spd')::numeric*.6 + (st->>'sta')::numeric*.3 + (st->>'int')::numeric*.1 + 15.05 then
    raise exception 'bad score';
  end if;
  insert into hd_entries(event_key,event_date,player_id,ranch_name,dog,dog_name,score) values (p_key, (now() at time zone 'utc')::date, p_pid, left(p_ranch,40), p_dog, left(p_dog->>'name',30), p_score);
end $$;

create or replace function public.hd_publish_ranch(p_pid uuid, p_sec text, p_name text, p_level integer, p_net bigint, p_hogs integer, p_dogs integer, p_line text, p_snapshot jsonb)
returns void language plpgsql security definer set search_path = public as $$
begin
  perform hd_check(p_pid, p_sec);
  if pg_column_size(p_snapshot) > 600000 then raise exception 'snapshot too large'; end if;
  -- published dogs can be borrowed for hunts, so they must be valid too
  if exists (select 1 from jsonb_array_elements(case when jsonb_typeof(p_snapshot)='array' then p_snapshot else '[]'::jsonb end) o where not hd_dog_ok(o)) then
    raise exception 'One of your dogs has invalid stats.';
  end if;
  insert into hd_ranches(player_id,name,level,net_worth,hogs,dog_count,best_line,snapshot,updated_at) values (p_pid, left(coalesce(p_name,'Ranch'),40), greatest(1,p_level), greatest(0,p_net), greatest(0,p_hogs), greatest(0,p_dogs), left(p_line,60), coalesce(p_snapshot,'[]'::jsonb), now())
  on conflict (player_id) do update set name=excluded.name, level=excluded.level, net_worth=excluded.net_worth, hogs=excluded.hogs, dog_count=excluded.dog_count, best_line=excluded.best_line, snapshot=excluded.snapshot, updated_at=now();
end $$;

-- the checker is only called from the functions above
revoke execute on function public.hd_dog_ok(jsonb) from public, anon, authenticated;
