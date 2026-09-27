-- 1) The online market takes horses and hogs as well as dogs (sale or stud service). Listings keep their existing
--    shape; a new column says what kind of animal is in the "dog" JSON.
alter table public.hd_listings add column if not exists animal text not null default 'dog';

create or replace function public.hd_list_animal(p_pid uuid, p_sec text, p_animal text, p_kind text, p_data jsonb, p_price integer, p_ranch text)
returns bigint language plpgsql security definer set search_path = public as $$
declare lid bigint;
begin
  perform hd_check(p_pid, p_sec);
  if p_animal not in ('horse','hog') then raise exception 'bad animal'; end if;
  if p_kind not in ('sale','stud') then raise exception 'bad listing type'; end if;
  if p_price is null or p_price < 1 or p_price > 1000000 then raise exception 'Prices must be between $1 and $1,000,000.'; end if;
  if jsonb_typeof(p_data) <> 'object' or coalesce(p_data->>'name','') = '' then raise exception 'That animal is not valid.'; end if;
  if pg_column_size(p_data) > 60000 then raise exception 'too large'; end if;
  if (select count(*) from hd_listings where seller = p_pid and status = 'open') >= 12 then raise exception 'too many open listings'; end if;
  insert into hd_listings(seller, seller_ranch, kind, dog, dog_name, breed, price, animal)
  values (p_pid, left(p_ranch,40), p_kind, p_data, left(p_data->>'name',30), left(coalesce(p_data->>'breed', p_data->>'type', p_animal),40), p_price, p_animal) returning id into lid;
  return lid;
end $$;

create or replace function public.hd_cancel_listing(p_pid uuid, p_sec text, p_id bigint)
returns jsonb language plpgsql security definer set search_path = public as $$
declare l hd_listings;
begin
  perform hd_check(p_pid, p_sec);
  select * into l from hd_listings where id = p_id and seller = p_pid and status = 'open' for update;
  if not found then raise exception 'listing not open'; end if;
  update hd_listings set status = 'cancelled', closed_at = now() where id = p_id;
  return json_build_object('kind', l.kind, 'dog', l.dog, 'animal', l.animal)::jsonb;
end $$;

create or replace function public.hd_buy_listing(p_pid uuid, p_sec text, p_id bigint)
returns jsonb language plpgsql security definer set search_path = public as $$
declare l hd_listings; what text;
begin
  perform hd_check(p_pid, p_sec);
  select * into l from hd_listings where id = p_id and status = 'open' for update;
  if not found then raise exception 'That listing is no longer available.'; end if;
  if l.seller = p_pid then raise exception 'You cannot buy your own listing.'; end if;
  what := case l.animal when 'horse' then 'a horse' when 'hog' then 'a hog' else 'a dog' end;
  if l.kind = 'sale' then
    update hd_listings set status = 'sold', buyer = p_pid, closed_at = now() where id = p_id;
    insert into hd_payouts(player_id, amount, reason) values (l.seller, l.price, 'Sold ' || coalesce(l.dog_name, what) || ' on the online market');
  else
    update hd_listings set uses = uses + 1 where id = p_id;
    insert into hd_payouts(player_id, amount, reason) values (l.seller, l.price, 'Stud fee for ' || coalesce(l.dog_name,'your stud'));
  end if;
  return json_build_object('kind', l.kind, 'dog', l.dog, 'price', l.price, 'seller_ranch', l.seller_ranch, 'animal', l.animal)::jsonb;
end $$;

revoke all on function public.hd_list_animal(uuid, text, text, text, jsonb, integer, text) from public;
grant execute on function public.hd_list_animal(uuid, text, text, text, jsonb, integer, text) to anon, authenticated;

-- 2) Co-op hunts. The host opens a room and gets a six-letter code; a friend joins with it and lends a dog. The
--    host's game runs the hunt and posts a small snapshot every second or two; the partner watches it live and can
--    send a few commands (release the catch dogs, call out). When the hunt ends the host posts the result and the
--    partner's game collects the pay and the dog's experience once.
create table if not exists public.hd_coop(
  code text primary key,
  host uuid not null references public.hd_players(id) on delete cascade,
  host_ranch text not null,
  guest uuid references public.hd_players(id) on delete cascade,
  guest_ranch text, guest_dog jsonb,
  status text not null default 'open',
  state jsonb, cmds jsonb not null default '[]'::jsonb, result jsonb,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now());
alter table public.hd_coop enable row level security;

create or replace function public.hd_coop_open(p_pid uuid, p_sec text, p_ranch text)
returns text language plpgsql security definer set search_path = public, extensions as $$
declare c text; i integer := 0;
begin
  perform hd_check(p_pid, p_sec);
  delete from hd_coop where updated_at < now() - interval '1 day';
  update hd_coop set status = 'done' where host = p_pid and status in ('open','live');
  loop
    c := upper(substr(translate(encode(gen_random_bytes(8),'base64'),'+/=01OIl',''),1,6)); i := i + 1;
    exit when length(c) = 6 and not exists(select 1 from hd_coop where code = c);
    if i > 20 then raise exception 'try again'; end if;
  end loop;
  insert into hd_coop(code, host, host_ranch) values (c, p_pid, left(coalesce(nullif(trim(p_ranch),''),'A ranch'),40));
  return c;
