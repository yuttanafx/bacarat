const A = require('../lib/auth');
module.exports = async (req, res) => {
  A.cors(res);
  if (req.method === 'OPTIONS') return res.status(204).end();
  const u = await A.currentUser(req);
  if (!u) return res.status(401).json({ ok: false, error: 'unauthorized' });
  res.status(200).json({ ok: true, user: u });
};
