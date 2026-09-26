-- Most-hogs leaderboard: how many verified catches each player has (every catch goes through hd_record_hog),
-- all time or in the last 7 days, with their heaviest hog in that period for a tie-break and a bit of colour.
create or replace function public.hd_hog_count_board(p_period text default 'all', p_limit integer default 50)
returns table(player_id uuid, ranch_name text, hogs integer, biggest integer, last_catch timestamptz)
language sql stable security definer set search_path = public as $$
  select c.player_id,
         (array_agg(c.ranch_name order by c.caught_at desc))[1] as ranch_name,
         count(*)::integer as hogs,
         max(c.weight) as biggest,
         max(c.caught_at) as last_catch
  from hd_hog_catches c
  where p_period = 'all' or c.caught_at > now() - interval '7 days'
  group by c.player_id
  order by hogs desc, biggest desc, last_catch asc
  limit least(greatest(coalesce(p_limit,50),1),100)
$$;
grant execute on function public.hd_hog_count_board(text, integer) to anon, authenticated;
