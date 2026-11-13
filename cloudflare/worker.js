// Бесплатный сервер оплаты Premium (Cloudflare Workers + KV). Вставь этот код целиком в Worker.
const PRICE = 100; // цена в звёздах Telegram

const hex = b => [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, "0")).join("");
async function hmac(key, data) {
  const k = await crypto.subtle.importKey("raw", key, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return crypto.subtle.sign("HMAC", k, data);
}
// Проверяем подпись Telegram, чтобы нельзя было подделать чужой ID
async function userId(initData, token) {
  const p = new URLSearchParams(initData), h = p.get("hash");
  p.delete("hash");
  const str = [...p.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1)).map(([k, v]) => k + "=" + v).join("\n");
  const enc = new TextEncoder();
  const secret = await hmac(enc.encode("WebAppData"), enc.encode(token));
  if (hex(await hmac(secret, enc.encode(str))) !== h) return null;
  return JSON.parse(p.get("user")).id;
}

// ---------- Озвучка ElevenLabs: GET /tts?t=<английский текст> -> mp3 ----------
// Секрет: ELEVENLABS_API_KEY (или ELEVEN_API_KEY). Необязательно: ELEVENLABS_VOICE_ID, TTS_DAILY_MAX (новых фраз в сутки, по умолчанию 300).
const VOICE = "hpp4J3VqNfWAUOO0d1Us"; // Bella (как в скрипте генерации mp3)
const TTS_MAX_CHARS = 160, TTS_DAILY_DEFAULT = 300;

async function sha16(text) {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return hex(d).slice(0, 32);
}
function audioResponse(bytes, req) {
  const total = bytes.byteLength;
  const base = {
    "Content-Type": "audio/mpeg", "Accept-Ranges": "bytes",
    "Cache-Control": "public, max-age=31536000, immutable", "Access-Control-Allow-Origin": "*",
  };
  const m = /^bytes=(\d*)-(\d*)$/.exec(req.headers.get("Range") || "");
  if (m && (m[1] || m[2])) {  // Safari на iPhone просит файл кусками
    let start, end;
    if (m[1] === "") { start = Math.max(0, total - Number(m[2])); end = total - 1; }
    else { start = Number(m[1]); end = m[2] === "" ? total - 1 : Math.min(Number(m[2]), total - 1); }
    if (start > end || start >= total)
      return new Response(null, { status: 416, headers: { ...base, "Content-Range": `bytes */${total}` } });
    return new Response(req.method === "HEAD" ? null : bytes.slice(start, end + 1), {
      status: 206,
      headers: { ...base, "Content-Range": `bytes ${start}-${end}/${total}`, "Content-Length": String(end - start + 1) },
    });
  }
  return new Response(req.method === "HEAD" ? null : bytes, { status: 200, headers: { ...base, "Content-Length": String(total) } });
}
async function tts(req, env, url) {
  const err = (status, msg) => new Response(msg, {
    status, headers: { "Access-Control-Allow-Origin": "*", "Cache-Control": "no-store", "Content-Type": "text/plain; charset=utf-8" },
  });
  const text = (url.searchParams.get("t") || "").replace(/\s+/g, " ").trim();
  if (!text || text.length > TTS_MAX_CHARS || !/[A-Za-z]/.test(text) ||
      !/^[\x20-\x7E\u2018\u2019\u201C\u201D\u2013\u2014\u2026]+$/.test(text)) return err(400, "bad text");
  const voice = env.ELEVENLABS_VOICE_ID || VOICE, model = env.ELEVENLABS_MODEL || "eleven_flash_v2_5";
  const key = "t:" + await sha16(voice + "|" + model + "|" + text);
  let bytes = await env.PREM.get(key, "arrayBuffer");   // уже озвучено раньше: бесплатно
  if (!bytes) {
    const elKey = env.ELEVENLABS_API_KEY || env.ELEVEN_API_KEY;   // подойдёт любое из двух имён секрета
    if (!elKey) return err(503, "no ElevenLabs key");
    const ck = "cap:" + new Date().toISOString().slice(0, 10);
    const used = parseInt((await env.PREM.get(ck)) || "0", 10);
    if (used >= parseInt(env.TTS_DAILY_MAX || TTS_DAILY_DEFAULT, 10)) return err(429, "daily limit");
    await env.PREM.put(ck, String(used + 1), { expirationTtl: 172800 });
    const r = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${voice}?output_format=mp3_44100_128`, {
      method: "POST",
      headers: { "xi-api-key": elKey, "Content-Type": "application/json", Accept: "audio/mpeg" },
      body: JSON.stringify({ text, model_id: env.ELEVENLABS_MODEL || "eleven_flash_v2_5", voice_settings: { stability: 0.5, similarity_boost: 0.8, speed: 0.95 } }),
    }).catch(() => null);
    if (!r || !r.ok) return err(502, "ElevenLabs " + (r ? r.status : "unreachable"));
    bytes = await r.arrayBuffer();
    if (bytes.byteLength < 500) return err(502, "empty audio");
    await env.PREM.put(key, bytes);
  }
  return audioResponse(bytes, req);
}

const tg = (env, method, body) =>
  fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }).then(r => r.json());

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const H = {
      "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN || "*",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Content-Type": "application/json",
    };
    const J = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: H });
    if (req.method === "OPTIONS") return new Response(null, { headers: H });

    if (url.pathname === "/tts" && (req.method === "GET" || req.method === "HEAD")) return tts(req, env, url);

    // Сюда Telegram присылает платежи
    if (url.pathname === "/webhook") {
      if (req.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) return new Response("no", { status: 403 });
      const u = await req.json();
      if (u.pre_checkout_query) await tg(env, "answerPreCheckoutQuery", { pre_checkout_query_id: u.pre_checkout_query.id, ok: true });
      if (u.message && u.message.successful_payment) {
        await env.PREM.put("u" + u.message.from.id, "1");
        await tg(env, "sendMessage", { chat_id: u.message.chat.id, text: "👑 Premium активирован! Возвращайся в приложение." });
      }
      return new Response("ok");
    }

    if (req.method !== "POST") return new Response("premium server works", { headers: H });
    const { initData = "" } = await req.json().catch(() => ({}));
    const uid = await userId(initData, env.BOT_TOKEN);
    if (!uid) return J({ error: "bad signature" }, 403);

    if (url.pathname === "/status") return J({ premium: !!(await env.PREM.get("u" + uid)) });
    if (url.pathname === "/invoice") {
      const r = await tg(env, "createInvoiceLink", {
        title: "Premium",
        description: "Монеты x2, бонус каждый день, заморозка серии, −20% в магазине",
        payload: "premium:" + uid, provider_token: "", currency: "XTR",
        prices: [{ label: "Premium", amount: PRICE }],
      });
      if (!r.ok) return J({ error: "telegram: " + (r.description || "unknown") }, 502);
      return J({ link: r.result });
    }
    return J({}, 404);
  },
};
