import "dotenv/config";
import express from "express";
import cors from "cors";
import multer from "multer";
import pg from "pg";

import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = 5002;
app.use(cors({
  origin: function (origin, callback) {
    const allowed = [
      "http://localhost:5173",
      "https://pick-and-drop-2723.netlify.app",
      "https://pd.brittoo.xyz",
      "https://localhost",          // Capacitor Android WebView
      "capacitor://localhost"       // Capacitor iOS (future)
    ];
    if (!origin) return callback(null, true);
    if (allowed.includes(origin)) return callback(null, true);
    return callback(new Error("Not allowed by CORS"));
  },
  credentials: true,
  methods: ["GET", "POST", "PUT", "DELETE"],
  allowedHeaders: ["Content-Type"]
}));
app.set("trust proxy", 1);
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

const uploadsDir = path.join(__dirname, 'uploads');
if (!fs.existsSync(uploadsDir)) {
  fs.mkdirSync(uploadsDir);
}

/*
  url = http://localhost:5000/upload/image1.jpg
  /upload/image1.jpg
*/
app.use('/uploads', express.static(uploadsDir));
const imageCache = new Map();   // fallback when no DATABASE_URL

const friendsMap = new Map([
  ['id1', 'id2'],
  ['id2', 'id1']
]);

// DB-backed transfer state so a server restart (pm2, deploy) can't lose a
// grabbed image between grab and drop.
async function setTransfer(userId, imagePath) {
  if (!pool) { imageCache.set(userId, imagePath); return; }
  await ensureTables();
  await pool.query(
    `INSERT INTO dusk_transfers (user_id, image_path, updated_at)
     VALUES ($1, $2, now())
     ON CONFLICT (user_id) DO UPDATE
       SET image_path = $2, updated_at = now()`,
    [userId, imagePath]);
}

async function takeTransfer(userId) {
  if (!pool) {
    const p = imageCache.get(userId);
    imageCache.delete(userId);
    return p || null;
  }
  await ensureTables();
  const { rows } = await pool.query(
    "DELETE FROM dusk_transfers WHERE user_id = $1 RETURNING image_path",
    [userId]);
  return rows[0]?.image_path || null;
}


//-------------MULTER CONFIGS--------------
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, uploadsDir)
  },
  filename: (req, file, cb) => {
    const uniqueString = Math.random().toString(36).substring(7);
    const timestamp = Date.now();
    const ext = path.extname(file.originalname);
    const name = path.basename(file.originalname, ext);

    cb(null, `image-${name}-${timestamp}-${uniqueString}${ext}`);
  }
});

const upload = multer({ storage });


app.post('/upload', upload.single('image'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({
        success: false,
        message: "No file uploaded"
      });
    }

    const userId = req.body.userId;
    const imagePath = `/uploads/${req.file.filename}`;

    await setTransfer(userId, imagePath);

    res.json({
      success: true,
      message: "Image uploaded successfully",
      imagePath
    })

  } catch (error) {
    console.error("Upload error: ", error);
    res.status(500).json({
      success: false,
      message: "Upload failed",
    })
  }
});


app.get('/drop/:receiverId', async (req, res) => {
  try {
    const receiverId = req.params.receiverId;
    const senderId = friendsMap.get(receiverId);

    if (!senderId) {
      return res.json({
        success: false,
        message: "No friend mapping found",
      });
    }

    const imagePath = await takeTransfer(senderId);

    if (!imagePath) {
      return res.json({
        success: false,
        message: "No image available from your friend",
      })
    }

    res.json({
      success: true,
      imagePath,
      message: "Image received"
    })

  } catch (error) {
    console.error(error);
    res.status(500).json({
      success: false,
      message: "Drop failed",
    })
  }
})


//-------------METRICS LOGGING (Neon Postgres)--------------
// The Dusk app batches wake/commit/camera events here for the thesis
// measurements. Table is created on first use; everything beyond the
// indexed columns lands in the jsonb blob.

const pool = process.env.DATABASE_URL
  ? new pg.Pool({ connectionString: process.env.DATABASE_URL })
  : null;

let tablesReady = false;
async function ensureTables() {
  if (tablesReady || !pool) return;
  await pool.query(`
    CREATE TABLE IF NOT EXISTS dusk_logs (
      id      SERIAL PRIMARY KEY,
      ts      TIMESTAMPTZ NOT NULL,
      device  TEXT,
      mode    TEXT,
      event   TEXT NOT NULL,
      battery INT,
      data    JSONB
    )`);
  await pool.query(`
    CREATE TABLE IF NOT EXISTS dusk_transfers (
      user_id    TEXT PRIMARY KEY,
      image_path TEXT NOT NULL,
      updated_at TIMESTAMPTZ DEFAULT now()
    )`);
  tablesReady = true;
}

app.post('/log', async (req, res) => {
  try {
    if (!pool) return res.status(503).json({ success: false, message: "no DATABASE_URL" });
    await ensureTables();

    const { device, events } = req.body;
    if (!Array.isArray(events) || !events.length) {
      return res.status(400).json({ success: false, message: "events[] required" });
    }
    for (const e of events.slice(0, 500)) {
      const { ts, event, mode, battery, ...rest } = e;
      await pool.query(
        `INSERT INTO dusk_logs (ts, device, mode, event, battery, data)
         VALUES ($1, $2, $3, $4, $5, $6)`,
        [ts || new Date().toISOString(), device || null, mode || null,
         event || "unknown", Number.isFinite(battery) ? battery : null, rest]
      );
    }
    res.json({ success: true, stored: events.length });
  } catch (error) {
    console.error("Log error: ", error);
    res.status(500).json({ success: false, message: "log failed" });
  }
});

app.get('/logs.csv', async (req, res) => {
  try {
    if (!pool) return res.status(503).send("no DATABASE_URL");
    await ensureTables();
    const { rows } = await pool.query(
      "SELECT id, ts, device, mode, event, battery, data FROM dusk_logs ORDER BY ts");
    const esc = (v) => v === null || v === undefined
      ? "" : String(typeof v === "object" ? JSON.stringify(v) : v).replace(/,/g, ";");
    const csv = ["id,ts,device,mode,event,battery,data"]
      .concat(rows.map(r => [r.id, r.ts.toISOString(), r.device, r.mode,
                             r.event, r.battery, r.data].map(esc).join(",")))
      .join("\n");
    res.type("text/csv").send(csv);
  } catch (error) {
    console.error(error);
    res.status(500).send("export failed");
  }
});

app.get('/health', (req, res) => {
  res.json({
    status: "OK",
    db: !!pool,
  });
});

app.listen(PORT, () => {
  console.log(`Server is running on http://localhost:${PORT}`)
});