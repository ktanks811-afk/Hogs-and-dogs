-- ===== Hunting Club hub: social feed, studs, breeding contracts, profiles, notifications, messages, moderation =====
-- Everything goes through SECURITY DEFINER functions that check the player's secret (hd_check), like the rest of the game.

alter table public.hd_listings add column if not exists info jsonb not null default '{}'::jsonb;

create table if not exists public.hd_hub_posts (
  id bigint generated always as identity primary key, player_id uuid not null, ranch text not null, club text,
  kind text not null check (kind in ('hunt','litter','stud','alpha','request','showcase','trophy','announce')),
  title text not null, body text not null default '', data jsonb not null default '{}'::jsonb,
  likes integer not null default 0, comments integer not null default 0, shares integer not null default 0,
  reports integer not null default 0, hidden boolean not null default false, created_at timestamptz not null default now());
create index if not exists hd_hub_posts_time on public.hd_hub_posts(created_at desc);
create index if not exists hd_hub_posts_player on public.hd_hub_posts(player_id, created_at desc);
create table if not exists public.hd_hub_likes (post_id bigint not null, player_id uuid not null, created_at timestamptz not null default now(), primary key(post_id, player_id));
create table if not exists public.hd_hub_shares (post_id bigint not null, player_id uuid not null, created_at timestamptz not null default now(), primary key(post_id, player_id));
create table if not exists public.hd_hub_comments (id bigint generated always as identity primary key, post_id bigint not null, player_id uuid not null, ranch text not null,
  parent_id bigint, body text not null, hidden boolean not null default false, created_at timestamptz not null default now());
create index if not exists hd_hub_comments_post on public.hd_hub_comments(post_id, id);
create table if not exists public.hd_hub_saves (player_id uuid not null, kind text not null check (kind in ('post','stud','dog')), ref text not null, data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(), primary key(player_id, kind, ref));
create table if not exists public.hd_hub_follows (player_id uuid not null, kind text not null check (kind in ('player','club')), target text not null, created_at timestamptz not null default now(), primary key(player_id, kind, target));
create table if not exists public.hd_hub_blocks (player_id uuid not null, target uuid not null, kind text not null check (kind in ('block','mute')), created_at timestamptz not null default now(), primary key(player_id, target, kind));
create table if not exists public.hd_hub_reports (id bigint generated always as identity primary key, reporter uuid not null, post_id bigint, comment_id bigint, target uuid, reason text not null, created_at timestamptz not null default now());
create unique index if not exists hd_hub_reports_once on public.hd_hub_reports(reporter, coalesce(post_id,0), coalesce(comment_id,0), coalesce(target,'00000000-0000-0000-0000-000000000000'::uuid));
create table if not exists public.hd_hub_notifs (id bigint generated always as identity primary key, player_id uuid not null, kind text not null, actor uuid, actor_ranch text,
  post_id bigint, req_id bigint, txt text not null, read boolean not null default false, created_at timestamptz not null default now());
create index if not exists hd_hub_notifs_player on public.hd_hub_notifs(player_id, id desc);
create table if not exists public.hd_hub_msgs (id bigint generated always as identity primary key, from_id uuid not null, to_id uuid not null, from_ranch text not null, body text not null,
  read boolean not null default false, created_at timestamptz not null default now());
create index if not exists hd_hub_msgs_pair on public.hd_hub_msgs(to_id, from_id, id desc);
create table if not exists public.hd_hub_profiles (player_id uuid primary key, ranch text not null, club text, bio text, avatar jsonb, stats jsonb not null default '{}'::jsonb,
  alpha jsonb not null default '[]'::jsonb, game_rep integer not null default 0, updated_at timestamptz not null default now());
create table if not exists public.hd_hub_breeds (id bigint generated always as identity primary key, listing_id bigint, post_id bigint,
  sire_owner uuid not null, sire_ranch text not null, dam_owner uuid not null, dam_ranch text not null, initiator uuid not null, turn uuid,
  sire jsonb not null, dam jsonb not null, fee integer not null default 0 check (fee >= 0 and fee <= 1000000),
  status text not null default 'pending' check (status in ('pending','countered','agreed','confirmed','bred','born','declined','cancelled')),
  sire_ok boolean not null default false, dam_ok boolean not null default false, msg text, litter jsonb,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now());
create index if not exists hd_hub_breeds_sire on public.hd_hub_breeds(sire_owner, updated_at desc);
create index if not exists hd_hub_breeds_dam on public.hd_hub_breeds(dam_owner, updated_at desc);
alter table public.hd_hub_posts enable row level security; alter table public.hd_hub_likes enable row level security; alter table public.hd_hub_shares enable row level security;
alter table public.hd_hub_comments enable row level security; alter table public.hd_hub_saves enable row level security; alter table public.hd_hub_follows enable row level security;
alter table public.hd_hub_blocks enable row level security; alter table public.hd_hub_reports enable row level security; alter table public.hd_hub_notifs enable row level security;
alter table public.hd_hub_msgs enable row level security; alter table public.hd_hub_profiles enable row level security; alter table public.hd_hub_breeds enable row level security;

-- ---------- helpers (not callable from the browser) ----------
-- basic word filter for posts, comments, messages and names; raises a friendly error
create or replace function public.hd_hub_clean(t text, maxlen integer) returns text language plpgsql immutable set search_path to 'public' as $$
declare s text := left(regexp_replace(trim(coalesce(t,'')), '\s+', ' ', 'g'), maxlen);
begin
  if s ~* '(fuck|cunt|nigg|f[a@]gg?[o0]t|\mfag\M|retard|\mwhore|\mslut|\mrape|\mkike\M|\mspic\M|\mchink|cocksuck|motherf|\mtwat\M)' then
    raise exception 'Keep it clean: that has a word the Hunting Club does not allow.';
  end if;
  if s ~ '(.)\1{11,}' then raise exception 'That looks like spam.'; end if;
  return s;
end $$;
create or replace function public.hd_hub_ranch(p_pid uuid) returns text language sql stable security definer set search_path to 'public' as $$
  select coalesce((select ranch from hd_hub_profiles where player_id = p_pid), (select name from hd_ranches where player_id = p_pid), 'A ranch') $$;
