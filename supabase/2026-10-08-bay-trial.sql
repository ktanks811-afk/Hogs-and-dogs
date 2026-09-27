-- Bay pen trials join the daily online events (show, race, bay). Same rules: one entry per ranch per day, prizes for
-- yesterday's top finishers through hd_claim_prize. A bay score is the judges' total out of 40, times five.
create or replace function public.hd_enter_event(p_pid uuid, p_sec text, p_key text, p_ranch text, p_dog jsonb, p_score numeric)
 returns void language plpgsql security definer set search_path to 'public' as $function$
declare st jsonb := p_dog->'stats';
begin
  perform hd_check(p_pid, p_sec);
  if p_key !~ '^(show|race|bay)-\d{4}-\d{2}-\d{2}$' then raise exception 'bad event'; end if;
  if substring(p_key from '\d{4}-\d{2}-\d{2}')::date <> (now() at time zone 'utc')::date then raise exception 'That event is closed.'; end if;
  if p_score < 0 or p_score > 200 then raise exception 'bad score'; end if;
  if not hd_dog_ok(p_dog) then raise exception 'That dog''s stats are not valid.'; end if;
  -- a race score is speed/stamina/smarts plus up to 15 points of luck, so it can't beat that
  if p_key like 'race-%' and p_score > (st->>'spd')::numeric*.6 + (st->>'sta')::numeric*.3 + (st->>'int')::numeric*.1 + 15.05 then
    raise exception 'bad score';
  end if;
  insert into hd_entries(event_key,event_date,player_id,ranch_name,dog,dog_name,score) values (p_key, (now() at time zone 'utc')::date, p_pid, left(p_ranch,40), p_dog, left(p_dog->>'name',30), p_score);
end $function$;
