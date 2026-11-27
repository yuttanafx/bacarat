// จัดการสมาชิก (เฉพาะแอดมิน)
//   GET    /api/admin?q=ค้นหา&status=active|disabled|expired   รายชื่อ (กรองได้)
//   POST   /api/admin   {username,password,name?,expires?,note?}  สร้างสมาชิก
//   PATCH  /api/admin   {username, active?, password?, name?, expires?, note?}
//   DELETE /api/admin?username=...
const A = require('../lib/auth');
// 'YYYY-MM-DD' = ใช้ได้ถึงสิ้นวันนั้นตามเวลาไทย; รับ {days:N} = นับจากตอนนี้
const toExpiry = (v, days) => {
  if (days) { const n = Number(days); return Number.isFinite(n) && n > 0 && n <= 3650 ? new Date(Date.now() + n * 86400000).toISOString() : undefined; }
  if (!v) return null;
  const d = new Date(/^\d{4}-\d{2}-\d{2}$/.test(v) ? v + 'T23:59:59+07:00' : v);
  return isNaN(d) ? undefined : d.toISOString();
};

module.exports = async (req, res) => {
  A.cors(res);
  if (req.method === 'OPTIONS') return res.status(204).end();
  const me = await A.currentUser(req);
  if (!me || me.role !== 'admin') return res.status(401).json({ ok: false, error: 'ต้องเป็นแอดมิน' });
  const q = req.query || {};
  try {
    if (req.method === 'GET') {
      let list = (await A.store.all()).map(A.publicUser);
      const now = Date.now();
      const expired = (u) => u.expires && Date.parse(u.expires) < now;
      const s = String(q.q || '').trim().toLowerCase();
      if (s) list = list.filter((u) => (u.username + ' ' + u.name + ' ' + u.note).toLowerCase().includes(s));
      if (q.status === 'active') list = list.filter((u) => u.active && !expired(u));
      else if (q.status === 'disabled') list = list.filter((u) => !u.active);
      else if (q.status === 'expired') list = list.filter(expired);
      list.sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt)));
      return res.status(200).json({ ok: true, persistent: A.persistent, total: list.length, users: list });
    }
    if (req.method === 'POST') {
      const b = A.body(req);
      const username = String(b.username || '').trim().toLowerCase();
      if (!A.USER_RE.test(username)) return res.status(400).json({ ok: false, error: 'ชื่อผู้ใช้ 3-32 ตัว ใช้ a-z 0-9 _ . - เท่านั้น' });
      if (username === (process.env.ADMIN_USER || 'admin').toLowerCase()) return res.status(400).json({ ok: false, error: 'ชื่อนี้สงวนไว้สำหรับแอดมิน' });
      if (String(b.password || '').length < 6) return res.status(400).json({ ok: false, error: 'รหัสผ่านอย่างน้อย 6 ตัวอักษร' });
      if (await A.store.get(username)) return res.status(409).json({ ok: false, error: 'มีชื่อผู้ใช้นี้แล้ว' });
      const exp = toExpiry(b.expires, b.days);
      if (exp === undefined) return res.status(400).json({ ok: false, error: 'วันหมดอายุไม่ถูกต้อง' });
      const user = { username, name: String(b.name || '').slice(0, 80), note: String(b.note || '').slice(0, 200), active: true,
        expires: exp, createdAt: new Date().toISOString(), ...A.hashPw(b.password) };
      await A.store.put(user);
      return res.status(201).json({ ok: true, user: A.publicUser(user) });
    }
    if (req.method === 'PATCH') {
      const b = A.body(req);
      const user = await A.store.get(String(b.username || '').toLowerCase());
      if (!user) return res.status(404).json({ ok: false, error: 'ไม่พบสมาชิก' });
      if (typeof b.active === 'boolean') user.active = b.active;
      if (typeof b.name === 'string') user.name = b.name.slice(0, 80);
      if (typeof b.note === 'string') user.note = b.note.slice(0, 200);
      if ('expires' in b || b.days) { const exp = toExpiry(b.expires, b.days); if (exp === undefined) return res.status(400).json({ ok: false, error: 'วันหมดอายุไม่ถูกต้อง' }); user.expires = exp; }
      if (b.password) { if (String(b.password).length < 6) return res.status(400).json({ ok: false, error: 'รหัสผ่านอย่างน้อย 6 ตัวอักษร' }); Object.assign(user, A.hashPw(b.password)); }
      await A.store.put(user);
      return res.status(200).json({ ok: true, user: A.publicUser(user) });
    }
    if (req.method === 'DELETE') {
      const u = String(q.username || '').toLowerCase();
      if (!(await A.store.get(u))) return res.status(404).json({ ok: false, error: 'ไม่พบสมาชิก' });
      await A.store.del(u);
      return res.status(200).json({ ok: true, deleted: u });
    }
    return res.status(405).json({ ok: false, error: 'method not allowed' });
  } catch (e) { return res.status(500).json({ ok: false, error: e.message }); }
};