create or replace function public.hd_hub_blocked(a uuid, b uuid) returns boolean language sql stable security definer set search_path to 'public' as $$
  select exists(select 1 from hd_hub_blocks where kind = 'block' and ((player_id = a and target = b) or (player_id = b and target = a))) $$;
create or replace function public.hd_hub_notify(p_to uuid, p_kind text, p_actor uuid, p_txt text, p_post bigint default null, p_req bigint default null) returns void
language plpgsql security definer set search_path to 'public' as $$
begin
  if p_to is null or p_to = p_actor then return; end if;
  if p_actor is not null and exists(select 1 from hd_hub_blocks where player_id = p_to and target = p_actor) then return; end if;
  insert into hd_hub_notifs(player_id, kind, actor, actor_ranch, post_id, req_id, txt) values (p_to, p_kind, p_actor, hd_hub_ranch(p_actor), p_post, p_req, left(p_txt, 200));
  delete from hd_hub_notifs where player_id = p_to and id < (select min(id) from (select id from hd_hub_notifs where player_id = p_to order by id desc limit 200) k);
  perform hd_push_queue_add(p_to, 'hub:'||p_kind, 'Hunting Club', left(p_txt, 160));
end $$;
revoke execute on function public.hd_hub_clean(text, integer) from public, anon;
revoke execute on function public.hd_hub_notify(uuid, text, uuid, text, bigint, bigint) from public, anon;
revoke execute on function public.hd_hub_blocked(uuid, uuid) from public, anon;

-- a post as the reader sees it
create or replace function public.hd_hub_post_json(p hd_hub_posts, me uuid) returns jsonb language sql stable security definer set search_path to 'public' as $$
  select jsonb_build_object('id', p.id, 'player_id', p.player_id, 'ranch', p.ranch, 'club', p.club, 'kind', p.kind, 'title', p.title, 'body', p.body, 'data', p.data,
    'likes', p.likes, 'comments', p.comments, 'shares', p.shares, 'at', p.created_at,
    'liked', exists(select 1 from hd_hub_likes l where l.post_id = p.id and l.player_id = me),
    'saved', exists(select 1 from hd_hub_saves s where s.player_id = me and s.kind = 'post' and s.ref = p.id::text),
    'avatar', (select avatar from hd_hub_profiles f where f.player_id = p.player_id)) $$;
revoke execute on function public.hd_hub_post_json(hd_hub_posts, uuid) from public, anon;

-- ---------- posts ----------
create or replace function public.hd_hub_post(p_pid uuid, p_sec text, p_kind text, p_title text, p_body text, p_data jsonb, p_ranch text, p_club text default null) returns bigint
language plpgsql security definer set search_path to 'public' as $$
declare t text; b text; r text; pid bigint; f record; who text;
begin
  perform hd_check(p_pid, p_sec);
  if p_kind not in ('hunt','litter','stud','alpha','request','showcase','trophy','announce') then raise exception 'Unknown post type.'; end if;
  t := hd_hub_clean(p_title, 80); b := hd_hub_clean(p_body, 1000); r := hd_hub_clean(coalesce(nullif(trim(p_ranch),''),'A ranch'), 40);
  if length(t) < 2 then raise exception 'Give your post a title.'; end if;
  if pg_column_size(p_data) > 300000 then raise exception 'That post is too big.'; end if;
  if p_kind = 'announce' and not exists(select 1 from hd_groups where owner = p_pid) then raise exception 'Only a club leader can post a club announcement.'; end if;
  if exists(select 1 from hd_hub_posts where player_id = p_pid and created_at > now() - interval '8 seconds') then raise exception 'Slow down: one post every 8 seconds.'; end if;
  if (select count(*) from hd_hub_posts where player_id = p_pid and created_at > now() - interval '1 day') >= 30 then raise exception 'That is enough posts for today.'; end if;
  if exists(select 1 from hd_hub_posts where player_id = p_pid and title = t and body = b and created_at > now() - interval '10 minutes') then raise exception 'You just posted that.'; end if;
  insert into hd_hub_posts(player_id, ranch, club, kind, title, body, data) values (p_pid, r, nullif(hd_hub_clean(p_club, 40),''), p_kind, t, b, coalesce(p_data, '{}'::jsonb)) returning id into pid;
  -- followers hear about new litters and studs
  if p_kind in ('litter','stud') then
    who := case p_kind when 'litter' then r||' has a new litter: '||t else r||' has a stud available: '||t end;
    for f in select player_id from hd_hub_follows where kind = 'player' and target = p_pid::text limit 500 loop
      perform hd_hub_notify(f.player_id, case p_kind when 'litter' then 'litter' else 'stud_new' end, p_pid, who, pid);
    end loop;
  end if;
  return pid;
end $$;

create or replace function public.hd_hub_delete_post(p_pid uuid, p_sec text, p_id bigint) returns void language plpgsql security definer set search_path to 'public' as $$
begin
  perform hd_check(p_pid, p_sec);
  delete from hd_hub_posts where id = p_id and player_id = p_pid;
  delete from hd_hub_comments where post_id = p_id; delete from hd_hub_likes where post_id = p_id;
end $$;

-- the feed: newest first, hiding reported-away posts and anyone you blocked or muted
create or replace function public.hd_hub_feed(p_pid uuid, p_sec text, p_mode text default 'all', p_kind text default null, p_author uuid default null, p_before bigint default null, p_limit integer default 30) returns jsonb
language plpgsql security definer set search_path to 'public' as $$
begin
  perform hd_check(p_pid, p_sec);
  return coalesce((select jsonb_agg(hd_hub_post_json(p::hd_hub_posts, p_pid) order by p.id desc) from (
    select * from hd_hub_posts p where not p.hidden
      and (p_kind is null or p.kind = p_kind or (p_kind = 'hunt' and p.kind = 'trophy'))
      and (p_author is null or p.player_id = p_author)
      and (p_before is null or p.id < p_before)
      and not exists(select 1 from hd_hub_blocks k where k.player_id = p_pid and k.target = p.player_id)
      and not exists(select 1 from hd_hub_blocks k where k.kind = 'block' and k.player_id = p.player_id and k.target = p_pid)
      and (p_mode <> 'following' or p.player_id = p_pid
           or exists(select 1 from hd_hub_follows w where w.player_id = p_pid and w.kind = 'player' and w.target = p.player_id::text)
           or exists(select 1 from hd_hub_follows w join hd_groups g on w.kind = 'club' and w.target = g.id::text join hd_group_members m on m.group_id = g.id where w.player_id = p_pid and m.player_id = p.player_id))
      and (p_mode <> 'saved' or exists(select 1 from hd_hub_saves s where s.player_id = p_pid and s.kind = 'post' and s.ref = p.id::text))
    order by p.id desc limit least(greatest(coalesce(p_limit,30),1),60)) p), '[]'::jsonb);
