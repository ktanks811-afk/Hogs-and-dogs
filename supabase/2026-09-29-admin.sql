-- Admin accounts. The in-game Admin menu only appears for players listed here, and the game asks the server
-- through hd_is_admin (which checks the player's secret first) before every admin action.
-- The table has RLS on and no policies: nobody can add themselves from the game; admins are added here in SQL.
create table if not exists public.hd_admins(
  player_id uuid primary key references public.hd_players(id) on delete cascade,
  added_at timestamptz not null default now());
alter table public.hd_admins enable row level security;

create or replace function public.hd_is_admin(p_pid uuid, p_sec text)
returns boolean language plpgsql security definer set search_path = public as $$
begin
  perform hd_check(p_pid, p_sec);
  return exists(select 1 from hd_admins where player_id = p_pid);
end $$;
revoke all on function public.hd_is_admin(uuid, text) from public;
grant execute on function public.hd_is_admin(uuid, text) to anon, authenticated;

-- the game's owner
insert into public.hd_admins(player_id)
select id from public.hd_players where lower(username) = 'kingkt'
on conflict do nothing;

-- a second admin, added at the owner's request
insert into public.hd_admins(player_id)
select id from public.hd_players where lower(username) = 'ogsolo'
on conflict do nothing;
