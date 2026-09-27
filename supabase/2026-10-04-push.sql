-- Real push notifications (Web Push). The game subscribes the phone and hands the server reminders to send later
-- (streak about to end, daily goals ready). The server also queues its own (tournament ending, a dog sold, a trade
-- offer, a club message, a co-op partner). Every few minutes pg_cron calls the hd-push edge function, which takes
-- what is due through hd_push_take and sends it. VAPID keys and the cron secret live in Vault (not in this file).
create extension if not exists pg_net;
create extension if not exists pg_cron;

create table if not exists public.hd_push_subs(
  endpoint text primary key,
  player_id uuid not null references public.hd_players(id) on delete cascade,
  p256dh text not null, auth text not null,
  created_at timestamptz not null default now(), last_ok timestamptz);
create index if not exists hd_push_subs_player on public.hd_push_subs(player_id);
alter table public.hd_push_subs enable row level security;

create table if not exists public.hd_push_queue(
  id bigint generated always as identity primary key,
  player_id uuid not null references public.hd_players(id) on delete cascade,
  tag text not null, title text not null, body text not null,
  due_at timestamptz not null default now(), sent_at timestamptz);
create index if not exists hd_push_queue_due on public.hd_push_queue(due_at) where sent_at is null;
create unique index if not exists hd_push_queue_tag on public.hd_push_queue(player_id, tag) where sent_at is null;
alter table public.hd_push_queue enable row level security;