end $$;

create or replace function public.hd_hub_get_post(p_pid uuid, p_sec text, p_id bigint) returns jsonb language plpgsql security definer set search_path to 'public' as $$
declare p hd_hub_posts;
begin
  perform hd_check(p_pid, p_sec);
  select * into p from hd_hub_posts where id = p_id and not hidden;
  if not found or hd_hub_blocked(p_pid, p.player_id) then raise exception 'That post is gone.'; end if;
  return hd_hub_post_json(p, p_pid);
end $$;

create or replace function public.hd_hub_like(p_pid uuid, p_sec text, p_post bigint, p_on boolean) returns integer language plpgsql security definer set search_path to 'public' as $$
declare p hd_hub_posts; n integer;
begin
  perform hd_check(p_pid, p_sec);
  select * into p from hd_hub_posts where id = p_post;
  if not found then raise exception 'That post is gone.'; end if;
  if p_on then
    insert into hd_hub_likes(post_id, player_id) values (p_post, p_pid) on conflict do nothing;
    get diagnostics n = row_count;
    if n > 0 then perform hd_hub_notify(p.player_id, 'like', p_pid, hd_hub_ranch(p_pid)||' liked your post "'||p.title||'"', p_post); end if;
  else delete from hd_hub_likes where post_id = p_post and player_id = p_pid; end if;
  update hd_hub_posts set likes = (select count(*) from hd_hub_likes where post_id = p_post) where id = p_post returning likes into n;
  return n;
end $$;

create or replace function public.hd_hub_share(p_pid uuid, p_sec text, p_post bigint) returns integer language plpgsql security definer set search_path to 'public' as $$
declare n integer;
begin
  perform hd_check(p_pid, p_sec);
  insert into hd_hub_shares(post_id, player_id) values (p_post, p_pid) on conflict do nothing;
  update hd_hub_posts set shares = (select count(*) from hd_hub_shares where post_id = p_post) where id = p_post returning shares into n;
  return coalesce(n, 0);
end $$;

-- ---------- comments and replies ----------
create or replace function public.hd_hub_comment(p_pid uuid, p_sec text, p_post bigint, p_parent bigint, p_body text, p_ranch text) returns bigint
language plpgsql security definer set search_path to 'public' as $$
declare p hd_hub_posts; c hd_hub_comments; b text; cid bigint; r text;
begin
  perform hd_check(p_pid, p_sec);
  select * into p from hd_hub_posts where id = p_post and not hidden;
  if not found then raise exception 'That post is gone.'; end if;
  if hd_hub_blocked(p_pid, p.player_id) then raise exception 'You cannot comment on that post.'; end if;
  b := hd_hub_clean(p_body, 500); r := hd_hub_clean(coalesce(nullif(trim(p_ranch),''), hd_hub_ranch(p_pid)), 40);
  if length(b) < 1 then raise exception 'Write something first.'; end if;
  if exists(select 1 from hd_hub_comments where player_id = p_pid and created_at > now() - interval '3 seconds') then raise exception 'Slow down a little.'; end if;
  if (select count(*) from hd_hub_comments where player_id = p_pid and created_at > now() - interval '1 day') >= 200 then raise exception 'That is enough comments for today.'; end if;
  if p_parent is not null then select * into c from hd_hub_comments where id = p_parent and post_id = p_post; if not found then raise exception 'That comment is gone.'; end if; end if;
  insert into hd_hub_comments(post_id, player_id, ranch, parent_id, body) values (p_post, p_pid, r, p_parent, b) returning id into cid;
  update hd_hub_posts set comments = (select count(*) from hd_hub_comments where post_id = p_post and not hidden) where id = p_post;
  perform hd_hub_notify(p.player_id, 'comment', p_pid, r||' commented on "'||p.title||'": '||left(b, 80), p_post);
  if p_parent is not null and c.player_id <> p.player_id then perform hd_hub_notify(c.player_id, 'reply', p_pid, r||' replied to you: '||left(b, 80), p_post); end if;
  return cid;
end $$;

create or replace function public.hd_hub_comments(p_pid uuid, p_sec text, p_post bigint) returns jsonb language plpgsql security definer set search_path to 'public' as $$
begin
  perform hd_check(p_pid, p_sec);
  return coalesce((select jsonb_agg(jsonb_build_object('id', c.id, 'player_id', c.player_id, 'ranch', c.ranch, 'parent_id', c.parent_id, 'body', c.body, 'at', c.created_at) order by c.id)
    from hd_hub_comments c where c.post_id = p_post and not c.hidden and not exists(select 1 from hd_hub_blocks k where k.player_id = p_pid and k.target = c.player_id)), '[]'::jsonb);
end $$;

-- ---------- saves, follows, blocks, reports ----------
create or replace function public.hd_hub_save(p_pid uuid, p_sec text, p_kind text, p_ref text, p_data jsonb, p_on boolean) returns void language plpgsql security definer set search_path to 'public' as $$
begin
  perform hd_check(p_pid, p_sec);
  if p_on then
    if (select count(*) from hd_hub_saves where player_id = p_pid) >= 300 then raise exception 'Your saved list is full.'; end if;
    if pg_column_size(p_data) > 80000 then raise exception 'too large'; end if;
    insert into hd_hub_saves(player_id, kind, ref, data) values (p_pid, p_kind, left(p_ref, 80), coalesce(p_data, '{}'::jsonb)) on conflict (player_id, kind, ref) do update set data = excluded.data;
  else delete from hd_hub_saves where player_id = p_pid and kind = p_kind and ref = p_ref; end if;
