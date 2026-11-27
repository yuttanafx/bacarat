// ระบบสมาชิก: เก็บใน Upstash Redis (ตั้ง UPSTASH_REDIS_REST_URL/TOKEN หรือ KV_REST_API_URL/TOKEN)
// ถ้าไม่ตั้ง จะใช้หน่วยความจำชั่วคราว (สมาชิกหายเมื่อ function รีสตาร์ท)
// env: ADMIN_USER (ค่าเริ่มต้น admin), ADMIN_PASS (จำเป็นสำหรับล็อกอินแอดมิน), AUTH_SECRET (ใช้เซ็น token; ถ้าไม่ตั้งใช้ ADMIN_PASS)
const crypto = require('crypto');

// หา env ของ Redis ให้ครบทุกชื่อที่ Vercel/Upstash ตั้งให้ (UPSTASH_REDIS_REST_*, KV_REST_API_*, หรือมี prefix เองเช่น STORAGE_REST_API_*)
function findRedisEnv() {
  const e = process.env;
  for (const [u, t] of [['UPSTASH_REDIS_REST_URL', 'UPSTASH_REDIS_REST_TOKEN'], ['KV_REST_API_URL', 'KV_REST_API_TOKEN']]) if (e[u] && e[t]) return { url: e[u], token: e[t], via: u };
  for (const k of Object.keys(e)) {
    const m = /^(.*)_(REST_API_URL|REST_URL)$/.exec(k);
    if (!m || !e[k]) continue;
    const t = m[1] + '_' + (m[2] === 'REST_API_URL' ? 'REST_API_TOKEN' : 'REST_TOKEN');
    if (e[t]) return { url: e[k], token: e[t], via: k };
  }
  return null;
}
const rEnv = findRedisEnv();
let redis = null;
if (rEnv) { const { Redis } = require('@upstash/redis'); redis = new Redis({ url: rEnv.url, token: rEnv.token }); }
const mem = new Map();
const KEY = 'bacc:users';
const persistent = !!redis;
const redisVia = rEnv ? rEnv.via : null; // ชื่อตัวแปรที่ใช้ (ไม่เปิดเผยค่า)

const store = {
  async get(u) {
    if (redis) { const v = await redis.hget(KEY, u); return v ? (typeof v === 'string' ? JSON.parse(v) : v) : null; }
    return mem.get(u) || null;
  },
  async put(user) {
    if (redis) await redis.hset(KEY, { [user.username]: JSON.stringify(user) }); else mem.set(user.username, user);
  },
  async del(u) { if (redis) await redis.hdel(KEY, u); else mem.delete(u); },
  async all() {
    if (redis) { const h = (await redis.hgetall(KEY)) || {}; return Object.values(h).map((v) => (typeof v === 'string' ? JSON.parse(v) : v)); }
    return [...mem.values()];
  },
};

const USER_RE = /^[a-zA-Z0-9_.-]{3,32}$/;
function hashPw(pw, salt = crypto.randomBytes(16).toString('hex')) {
  return { salt, hash: crypto.scryptSync(String(pw), salt, 32).toString('hex') };
}
function checkPw(pw, user) {
  const h = crypto.scryptSync(String(pw), user.salt, 32);
  const b = Buffer.from(user.hash, 'hex');
  return b.length === h.length && crypto.timingSafeEqual(h, b);
}

function secret() { return process.env.AUTH_SECRET || process.env.ADMIN_PASS || ''; }
const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
function sign(payload, ttlMs = 12 * 3600 * 1000) {
  const s = secret(); if (!s) throw new Error('ยังไม่ได้ตั้ง AUTH_SECRET หรือ ADMIN_PASS');
  const body = b64({ ...payload, exp: Date.now() + ttlMs });
  return body + '.' + crypto.createHmac('sha256', s).update(body).digest('base64url');
}
function verify(token) {
  const s = secret(); if (!s || !token) return null;
  const [body, sig] = String(token).split('.');
  if (!body || !sig) return null;
  const exp = crypto.createHmac('sha256', s).update(body).digest('base64url');
  if (sig.length !== exp.length || !crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(exp))) return null;
  try { const p = JSON.parse(Buffer.from(body, 'base64url').toString()); return p.exp > Date.now() ? p : null; } catch { return null; }
}

function bearer(req) {
  const a = req.headers.authorization || '';
  return a.toLowerCase().startsWith('bearer ') ? a.slice(7).trim() : '';
}
// ตรวจ token + สถานะสมาชิกปัจจุบัน (ถูกปิด/หมดอายุ = เข้าไม่ได้ทันที)
async function currentUser(req) {
  const p = verify(bearer(req)); if (!p) return null;
  if (p.r === 'admin') return { username: p.u, role: 'admin', name: 'Admin' };
  const u = await store.get(p.u);
  if (!u || !u.active || (u.expires && Date.parse(u.expires) < Date.now())) return null;
  return { username: u.username, role: 'member', name: u.name || u.username };
}

function cors(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PATCH, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  res.setHeader('Cache-Control', 'no-store');
}
function body(req) {
  let b = req.body;
  if (typeof b === 'string') { try { b = JSON.parse(b); } catch { b = null; } }
  return b && typeof b === 'object' ? b : {};
}
const publicUser = (u) => ({ username: u.username, name: u.name || '', role: 'member', active: !!u.active, expires: u.expires || null, createdAt: u.createdAt, lastLogin: u.lastLogin || null, note: u.note || '' });

module.exports = { store, persistent, redisVia, USER_RE, hashPw, checkPw, sign, verify, currentUser, cors, body, publicUser };