create or replace function public.hd_push_subscribe(p_pid uuid, p_sec text, p_sub jsonb)
returns void language plpgsql security definer set search_path = public as $$
declare ep text := p_sub->>'endpoint';
begin
  perform hd_check(p_pid, p_sec);
  if ep is null or ep !~ '^https://' or length(ep) > 1000 then raise exception 'bad subscription'; end if;
  if (select count(*) from hd_push_subs where player_id = p_pid) >= 5 then
    delete from hd_push_subs where endpoint = (select endpoint from hd_push_subs where player_id = p_pid order by created_at limit 1); end if;
  insert into hd_push_subs(endpoint, player_id, p256dh, auth) values (ep, p_pid, p_sub#>>'{keys,p256dh}', p_sub#>>'{keys,auth}')
  on conflict (endpoint) do update set player_id = excluded.player_id, p256dh = excluded.p256dh, auth = excluded.auth;
end $$;

create or replace function public.hd_push_unsubscribe(p_pid uuid, p_sec text, p_endpoint text)
returns void language plpgsql security definer set search_path = public as $$
begin perform hd_check(p_pid, p_sec); delete from hd_push_subs where player_id = p_pid and (p_endpoint is null or endpoint = p_endpoint); end $$;

-- internal: queue one message (a newer one with the same tag replaces an unsent one)
create or replace function public.hd_push_queue_add(p_player uuid, p_tag text, p_title text, p_body text, p_due timestamptz default now())
returns void language plpgsql security definer set search_path = public as $$
begin
  if not exists(select 1 from hd_push_subs where player_id = p_player) then return; end if;
  delete from hd_push_queue where player_id = p_player and tag = p_tag and sent_at is null;
  insert into hd_push_queue(player_id, tag, title, body, due_at) values (p_player, left(p_tag,40), left(p_title,80), left(p_body,200), coalesce(p_due, now()));
end $$;
revoke all on function public.hd_push_queue_add(uuid, text, text, text, timestamptz) from public, anon, authenticated;

-- the game's own reminders: [{tag, title, body, at}] with tags from a fixed list; anything else is ignored
create or replace function public.hd_push_schedule(p_pid uuid, p_sec text, p_items jsonb)
returns integer language plpgsql security definer set search_path = public as $$
declare it jsonb; n integer := 0; t timestamptz;
begin
  perform hd_check(p_pid, p_sec);
  delete from hd_push_queue where player_id = p_pid and sent_at is null and tag like 'r:%';
  for it in select * from jsonb_array_elements(coalesce(p_items,'[]'::jsonb)) loop
    if n >= 6 then exit; end if;
    if (it->>'tag') !~ '^r:[a-z_]{2,20}$' then continue; end if;
    t := (it->>'at')::timestamptz;
    if t is null or t < now() or t > now() + interval '8 days' then continue; end if;
    perform hd_push_queue_add(p_pid, it->>'tag', coalesce(it->>'title','Hogs & Dogs'), coalesce(it->>'body',''), t); n := n + 1;
  end loop;
  return n;
end $$;

-- for the sender only (checked against the cron secret in Vault): due messages with their subscriptions, marked sent
create or replace function public.hd_push_take(p_secret text, p_limit integer default 200)
returns json language plpgsql security definer set search_path = public as $$
declare out json;
begin
  if p_secret is null or p_secret is distinct from (select decrypted_secret from vault.decrypted_secrets where name = 'hd_cron_secret') then raise exception 'no'; end if;
  with due as (update hd_push_queue q set sent_at = now() where q.id in (select id from hd_push_queue where sent_at is null and due_at <= now() order by due_at limit least(coalesce(p_limit,200),500)) returning q.*)
  select json_build_object('vapid', (select decrypted_secret from vault.decrypted_secrets where name = 'hd_vapid_private'),
    'msgs', coalesce(json_agg(json_build_object('title', d.title, 'body', d.body, 'tag', d.tag, 'subs',
      (select coalesce(json_agg(json_build_object('endpoint', s.endpoint, 'keys', json_build_object('p256dh', s.p256dh, 'auth', s.auth))), '[]'::json) from hd_push_subs s where s.player_id = d.player_id)))
    , '[]'::json)) into out from due d;
  delete from hd_push_queue where sent_at < now() - interval '3 days';
  return out;
end $$;

create or replace function public.hd_push_drop(p_secret text, p_endpoints text[], p_ok text[])
returns void language plpgsql security definer set search_path = public as $$
begin
  if p_secret is null or p_secret is distinct from (select decrypted_secret from vault.decrypted_secrets where name = 'hd_cron_secret') then raise exception 'no'; end if;
  delete from hd_push_subs where endpoint = any(coalesce(p_endpoints, '{}'));
  update hd_push_subs set last_ok = now() where endpoint = any(coalesce(p_ok, '{}'));
end $$;

-- the weekly tournament's last evening: remind everyone who has notifications on
create or replace function public.hd_push_tourney_reminder()
returns void language plpgsql security definer set search_path = public as $$
begin
  insert into hd_push_queue(player_id, tag, title, body)
  select distinct s.player_id, 'tourney', 'Tournament ends tonight', 'Last chance this week: get a big hog or a top pup on the board before midnight UTC.'
  from hd_push_subs s where not exists(select 1 from hd_push_queue q where q.player_id = s.player_id and q.tag = 'tourney' and q.sent_at is null);
end $$;
revoke all on function public.hd_push_tourney_reminder() from public, anon, authenticated;

-- a sale or stud fee and a trade offer ping the other player
create or replace function public.hd_push_on_listing() returns trigger language plpgsql security definer set search_path = public as $$
begin
  if (new.status = 'sold' and old.status is distinct from 'sold') or coalesce(new.uses,0) > coalesce(old.uses,0) then
    perform hd_push_queue_add(new.seller, 'sale:'||new.id||':'||coalesce(new.uses,0), case when new.kind = 'stud' then 'Stud fee earned' else 'Sold!' end,
      case when new.kind = 'stud' then new.dog_name||' was used at stud for '||new.price||' dollars.' else new.dog_name||' sold on the market for '||new.price||' dollars.' end);
  end if; return new;
end $$;
drop trigger if exists hd_push_listing on public.hd_listings;
create trigger hd_push_listing after update on public.hd_listings for each row execute function public.hd_push_on_listing();

create or replace function public.hd_push_on_trade() returns trigger language plpgsql security definer set search_path = public as $$
begin perform hd_push_queue_add(new.to_user, 'trade:'||new.id, 'Trade offer', coalesce(new.from_ranch,'A ranch')||' made you an offer.'); return new; end $$;
drop trigger if exists hd_push_trade on public.hd_trades;
create trigger hd_push_trade after insert on public.hd_trades for each row execute function public.hd_push_on_trade();

revoke all on function public.hd_push_subscribe(uuid, text, jsonb) from public;
revoke all on function public.hd_push_unsubscribe(uuid, text, text) from public;
revoke all on function public.hd_push_schedule(uuid, text, jsonb) from public;
revoke all on function public.hd_push_take(text, integer) from public, anon, authenticated;
revoke all on function public.hd_push_drop(text, text[], text[]) from public, anon, authenticated;
grant execute on function public.hd_push_subscribe(uuid, text, jsonb) to anon, authenticated;
grant execute on function public.hd_push_unsubscribe(uuid, text, text) to anon, authenticated;
grant execute on function public.hd_push_schedule(uuid, text, jsonb) to anon, authenticated;
grant execute on function public.hd_push_take(text, integer) to service_role;
grant execute on function public.hd_push_drop(text, text[], text[]) to service_role;