end $$;
create or replace function public.hd_hub_saved(p_pid uuid, p_sec text) returns jsonb language plpgsql security definer set search_path to 'public' as $$
begin
  perform hd_check(p_pid, p_sec);
  return coalesce((select jsonb_agg(jsonb_build_object('kind', kind, 'ref', ref, 'data', data, 'at', created_at) order by created_at desc) from hd_hub_saves where player_id = p_pid), '[]'::jsonb);
end $$;

create or replace function public.hd_hub_follow(p_pid uuid, p_sec text, p_kind text, p_target text, p_on boolean) returns void language plpgsql security definer set search_path to 'public' as $$
declare n integer;
begin
  perform hd_check(p_pid, p_sec);
  if p_kind = 'player' and p_target = p_pid::text then raise exception 'You cannot follow yourself.'; end if;
  if p_on then
    if (select count(*) from hd_hub_follows where player_id = p_pid) >= 500 then raise exception 'You follow a lot already.'; end if;
    insert into hd_hub_follows(player_id, kind, target) values (p_pid, p_kind, p_target) on conflict do nothing;
    get diagnostics n = row_count;
    if n > 0 and p_kind = 'player' then perform hd_hub_notify(p_target::uuid, 'follow', p_pid, hd_hub_ranch(p_pid)||' started following you.'); end if;
  else delete from hd_hub_follows where player_id = p_pid and kind = p_kind and target = p_target; end if;
end $$;

create or replace function public.hd_hub_block(p_pid uuid, p_sec text, p_target uuid, p_kind text, p_on boolean) returns void language plpgsql security definer set search_path to 'public' as $$
begin
  perform hd_check(p_pid, p_sec);
  if p_target = p_pid then raise exception 'That is you.'; end if;
  if p_on then insert into hd_hub_blocks(player_id, target, kind) values (p_pid, p_target, p_kind) on conflict do nothing;
    if p_kind = 'block' then delete from hd_hub_follows where (player_id = p_pid and kind = 'player' and target = p_target::text) or (player_id = p_target and kind = 'player' and target = p_pid::text); end if;
  else delete from hd_hub_blocks where player_id = p_pid and target = p_target and kind = p_kind; end if;
end $$;

-- three reports from different players hide a post or comment until someone looks at it
create or replace function public.hd_hub_report(p_pid uuid, p_sec text, p_post bigint, p_comment bigint, p_target uuid, p_reason text) returns void language plpgsql security definer set search_path to 'public' as $$
declare n integer;
begin
  perform hd_check(p_pid, p_sec);
  if (select count(*) from hd_hub_reports where reporter = p_pid and created_at > now() - interval '1 day') >= 30 then raise exception 'That is a lot of reports today.'; end if;
  insert into hd_hub_reports(reporter, post_id, comment_id, target, reason) values (p_pid, p_post, p_comment, p_target, left(coalesce(nullif(trim(p_reason),''),'Reported'), 200)) on conflict do nothing;
  if p_post is not null then
    select count(distinct reporter) into n from hd_hub_reports where post_id = p_post and comment_id is null;
    update hd_hub_posts set reports = n, hidden = (n >= 3) where id = p_post;
  end if;
  if p_comment is not null then
    select count(distinct reporter) into n from hd_hub_reports where comment_id = p_comment;
    if n >= 3 then update hd_hub_comments set hidden = true where id = p_comment; end if;
  end if;
end $$;

-- ---------- notifications and messages ----------
create or replace function public.hd_hub_notifs(p_pid uuid, p_sec text) returns jsonb language plpgsql security definer set search_path to 'public' as $$
begin
  perform hd_check(p_pid, p_sec);
  return jsonb_build_object('unread', (select count(*) from hd_hub_notifs where player_id = p_pid and not read),
    'msgs', (select count(*) from hd_hub_msgs where to_id = p_pid and not read),
    'list', coalesce((select jsonb_agg(jsonb_build_object('id', id, 'kind', kind, 'actor', actor, 'actor_ranch', actor_ranch, 'post_id', post_id, 'req_id', req_id, 'txt', txt, 'read', read, 'at', created_at) order by id desc)
      from (select * from hd_hub_notifs where player_id = p_pid order by id desc limit 60) x), '[]'::jsonb));
end $$;
create or replace function public.hd_hub_notifs_read(p_pid uuid, p_sec text) returns void language plpgsql security definer set search_path to 'public' as $$
begin perform hd_check(p_pid, p_sec); update hd_hub_notifs set read = true where player_id = p_pid and not read; end $$;

create or replace function public.hd_hub_msg_send(p_pid uuid, p_sec text, p_to uuid, p_body text, p_ranch text) returns bigint language plpgsql security definer set search_path to 'public' as $$
declare b text; mid bigint; r text;
begin
  perform hd_check(p_pid, p_sec);
  if p_to = p_pid then raise exception 'That is you.'; end if;
  if not exists(select 1 from hd_players where id = p_to) then raise exception 'That player was not found.'; end if;
  if hd_hub_blocked(p_pid, p_to) or exists(select 1 from hd_hub_blocks where player_id = p_to and target = p_pid) then raise exception 'You cannot message that player.'; end if;
  b := hd_hub_clean(p_body, 500); r := hd_hub_clean(coalesce(nullif(trim(p_ranch),''), hd_hub_ranch(p_pid)), 40);
  if length(b) < 1 then raise exception 'Write something first.'; end if;
  if exists(select 1 from hd_hub_msgs where from_id = p_pid and created_at > now() - interval '2 seconds') then raise exception 'Slow down a little.'; end if;
  if (select count(*) from hd_hub_msgs where from_id = p_pid and created_at > now() - interval '1 day') >= 300 then raise exception 'That is enough messages for today.'; end if;
  insert into hd_hub_msgs(from_id, to_id, from_ranch, body) values (p_pid, p_to, r, b) returning id into mid;
  perform hd_push_queue_add(p_to, 'hubmsg', 'Message from '||r, left(b, 140));
  return mid;
