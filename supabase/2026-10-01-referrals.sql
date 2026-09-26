-- Invite a friend. A new player who arrives through someone's invite link names them once, right after making an
-- account; both get a bonus. The new player's bonus is paid in the game when this returns 'ok'; the inviter's bonuses
-- are collected (once each) the next time they play, through hd_referral_rewards.
-- RLS on, no policies: only these functions (which check the player's secret first) touch the table.
create table if not exists public.hd_referrals(
  player_id uuid primary key references public.hd_players(id) on delete cascade,
  referrer_id uuid not null references public.hd_players(id) on delete cascade,
  created_at timestamptz not null default now(),
  referrer_paid boolean not null default false);
create index if not exists hd_referrals_referrer on public.hd_referrals(referrer_id);
alter table public.hd_referrals enable row level security;

create or replace function public.hd_refer(p_pid uuid, p_sec text, p_ref text)
returns text language plpgsql security definer set search_path = public as $$
declare r uuid; made timestamptz;
begin
  perform hd_check(p_pid, p_sec);
  select id into r from hd_players where lower(username) = lower(trim(p_ref));
  if r is null then return 'unknown'; end if;
  if r = p_pid then return 'self'; end if;
  if exists(select 1 from hd_referrals where player_id = p_pid) then return 'already'; end if;
  select created_at into made from hd_players where id = p_pid;
  if made < now() - interval '7 days' then return 'too_old'; end if;
  insert into hd_referrals(player_id, referrer_id) values (p_pid, r);
  return 'ok';
end $$;

-- how many new friend bonuses are waiting for this player (and marks them collected), plus the lifetime total
create or replace function public.hd_referral_rewards(p_pid uuid, p_sec text)
returns json language plpgsql security definer set search_path = public as $$
declare n int; tot int;
begin
  perform hd_check(p_pid, p_sec);
  with paid as (update hd_referrals set referrer_paid = true where referrer_id = p_pid and not referrer_paid returning 1)
  select count(*) into n from paid;
  select count(*) into tot from hd_referrals where referrer_id = p_pid;
  return json_build_object('new', n, 'total', tot);
end $$;

revoke all on function public.hd_refer(uuid, text, text) from public;
revoke all on function public.hd_referral_rewards(uuid, text) from public;
grant execute on function public.hd_refer(uuid, text, text) to anon, authenticated;
grant execute on function public.hd_referral_rewards(uuid, text) to anon, authenticated;
