-- Player properties for the Land & Property system. The table has RLS on and no policies, so the
-- public API can't read it; only these functions can, and hd_get_property checks the owner's
-- permission settings (enter / dogs / animals, co-owners, friends, shared hunting groups) first.
create table if not exists public.hd_properties(
  player_id uuid primary key references public.hd_players(id) on delete cascade,
  property jsonb not null,
  perms jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now());
alter table public.hd_properties enable row level security;

create or replace function public.hd_save_property(p_pid uuid, p_sec text, p_property jsonb, p_perms jsonb)
returns void language plpgsql security definer set search_path = public as $$
begin
  perform hd_check(p_pid, p_sec);
  if jsonb_typeof(p_property) <> 'object' then raise exception 'bad property'; end if;
  if pg_column_size(p_property) > 400000 then raise exception 'property too large'; end if;
  insert into hd_properties(player_id, property, perms, updated_at)
  values (p_pid, p_property, coalesce(p_perms,'{}'::jsonb), now())
  on conflict (player_id) do update set property = excluded.property, perms = excluded.perms, updated_at = now();
end $$;

create or replace function public.hd_get_property(p_pid uuid, p_sec text, p_owner uuid)
returns jsonb language plpgsql security definer set search_path = public as $$
declare r hd_properties; role text; see text;
begin
  perform hd_check(p_pid, p_sec);
  select * into r from hd_properties where player_id = p_owner;
  if not found then raise exception 'That ranch has not published its property yet.'; end if;
  if p_owner = p_pid then role := 'owner';
  elsif coalesce(r.perms->'coowners','[]'::jsonb) ? p_pid::text then role := 'coowner';
  elsif coalesce(r.perms->'friends','[]'::jsonb) ? p_pid::text
     or exists (select 1 from hd_group_members a join hd_group_members b on a.group_id = b.group_id
                where a.player_id = p_pid and b.player_id = p_owner) then role := 'friend';
  else role := 'visitor'; end if;
  -- may this role see something the owner set to everyone / friends / nobody (co-owners only)?
  see := case when role in ('owner','coowner') then 'all' when role = 'friend' then 'friends' else 'everyone' end;
  if not (see = 'all' or coalesce(r.perms->>'enter','friends') = 'everyone' or (see = 'friends' and coalesce(r.perms->>'enter','friends') = 'friends')) then
    raise exception 'This property is private.';
  end if;
  return jsonb_build_object(
    'role', role,
    'property', case when see = 'all' or coalesce(r.perms->>'animals','everyone') = 'everyone' or (see = 'friends' and coalesce(r.perms->>'animals','everyone') = 'friends')
                     then r.property else r.property - 'animals' - 'hogs' end,
    'animals', see = 'all' or coalesce(r.perms->>'animals','everyone') = 'everyone' or (see = 'friends' and coalesce(r.perms->>'animals','everyone') = 'friends'),
    'dogs', case when see = 'all' or coalesce(r.perms->>'dogs','friends') = 'everyone' or (see = 'friends' and coalesce(r.perms->>'dogs','friends') = 'friends')
                 then (select snapshot from hd_ranches where player_id = p_owner) else null end);
end $$;
