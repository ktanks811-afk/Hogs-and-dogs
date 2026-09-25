-- The game reads these tables directly. They already have read-all RLS policies, but the
-- anon role was never granted SELECT, so every read came back 401.
grant select on public.hd_ranches, public.hd_listings, public.hd_trades, public.hd_entries,
  public.hd_groups, public.hd_group_members to anon, authenticated;
