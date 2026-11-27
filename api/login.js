const A = require('../lib/auth');
const crypto = require('crypto');
const tries = new Map(); // กันเดารหัสแบบง่าย ๆ (ต่อ instance)

module.exports = async (req, res) => {
  A.cors(res);
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'POST') return res.status(405).json({ ok: false, error: 'ใช้ POST เท่านั้น' });
  const { username = '', password = '' } = A.body(req);
  const u = String(username).trim();
  const ip = String(req.headers['x-forwarded-for'] || '').split(',')[0].trim();
  const k = ip + '|' + u.toLowerCase();
  const t = tries.get(k) || { n: 0, until: 0 };
  if (t.until > Date.now()) return res.status(429).json({ ok: false, error: 'ลองผิดหลายครั้ง กรุณารอสักครู่แล้วลองใหม่' });
  const fail = async () => {
    t.n++; if (t.n >= 5) { t.until = Date.now() + 60000; t.n = 0; } tries.set(k, t);
    await new Promise((r) => setTimeout(r, 400));
    return res.status(401).json({ ok: false, error: 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง' });
  };
  if (!u || !password) return fail();

  const adminUser = process.env.ADMIN_USER || 'admin', adminPass = process.env.ADMIN_PASS || '';
  try {
    if (adminPass && u === adminUser) {
      const a = crypto.createHash('sha256').update(String(password)).digest(), b = crypto.createHash('sha256').update(adminPass).digest();
      if (!crypto.timingSafeEqual(a, b)) return fail();
      tries.delete(k);
      return res.status(200).json({ ok: true, token: A.sign({ u, r: 'admin' }), user: { username: u, role: 'admin', name: 'Admin' } });
    }
    const user = await A.store.get(u.toLowerCase());
    if (!user || !A.checkPw(password, user)) return fail();
    if (!user.active) return res.status(403).json({ ok: false, error: 'บัญชีนี้ถูกปิดใช้งาน' });
    if (user.expires && Date.parse(user.expires) < Date.now()) return res.status(403).json({ ok: false, error: 'บัญชีนี้หมดอายุแล้ว' });
    user.lastLogin = new Date().toISOString(); await A.store.put(user);
    tries.delete(k);
    return res.status(200).json({ ok: true, token: A.sign({ u: user.username, r: 'member' }), user: { username: user.username, role: 'member', name: user.name || user.username } });
  } catch (e) { return res.status(500).json({ ok: false, error: e.message }); }
};
