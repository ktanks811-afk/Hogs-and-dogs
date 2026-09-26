-- Dynamic world events: the rare giant boar (up to 620 lb) can go on the biggest-hog board, and seasons make
-- hogs heavier (up to 8% in winter), so the weight check allows 30% over a type's heaviest instead of 18%.
create or replace function public.hd_record_hog(p_pid uuid, p_sec text, p_ranch text, p_hog text, p_weight integer, p_area text, p_dogs text)
returns void language plpgsql security definer set search_path = public as $$
declare maxw integer; nm text;
begin
  perform hd_check(p_pid, p_sec);
  select m, n into maxw, nm from (values ('feral',150,'Feral hog'),('razor',220,'Razorback'),('spotted',260,'Spotted boar'),('russian',350,'Russian-cross boar'),('ghost',460,'Ghost boar'),('giant',620,'Giant boar')) v(k,m,n) where k = p_hog;
  if maxw is null then raise exception 'unknown hog'; end if;
  -- terrain, hunting-access upgrades and the season add at most 27% to a hog's weight
  if p_weight < 20 or p_weight > ceil(maxw * 1.3) then raise exception 'That weight is not possible.'; end if;
  if p_area not in ('creek','pine','swamp','thicket') then raise exception 'unknown area'; end if;
  if exists (select 1 from hd_hog_catches where player_id = p_pid and caught_at > now() - interval '60 seconds') then raise exception 'Too many catches too quickly.'; end if;
  insert into hd_hog_catches(player_id, ranch_name, hog_key, hog_name, weight, area, dogs)
  values (p_pid, left(coalesce(nullif(trim(p_ranch),''),'A ranch'),40), p_hog, nm, p_weight, p_area, left(coalesce(p_dogs,''),80));
end $$;
