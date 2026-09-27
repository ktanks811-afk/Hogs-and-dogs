// Sends due Web Push notifications. Called every few minutes by pg_cron (through pg_net) with the cron secret;
// hd_push_take checks that secret against Vault, marks the due messages sent and hands back the VAPID key.
import webpush from "npm:web-push@3.6.7";
import { createClient } from "npm:@supabase/supabase-js@2";

const VAPID_PUBLIC = "BCfFtua2RgKjt1cKin-FfnSIQTcwMbp4foymA6jT10MgKQTusf53Xqlbn7j7Y8mFrovA6fIbMfNz96HxaFjTlAQ";

Deno.serve(async (req) => {
  const secret = req.headers.get("x-cron-secret") || "";
  const sb = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const { data, error } = await sb.rpc("hd_push_take", { p_secret: secret, p_limit: 200 });
  if (error) return new Response(JSON.stringify({ error: "denied" }), { status: 403 });
  const { vapid, msgs } = data as { vapid: string; msgs: any[] };
  if (!msgs.length) return Response.json({ sent: 0 });
  webpush.setVapidDetails("https://hogs-and-dogs.vercel.app", VAPID_PUBLIC, vapid);
  const gone: string[] = [], ok: string[] = [];
  let sent = 0;
  await Promise.all(msgs.flatMap((m) => (m.subs || []).map(async (s: any) => {
    try {
      await webpush.sendNotification(s, JSON.stringify({ title: m.title, body: m.body, tag: m.tag }), { TTL: 60 * 60 * 12 });
      ok.push(s.endpoint); sent++;
    } catch (e: any) {
      if (e && (e.statusCode === 404 || e.statusCode === 410)) gone.push(s.endpoint);
      else console.warn("push failed", e && e.statusCode, e && e.body);
    }
  })));
  if (gone.length || ok.length) await sb.rpc("hd_push_drop", { p_secret: secret, p_endpoints: gone, p_ok: ok });
  return Response.json({ sent, gone: gone.length });
});
