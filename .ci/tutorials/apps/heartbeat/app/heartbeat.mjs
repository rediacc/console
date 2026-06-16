import pg from "pg";

const { Pool } = pg;

const poolConfig = {
  host: process.env.DB_HOST || "db",
  port: parseInt(process.env.DB_PORT || "5432"),
  user: process.env.POSTGRES_USER || "heartbeat",
  password: process.env.PGPASSWORD,
  database: process.env.POSTGRES_DB || "heartbeat",
};

function createPool() {
  const p = new Pool(poolConfig);
  p.on("error", (err) => {
    console.error(`Pool error (will reconnect): ${err.message}`);
    replacePool();
  });
  return p;
}

let pool = createPool();

function replacePool() {
  const old = pool;
  pool = createPool();
  // End old pool asynchronously — ignore errors, it's already broken
  old.end().catch(() => {});
}

// Safety net: after CRIU restore, stale TCP sockets can emit errors on
// internal BoundPool instances that bypass the pool-level error handler.
// Without this, the process crashes with "unhandled 'error' event".
process.on("uncaughtException", (err) => {
  if (
    err.code === "ECONNRESET" ||
    err.message.includes("Connection terminated unexpectedly")
  ) {
    console.error(`Caught stale-connection error (recovering): ${err.message}`);
    replacePool();
    return;
  }
  // Re-throw truly unexpected errors
  console.error("Uncaught exception:", err);
  process.exit(1);
});

const intervalMs = parseInt(process.env.HEARTBEAT_INTERVAL_MS || "5000");

// In-memory counter — resets on container restart, proving statefulness
let counter = 0;

async function init() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS heartbeats (
      id SERIAL PRIMARY KEY,
      counter INTEGER NOT NULL,
      recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
  `);
  console.log("Heartbeat table ready");
}

async function beat() {
  counter++;
  try {
    const result = await pool.query(
      "INSERT INTO heartbeats (counter, recorded_at) VALUES ($1, NOW()) RETURNING id, counter, recorded_at",
      [counter]
    );
    const row = result.rows[0];
    console.log(`beat #${row.id} | memory counter=${row.counter} | at ${row.recorded_at}`);
  } catch (err) {
    console.error(`beat failed (counter=${counter}): ${err.message}`);
    // Recreate pool on connection error (CRIU restore invalidates TCP sockets)
    replacePool();
  }
}

async function main() {
  await init();
  console.log(`Heartbeat starting — interval ${intervalMs}ms`);
  setInterval(beat, intervalMs);
  // First beat immediately
  await beat();
}

main().catch((err) => {
  console.error("Fatal:", err);
  process.exit(1);
});
