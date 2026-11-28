// ตัวส่งต่อไปฮุกสอง: หน้าเว็บส่งมาที่ /api/hook2 (ไม่มี key ในหน้าเว็บ) แล้วเซิร์ฟเวอร์ส่งต่อไป HOOK2_URL
// ต้องล็อกอินสมาชิกก่อน (Authorization: Bearer <token>) จึงส่งได้
// env: HOOK2_URL = URL เต็มของฮุกสองรวม ?key=... เช่น https://bacarat-hook2.vercel.app/api/hook2?key=xxxx
const A = require('../lib/auth');

module.exports = async (req, res) => {
  A.cors(res);
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'POST') return res.status(405).json({ ok: false, error: 'ใช้ POST เท่านั้น' });
  const me = await A.currentUser(req);
  if (!me) return res.status(401).json({ ok: false, error: 'ต้องเข้าสู่ระบบสมาชิกก่อน' });
  const url = process.env.HOOK2_URL;
  if (!/^https?:\/\//i.test(url || '')) return res.status(500).json({ ok: false, error: 'ยังไม่ได้ตั้ง HOOK2_URL ที่เซิร์ฟเวอร์' });
  try {
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(A.body(req)) });
    const text = await r.text();
    let out; try { out = JSON.parse(text); } catch { out = { ok: r.ok, raw: text.slice(0, 300) }; }
    return res.status(r.status).json(out);
  } catch (e) {
    return res.status(502).json({ ok: false, error: 'ติดต่อฮุกสองไม่ได้: ' + e.message });
  }
};