end $$;

create or replace function public.hd_coop_join(p_pid uuid, p_sec text, p_code text, p_ranch text, p_dog jsonb)
returns json language plpgsql security definer set search_path = public as $$
declare r hd_coop;
begin
  perform hd_check(p_pid, p_sec);
  select * into r from hd_coop where code = upper(trim(p_code)) for update;
  if not found or r.status <> 'open' then raise exception 'No open hunt with that code.'; end if;
  if r.host = p_pid then raise exception 'That is your own hunt.'; end if;
  if r.guest is not null and r.guest <> p_pid then raise exception 'Someone already joined that hunt.'; end if;
  if p_dog is not null and not hd_dog_ok(p_dog) then raise exception 'That dog is not valid.'; end if;
  if pg_column_size(p_dog) > 60000 then raise exception 'too large'; end if;
  update hd_coop set guest = p_pid, guest_ranch = left(coalesce(nullif(trim(p_ranch),''),'A ranch'),40), guest_dog = p_dog, updated_at = now() where code = r.code;
  perform hd_push_queue_add(r.host, 'coop:'||r.code, 'Your partner is here', left(coalesce(nullif(trim(p_ranch),''),'A ranch'),40)||' joined your hunt. Turn out the dogs!');
  return json_build_object('code', r.code, 'host_ranch', r.host_ranch);
end $$;

create or replace function public.hd_coop_poll(p_pid uuid, p_sec text, p_code text)
returns json language plpgsql security definer set search_path = public as $$
declare r hd_coop;
begin
  perform hd_check(p_pid, p_sec);
  select * into r from hd_coop where code = upper(trim(p_code));
  if not found or (r.host <> p_pid and r.guest is distinct from p_pid) then raise exception 'That hunt is gone.'; end if;
  return json_build_object('code', r.code, 'host_ranch', r.host_ranch, 'guest_ranch', r.guest_ranch, 'guest_dog', case when r.host = p_pid then r.guest_dog end,
    'status', r.status, 'state', r.state, 'result', r.result, 'age', extract(epoch from now() - r.updated_at)::int);
end $$;

-- host: post the live picture (and at the end the result); hands back and clears the partner's commands
create or replace function public.hd_coop_state(p_pid uuid, p_sec text, p_code text, p_state jsonb, p_status text, p_result jsonb default null)
returns jsonb language plpgsql security definer set search_path = public as $$
declare r hd_coop; out jsonb;
begin
  perform hd_check(p_pid, p_sec);
  select * into r from hd_coop where code = upper(trim(p_code)) and host = p_pid for update;
  if not found then raise exception 'That hunt is gone.'; end if;
  if p_status not in ('open','live','done') then raise exception 'bad status'; end if;
  if pg_column_size(p_state) > 30000 or pg_column_size(p_result) > 20000 then raise exception 'too large'; end if;
  out := r.cmds;
  update hd_coop set state = coalesce(p_state, state), status = p_status, result = coalesce(p_result, result), cmds = '[]'::jsonb, updated_at = now() where code = r.code;
  return out;
end $$;

create or replace function public.hd_coop_cmd(p_pid uuid, p_sec text, p_code text, p_cmd jsonb)
returns void language plpgsql security definer set search_path = public as $$
begin
  perform hd_check(p_pid, p_sec);
  update hd_coop set cmds = (case when jsonb_array_length(cmds) >= 20 then cmds - 0 else cmds end) || jsonb_build_array(p_cmd)
  where code = upper(trim(p_code)) and guest = p_pid and status = 'live' and pg_column_size(p_cmd) < 500;
end $$;

revoke all on function public.hd_coop_open(uuid, text, text) from public;
revoke all on function public.hd_coop_join(uuid, text, text, text, jsonb) from public;
revoke all on function public.hd_coop_poll(uuid, text, text) from public;
revoke all on function public.hd_coop_state(uuid, text, text, jsonb, text, jsonb) from public;
revoke all on function public.hd_coop_cmd(uuid, text, text, jsonb) from public;
grant execute on function public.hd_coop_open(uuid, text, text) to anon, authenticated;
grant execute on function public.hd_coop_join(uuid, text, text, text, jsonb) to anon, authenticated;
grant execute on function public.hd_coop_poll(uuid, text, text) to anon, authenticated;
grant execute on function public.hd_coop_state(uuid, text, text, jsonb, text, jsonb) to anon, authenticated;
grant execute on function public.hd_coop_cmd(uuid, text, text, jsonb) to anon, authenticated;
