// Vercel Serverless Function: รับ webhook จากหน้าเว็บที่ /hook (ผ่าน rewrite ใน vercel.json)
// ตัวแปรสภาพแวดล้อม (ตั้งใน Vercel > Settings > Environment Variables) ไม่บังคับ:
//   HOOK_TOKEN   ถ้าตั้งไว้ ต้องเรียกเป็น /hook?token=ค่านี้ มิฉะนั้นตอบ 401 (กันคนอื่นยิงมั่ว)
//   FORWARD_URL  ถ้าตั้งไว้ จะส่งต่อข้อมูลเดิมไปยัง URL นี้ (เช่น n8n / Make / Zapier)
module.exports = async (req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, GET, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  if (req.method === "OPTIONS") return res.status(204).end();

  if (req.method === "GET") {
    return res.status(200).json({ ok: true, message: "webhook พร้อมรับข้อมูล (ส่งด้วย POST เป็น JSON)" });
  }
  if (req.method !== "POST") return res.status(405).json({ ok: false, error: "ใช้ POST เท่านั้น" });

  const token = process.env.HOOK_TOKEN;
  if (token && (req.query || {}).token !== token) return res.status(401).json({ ok: false, error: "token ไม่ถูกต้อง" });

  let body = req.body;
  if (typeof body === "string") { try { body = JSON.parse(body); } catch { body = null; } }
  if (!body || typeof body !== "object") return res.status(400).json({ ok: false, error: "ต้องเป็น JSON" });

  const boards = body.board ? [body.board] : Array.isArray(body.boards) ? body.boards : [];
  console.log("webhook", JSON.stringify({
    event: body.event || "unknown",
    boards: boards.length,
    hands: boards.reduce((a, b) => a + (b.hands || 0), 0),
    sent_at: body.sent_at || null
  }));

  let forwarded = null;
  if (process.env.FORWARD_URL) {
    try {
      const r = await fetch(process.env.FORWARD_URL, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
      });
      forwarded = r.status;
    } catch (e) { forwarded = "error: " + e.message; }
  }
  return res.status(200).json({ ok: true, received: boards.length, forwarded });
};
