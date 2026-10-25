import { createClient } from "npm:@supabase/supabase-js@2.45.4";
import { handle, type Store } from "./handler.ts";

const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

const store: Store = {
  async insert(row) {
    const { error } = await db.from("approvals").insert(row);
    if (error) throw error;
  },
  async pending(approvalId) {
    const { data, error } = await db.from("approvals").select("approval_id, answer, from_number, received_at")
      .eq("approval_id", approvalId).order("id");
    if (error) throw error;
    return data ?? [];
  },
};

const env = {
  verifyToken: Deno.env.get("WA_VERIFY_TOKEN")!,
  appSecret: Deno.env.get("WA_APP_SECRET")!,
  relaySecret: Deno.env.get("RELAY_SECRET")!,
};

Deno.serve((req) => handle(req, env, store));