end $$;
create or replace function public.hd_hub_msgs(p_pid uuid, p_sec text, p_with uuid) returns jsonb language plpgsql security definer set search_path to 'public' as $$
begin
  perform hd_check(p_pid, p_sec);
  if p_with is null then
    return coalesce((select jsonb_agg(x order by x->>'at' desc) from (
      select distinct on (other) jsonb_build_object('with', other, 'ranch', hd_hub_ranch(other), 'body', body, 'at', created_at,
        'unread', (select count(*) from hd_hub_msgs u where u.to_id = p_pid and u.from_id = other and not u.read)) x
      from (select case when from_id = p_pid then to_id else from_id end other, body, created_at, id from hd_hub_msgs where from_id = p_pid or to_id = p_pid) m
      order by other, id desc) y), '[]'::jsonb);
  end if;
  update hd_hub_msgs set read = true where to_id = p_pid and from_id = p_with and not read;
  return coalesce((select jsonb_agg(jsonb_build_object('id', id, 'mine', from_id = p_pid, 'ranch', from_ranch, 'body', body, 'at', created_at) order by id)
    from (select * from hd_hub_msgs where (from_id = p_pid and to_id = p_with) or (from_id = p_with and to_id = p_pid) order by id desc limit 100) z), '[]'::jsonb);
end $$;

-- ---------- profiles and reputation ----------
-- game reputation comes from the player's real record (hunts, rare dogs, bloodlines, litters, achievements) and is capped;
-- the social part is earned here: finished breeding partnerships and likes from other players. Nothing buys it.
create or replace function public.hd_hub_profile_save(p_pid uuid, p_sec text, p_ranch text, p_club text, p_bio text, p_avatar jsonb, p_stats jsonb, p_alpha jsonb, p_game_rep integer) returns void
language plpgsql security definer set search_path to 'public' as $$
begin
  perform hd_check(p_pid, p_sec);
  if pg_column_size(p_avatar) + pg_column_size(p_alpha) + pg_column_size(p_stats) > 250000 then raise exception 'Profile too large.'; end if;
  if p_alpha is not null and jsonb_typeof(p_alpha) = 'array' and exists(select 1 from jsonb_array_elements(p_alpha) a where not hd_dog_ok(a)) then raise exception 'An Alpha Dog has invalid stats.'; end if;
  insert into hd_hub_profiles(player_id, ranch, club, bio, avatar, stats, alpha, game_rep, updated_at)
  values (p_pid, hd_hub_clean(coalesce(nullif(trim(p_ranch),''),'A ranch'), 40), hd_hub_clean(p_club, 40), hd_hub_clean(p_bio, 200), p_avatar, coalesce(p_stats,'{}'::jsonb), coalesce(p_alpha,'[]'::jsonb), least(greatest(coalesce(p_game_rep,0),0),5000), now())
  on conflict (player_id) do update set ranch = excluded.ranch, club = excluded.club, bio = excluded.bio, avatar = excluded.avatar, stats = excluded.stats, alpha = excluded.alpha, game_rep = excluded.game_rep, updated_at = now();
end $$;
create or replace function public.hd_hub_rep(p uuid) returns integer language sql stable security definer set search_path to 'public' as $$
  select coalesce((select game_rep from hd_hub_profiles where player_id = p), 0)
    + 60 * (select count(*) from hd_hub_breeds where status = 'born' and (sire_owner = p or dam_owner = p))::integer
    + least(800, (select coalesce(sum(likes),0) from hd_hub_posts where player_id = p and not hidden)::integer * 2)
    + least(300, (select count(*) from hd_hub_follows where kind = 'player' and target = p::text)::integer * 3) $$;
revoke execute on function public.hd_hub_rep(uuid) from public, anon;
create or replace function public.hd_hub_profile_get(p_pid uuid, p_sec text, p_target uuid) returns jsonb language plpgsql security definer set search_path to 'public' as $$
declare f hd_hub_profiles; rn hd_ranches;
begin
  perform hd_check(p_pid, p_sec);
  select * into f from hd_hub_profiles where player_id = p_target; select * into rn from hd_ranches where player_id = p_target;
  if f.player_id is null and rn.player_id is null then raise exception 'That player has no Hunting Club profile yet.'; end if;
  return jsonb_build_object('player_id', p_target, 'ranch', coalesce(f.ranch, rn.name, 'A ranch'), 'club', f.club, 'bio', f.bio, 'avatar', f.avatar, 'stats', coalesce(f.stats,'{}'::jsonb), 'alpha', coalesce(f.alpha,'[]'::jsonb),
    'rep', hd_hub_rep(p_target), 'level', rn.level, 'hogs', rn.hogs, 'dog_count', rn.dog_count, 'best_line', rn.best_line, 'dogs', coalesce(rn.snapshot,'[]'::jsonb),
    'clubs', coalesce((select jsonb_agg(jsonb_build_object('id', g.id, 'name', g.name)) from hd_groups g join hd_group_members m on m.group_id = g.id where m.player_id = p_target), '[]'::jsonb),
    'followers', (select count(*) from hd_hub_follows where kind = 'player' and target = p_target::text), 'following', (select count(*) from hd_hub_follows where player_id = p_target),
    'i_follow', exists(select 1 from hd_hub_follows where player_id = p_pid and kind = 'player' and target = p_target::text),
    'blocked', exists(select 1 from hd_hub_blocks where player_id = p_pid and target = p_target and kind = 'block'),
    'muted', exists(select 1 from hd_hub_blocks where player_id = p_pid and target = p_target and kind = 'mute'),
    'posts', (select count(*) from hd_hub_posts where player_id = p_target and not hidden),
    'studs', coalesce((select jsonb_agg(jsonb_build_object('id', id, 'price', price, 'dog', dog, 'info', info, 'uses', uses)) from hd_listings where seller = p_target and kind = 'stud' and status = 'open' and animal = 'dog'), '[]'::jsonb),
    'litters', coalesce((select jsonb_agg(jsonb_build_object('id', id, 'sire', sire->>'name', 'dam', dam->>'name', 'litter', litter, 'at', updated_at) order by id desc) from hd_hub_breeds where status = 'born' and (sire_owner = p_target or dam_owner = p_target)), '[]'::jsonb),
    'partners', (select count(*) from hd_hub_breeds where status = 'born' and (sire_owner = p_target or dam_owner = p_target)));
