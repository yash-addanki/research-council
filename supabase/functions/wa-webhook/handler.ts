// WhatsApp webhook relay: verifies Meta's signature, stores Yes/No button taps,
// and serves them to the Mac (which polls with a bearer secret).

export interface Env { verifyToken: string; appSecret: string; relaySecret: string }
export interface Row { approval_id: string; answer: string; from_number: string }
export interface Store {
  insert(row: Row): Promise<void>;
  pending(approvalId: string): Promise<Row[]>;
}

const enc = new TextEncoder();

async function validSignature(body: string, header: string | null, secret: string): Promise<boolean> {
  if (!header?.startsWith("sha256=")) return false;
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(body)));
  const expected = "sha256=" + [...sig].map((b) => b.toString(16).padStart(2, "0")).join("");
  if (expected.length !== header.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i++) diff |= expected.charCodeAt(i) ^ header.charCodeAt(i);
  return diff === 0;
}

function replies(payload: any): Row[] {
  const out: Row[] = [];
  for (const entry of payload?.entry ?? []) {
    for (const change of entry?.changes ?? []) {
      for (const m of change?.value?.messages ?? []) {
        const id = m?.interactive?.button_reply?.id ?? m?.button?.payload;
        const match = typeof id === "string" ? id.match(/^([\w-]+):(yes|no)$/) : null;
        if (match) out.push({ approval_id: match[1], answer: match[2], from_number: String(m.from ?? "") });
      }
    }
  }
  return out;
}

export async function handle(req: Request, env: Env, store: Store): Promise<Response> {
  const url = new URL(req.url);
  if (req.method === "GET" && url.pathname.endsWith("/pending")) {
    if (req.headers.get("authorization") !== `Bearer ${env.relaySecret}`) return new Response("unauthorized", { status: 401 });
    const id = url.searchParams.get("approval_id") ?? "";
    return Response.json(await store.pending(id));
  }
  if (req.method === "GET") {
    const ok = url.searchParams.get("hub.mode") === "subscribe" && url.searchParams.get("hub.verify_token") === env.verifyToken;
    return ok ? new Response(url.searchParams.get("hub.challenge") ?? "") : new Response("forbidden", { status: 403 });
  }
  if (req.method === "POST") {
    const body = await req.text();
    if (!(await validSignature(body, req.headers.get("x-hub-signature-256"), env.appSecret))) {
      return new Response("bad signature", { status: 401 });
    }
    let payload: unknown;
    try { payload = JSON.parse(body); } catch { return new Response("ok"); }
    for (const row of replies(payload)) await store.insert(row);
    return new Response("ok");
  }
  return new Response("method not allowed", { status: 405 });
}