end $$;

-- ---------- studs (the online market's stud listings, with Hunting Club details) ----------
-- the dog stays in its owner's kennel; other players buy a breeding, not the dog
create or replace function public.hd_hub_list_stud(p_pid uuid, p_sec text, p_dog jsonb, p_price integer, p_ranch text, p_info jsonb) returns bigint language plpgsql security definer set search_path to 'public' as $$
declare lid bigint; v_info jsonb;
begin
  perform hd_check(p_pid, p_sec);
  if p_dog->>'sex' <> 'M' then raise exception 'Only males can stand at stud.'; end if;
  if exists(select 1 from hd_listings where seller = p_pid and kind = 'stud' and status = 'open' and dog->>'id' = p_dog->>'id') then raise exception 'That dog is already listed at stud.'; end if;
  v_info := jsonb_build_object('avail', case when p_info->>'avail' in ('open','paused') then p_info->>'avail' else 'open' end,
    'slots', least(greatest(coalesce((p_info->>'slots')::int, 3), 1), 10),
    'req', hd_hub_clean(p_info->>'req', 200), 'loc', hd_hub_clean(p_info->>'loc', 60), 'desc', hd_hub_clean(p_info->>'desc', 500));
  lid := hd_list_dog(p_pid, p_sec, 'stud', p_dog, p_price, hd_hub_clean(p_ranch, 40));
  update hd_listings set info = v_info where id = lid;
  return lid;
end $$;
create or replace function public.hd_hub_stud_update(p_pid uuid, p_sec text, p_id bigint, p_price integer, p_info jsonb) returns void language plpgsql security definer set search_path to 'public' as $$
declare was text;
begin
  perform hd_check(p_pid, p_sec);
  select info->>'avail' into was from hd_listings where id = p_id and seller = p_pid and kind = 'stud' and status = 'open';
  if not found then raise exception 'That stud listing is not open.'; end if;
  if p_price is null or p_price < 1 or p_price > 1000000 then raise exception 'Prices must be between $1 and $1,000,000.'; end if;
  update hd_listings set price = p_price, info = jsonb_build_object('avail', case when p_info->>'avail' in ('open','paused') then p_info->>'avail' else 'open' end,
    'slots', least(greatest(coalesce((p_info->>'slots')::int, 3), 1), 10), 'req', hd_hub_clean(p_info->>'req', 200), 'loc', hd_hub_clean(p_info->>'loc', 60), 'desc', hd_hub_clean(p_info->>'desc', 500)) where id = p_id;
end $$;
create or replace function public.hd_hub_studs(p_pid uuid, p_sec text) returns jsonb language plpgsql security definer set search_path to 'public' as $$
begin
  perform hd_check(p_pid, p_sec);
  return coalesce((select jsonb_agg(jsonb_build_object('id', l.id, 'seller', l.seller, 'ranch', l.seller_ranch, 'price', l.price, 'dog', l.dog, 'info', l.info, 'uses', l.uses, 'at', l.created_at,
      'active', (select count(*) from hd_hub_breeds b where b.listing_id = l.id and b.status in ('pending','countered','agreed','confirmed')),
      'saved', exists(select 1 from hd_hub_saves s where s.player_id = p_pid and s.kind = 'stud' and s.ref = l.id::text)) order by l.id desc)
    from hd_listings l where l.kind = 'stud' and l.status = 'open' and l.animal = 'dog' and not exists(select 1 from hd_hub_blocks k where k.player_id = p_pid and k.target = l.seller and k.kind = 'block')), '[]'::jsonb);
end $$;

-- ---------- breeding requests and contracts ----------
-- p_role: 'dam' = I own the female and want their stud; 'sire' = I own the stud and offer him to their female
create or replace function public.hd_hub_breed_request(p_pid uuid, p_sec text, p_role text, p_to uuid, p_listing bigint, p_post bigint, p_sire jsonb, p_dam jsonb, p_fee integer, p_msg text, p_ranch text) returns bigint
language plpgsql security definer set search_path to 'public' as $$
declare l hd_listings; so uuid; dow uuid; fee integer := p_fee; rid bigint; r text; other text; act integer;
begin
  perform hd_check(p_pid, p_sec);
  if p_role not in ('dam','sire') then raise exception 'bad role'; end if;
  if not hd_dog_ok(p_sire) or not hd_dog_ok(p_dam) then raise exception 'One of those dogs has invalid stats.'; end if;
  if p_sire->>'sex' <> 'M' or p_dam->>'sex' <> 'F' then raise exception 'A breeding needs a male and a female.'; end if;
  if pg_column_size(p_sire) + pg_column_size(p_dam) > 140000 then raise exception 'dogs too large'; end if;
  r := hd_hub_clean(coalesce(nullif(trim(p_ranch),''), hd_hub_ranch(p_pid)), 40);
  if p_listing is not null then
    select * into l from hd_listings where id = p_listing and kind = 'stud' and status = 'open';
    if not found then raise exception 'That stud is no longer listed.'; end if;
    if coalesce(l.info->>'avail','open') <> 'open' then raise exception 'That stud is not taking bookings right now.'; end if;
    select count(*) into act from hd_hub_breeds where listing_id = l.id and status in ('pending','countered','agreed','confirmed');
    if act >= coalesce((l.info->>'slots')::int, 3) then raise exception 'That stud is fully booked right now. Try again later.'; end if;
    p_to := l.seller; p_sire := l.dog; if fee is null then fee := l.price; end if;
  end if;
  if p_to is null or p_to = p_pid then raise exception 'Pick another player''s dog.'; end if;
  if hd_hub_blocked(p_pid, p_to) or exists(select 1 from hd_hub_blocks where player_id = p_to and target = p_pid and kind = 'block') then raise exception 'You cannot send that player a request.'; end if;
  if (select count(*) from hd_hub_breeds where initiator = p_pid and status in ('pending','countered')) >= 15 then raise exception 'You have a lot of open requests. Wait for some answers first.'; end if;
  if exists(select 1 from hd_hub_breeds where initiator = p_pid and status in ('pending','countered','agreed','confirmed') and sire->>'id' = p_sire->>'id' and dam->>'id' = p_dam->>'id') then raise exception 'You already have a request open for that pair.'; end if;
  if fee is null or fee < 0 or fee > 1000000 then raise exception 'Fees run from $0 to $1,000,000.'; end if;
  if p_role = 'dam' then so := p_to; dow := p_pid; else so := p_pid; dow := p_to; end if;
  other := hd_hub_ranch(p_to);
  insert into hd_hub_breeds(listing_id, post_id, sire_owner, sire_ranch, dam_owner, dam_ranch, initiator, turn, sire, dam, fee, msg)
  values (p_listing, p_post, so, case when so = p_pid then r else other end, dow, case when dow = p_pid then r else other end, p_pid, p_to, p_sire, p_dam, fee, hd_hub_clean(p_msg, 300)) returning id into rid;
  if p_role = 'dam' then perform hd_hub_notify(p_to, 'req_stud', p_pid, r||' wants to breed '||coalesce(p_dam->>'name','a female')||' to your stud '||coalesce(p_sire->>'name','')||' ($'||fee||').', p_post, rid);
  else perform hd_hub_notify(p_to, 'req_female', p_pid, r||' offered '||coalesce(p_sire->>'name','a stud')||' for your female '||coalesce(p_dam->>'name','')||' ($'||fee||' stud fee).', p_post, rid); end if;
  return rid;
end $$;

create or replace function public.hd_hub_breeds(p_pid uuid, p_sec text) returns jsonb language plpgsql security definer set search_path to 'public' as $$
begin
  perform hd_check(p_pid, p_sec);
  return coalesce((select jsonb_agg(to_jsonb(b) order by b.updated_at desc) from (select * from hd_hub_breeds where sire_owner = p_pid or dam_owner = p_pid order by updated_at desc limit 80) b), '[]'::jsonb);
end $$;

-- accept / decline / counter: only the side whose turn it is; a counter hands the turn back
create or replace function public.hd_hub_breed_respond(p_pid uuid, p_sec text, p_id bigint, p_action text, p_fee integer) returns jsonb language plpgsql security definer set search_path to 'public' as $$
declare b hd_hub_breeds; other uuid; r text;
begin
  perform hd_check(p_pid, p_sec);
  select * into b from hd_hub_breeds where id = p_id for update;
  if not found or p_pid not in (b.sire_owner, b.dam_owner) then raise exception 'That request was not found.'; end if;
  if b.status not in ('pending','countered') then raise exception 'That request has already been answered.'; end if;
  if b.turn <> p_pid then raise exception 'Waiting on the other player.'; end if;
  other := case when p_pid = b.sire_owner then b.dam_owner else b.sire_owner end; r := hd_hub_ranch(p_pid);
  if p_action = 'accept' then
    update hd_hub_breeds set status = 'agreed', turn = null, updated_at = now() where id = p_id;
    perform hd_hub_notify(other, 'req_ok', p_pid, r||' accepted the breeding: '||(b.dam->>'name')||' × '||(b.sire->>'name')||' for $'||b.fee||'. Confirm the contract to go ahead.', b.post_id, p_id);
  elsif p_action = 'decline' then
    update hd_hub_breeds set status = 'declined', turn = null, updated_at = now() where id = p_id;
    perform hd_hub_notify(other, 'req_no', p_pid, r||' declined the breeding of '||(b.dam->>'name')||' × '||(b.sire->>'name')||'.', b.post_id, p_id);
  elsif p_action = 'counter' then
    if p_fee is null or p_fee < 0 or p_fee > 1000000 then raise exception 'Fees run from $0 to $1,000,000.'; end if;
    update hd_hub_breeds set status = 'countered', fee = p_fee, turn = other, updated_at = now() where id = p_id;
    perform hd_hub_notify(other, 'req_counter', p_pid, r||' made a counter offer: $'||p_fee||' for '||(b.dam->>'name')||' × '||(b.sire->>'name')||'.', b.post_id, p_id);
  else raise exception 'bad action'; end if;
  return (select to_jsonb(x) from hd_hub_breeds x where id = p_id);
end $$;

-- both players confirm the contract before anything is bred
create or replace function public.hd_hub_breed_confirm(p_pid uuid, p_sec text, p_id bigint) returns jsonb language plpgsql security definer set search_path to 'public' as $$
declare b hd_hub_breeds; other uuid;
begin
  perform hd_check(p_pid, p_sec);
  select * into b from hd_hub_breeds where id = p_id for update;
  if not found or p_pid not in (b.sire_owner, b.dam_owner) then raise exception 'That contract was not found.'; end if;
  if b.status <> 'agreed' then raise exception 'That contract is not waiting for confirmation.'; end if;
  if p_pid = b.sire_owner then b.sire_ok := true; else b.dam_ok := true; end if;
  update hd_hub_breeds set sire_ok = b.sire_ok, dam_ok = b.dam_ok, status = case when b.sire_ok and b.dam_ok then 'confirmed' else 'agreed' end, updated_at = now() where id = p_id;
  other := case when p_pid = b.sire_owner then b.dam_owner else b.sire_owner end;
  if b.sire_ok and b.dam_ok then perform hd_hub_notify(other, 'contract', p_pid, 'Breeding contract confirmed: '||(b.dam->>'name')||' × '||(b.sire->>'name')||'.', b.post_id, p_id);
  else perform hd_hub_notify(other, 'contract', p_pid, hd_hub_ranch(p_pid)||' confirmed the contract for '||(b.dam->>'name')||' × '||(b.sire->>'name')||'. Your turn to confirm.', b.post_id, p_id); end if;
  return (select to_jsonb(x) from hd_hub_breeds x where id = p_id);
end $$;

-- the female's owner breeds her: the stud fee goes to the stud's owner, and their game makes the pups with its own genetics
create or replace function public.hd_hub_breed_claim(p_pid uuid, p_sec text, p_id bigint) returns jsonb language plpgsql security definer set search_path to 'public' as $$
declare b hd_hub_breeds;
begin
  perform hd_check(p_pid, p_sec);
  select * into b from hd_hub_breeds where id = p_id for update;
  if not found or b.dam_owner <> p_pid then raise exception 'That contract was not found.'; end if;
  if b.status <> 'confirmed' then raise exception 'Both players have to confirm the contract first.'; end if;
  update hd_hub_breeds set status = 'bred', updated_at = now() where id = p_id;
  if b.fee > 0 then insert into hd_payouts(player_id, amount, reason, payer) values (b.sire_owner, b.fee, 'Stud fee for '||coalesce(b.sire->>'name','your stud')||' (breeding contract with '||b.dam_ranch||')', p_pid); end if;
  if b.listing_id is not null then update hd_listings set uses = uses + 1 where id = b.listing_id; end if;
  perform hd_hub_notify(b.sire_owner, 'bred', p_pid, (b.dam->>'name')||' was bred to your stud '||(b.sire->>'name')||'. The $'||b.fee||' fee is on its way.', b.post_id, p_id);
  return (select to_jsonb(x) from hd_hub_breeds x where id = p_id);
end $$;

-- the pups are born in the female owner's game; the litter is recorded so both players see it
create or replace function public.hd_hub_breed_born(p_pid uuid, p_sec text, p_id bigint, p_litter jsonb) returns void language plpgsql security definer set search_path to 'public' as $$
declare b hd_hub_breeds;
begin
  perform hd_check(p_pid, p_sec);
  select * into b from hd_hub_breeds where id = p_id for update;
  if not found or b.dam_owner <> p_pid or b.status <> 'bred' then raise exception 'That breeding is not waiting on a litter.'; end if;
  if pg_column_size(p_litter) > 60000 then raise exception 'too large'; end if;
  update hd_hub_breeds set status = 'born', litter = p_litter, updated_at = now() where id = p_id;
  perform hd_hub_notify(b.sire_owner, 'litter', p_pid, (b.dam->>'name')||' × '||(b.sire->>'name')||': '||coalesce(jsonb_array_length(p_litter->'pups'),0)||' pups were born at '||b.dam_ranch||'.', b.post_id, p_id);
end $$;

create or replace function public.hd_hub_breed_cancel(p_pid uuid, p_sec text, p_id bigint) returns void language plpgsql security definer set search_path to 'public' as $$
declare b hd_hub_breeds;
begin
  perform hd_check(p_pid, p_sec);
  select * into b from hd_hub_breeds where id = p_id for update;
  if not found or p_pid not in (b.sire_owner, b.dam_owner) then raise exception 'That request was not found.'; end if;
  if b.status not in ('pending','countered','agreed','confirmed') then raise exception 'That breeding can no longer be called off.'; end if;
  update hd_hub_breeds set status = 'cancelled', turn = null, updated_at = now() where id = p_id;
  perform hd_hub_notify(case when p_pid = b.sire_owner then b.dam_owner else b.sire_owner end, 'req_no', p_pid, hd_hub_ranch(p_pid)||' called off the breeding of '||(b.dam->>'name')||' × '||(b.sire->>'name')||'.', b.post_id, p_id);
end $$;

-- ---------- search ----------
create or replace function public.hd_hub_search(p_pid uuid, p_sec text, p_q text) returns jsonb language plpgsql security definer set search_path to 'public' as $$
declare q text := '%'||regexp_replace(lower(left(trim(coalesce(p_q,'')),60)), '[%_\\]', '', 'g')||'%';
begin
  perform hd_check(p_pid, p_sec);
  return jsonb_build_object(
    'posts', coalesce((select jsonb_agg(hd_hub_post_json(p::hd_hub_posts, p_pid) order by p.id desc) from (select * from hd_hub_posts p where not hidden and (lower(title) like q or lower(body) like q or lower(ranch) like q or lower(p.data::text) like q)
       and not exists(select 1 from hd_hub_blocks k where k.player_id = p_pid and k.target = p.player_id) order by id desc limit 30) p), '[]'::jsonb),
    'studs', coalesce((select jsonb_agg(jsonb_build_object('id', id, 'seller', seller, 'ranch', seller_ranch, 'price', price, 'dog', dog, 'info', info, 'uses', uses)) from (select * from hd_listings where kind = 'stud' and status = 'open' and animal = 'dog'
       and (lower(coalesce(dog_name,'')) like q or lower(coalesce(breed,'')) like q or lower(seller_ranch) like q or lower(coalesce(dog->'bl'->>'line','')) like q or lower(dog::text) like q) limit 40) l), '[]'::jsonb),
    'dogs', coalesce((select jsonb_agg(jsonb_build_object('owner', player_id, 'ranch', name, 'dog', d)) from (select r.player_id, r.name, d from hd_ranches r, jsonb_array_elements(r.snapshot) d
       where lower(coalesce(d->>'name','')) like q or lower(coalesce(d->>'breed','')) like q or lower(coalesce(d->>'cross','')) like q or lower(coalesce(d->'bl'->>'line','')) like q or lower(r.name) like q or ('gen '||coalesce(d->>'gen','0')) like q limit 80) x), '[]'::jsonb),
    'players', coalesce((select jsonb_agg(jsonb_build_object('player_id', r.player_id, 'ranch', coalesce(f.ranch, r.name), 'club', f.club, 'level', r.level, 'rep', hd_hub_rep(r.player_id), 'avatar', f.avatar))
       from hd_ranches r left join hd_hub_profiles f on f.player_id = r.player_id where lower(r.name) like q or lower(coalesce(f.ranch,'')) like q or lower(coalesce(f.club,'')) like q or lower(coalesce(r.best_line,'')) like q limit 30), '[]'::jsonb),
    'clubs', coalesce((select jsonb_agg(jsonb_build_object('id', g.id, 'name', g.name, 'motto', g.motto, 'members', (select count(*) from hd_group_members m where m.group_id = g.id),
       'following', exists(select 1 from hd_hub_follows w where w.player_id = p_pid and w.kind = 'club' and w.target = g.id::text))) from hd_groups g where lower(g.name) like q or lower(coalesce(g.motto,'')) like q limit 20), '[]'::jsonb));
end $$;
