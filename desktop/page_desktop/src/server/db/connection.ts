import BetterSqlite3 from 'better-sqlite3';
import { Kysely, SqliteDialect } from 'kysely';
import { Database } from './types';
import { MIGRATIONS } from './schema';

let kysely: Kysely<Database> | null = null;

function runMigrations(raw: BetterSqlite3.Database) {
  raw.pragma('journal_mode = WAL');
  raw.pragma('foreign_keys = ON');
  raw.exec(`
    CREATE TABLE IF NOT EXISTS _migrations (
      name TEXT PRIMARY KEY,
      applied_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
  `);
  const applied = new Set(
    raw.prepare('SELECT name FROM _migrations').all().map((r: any) => r.name),
  );
  const insertMigration = raw.prepare('INSERT INTO _migrations (name) VALUES (?)');
  for (const migration of MIGRATIONS) {
    if (applied.has(migration.name)) continue;
    const apply = raw.transaction(() => {
      raw.exec(migration.sql);
      insertMigration.run(migration.name);
    });
    apply();
  }
}

/** Opens (creating if needed) the SQLite file at dbPath, runs any pending
 * migrations, and returns a typed Kysely instance. Call once at startup. */
export function initDb(dbPath: string): Kysely<Database> {
  const raw = new BetterSqlite3(dbPath);
  runMigrations(raw);
  kysely = new Kysely<Database>({ dialect: new SqliteDialect({ database: raw }) });
  return kysely;
}

export function getDb(): Kysely<Database> {
  if (!kysely) throw new Error('Database not initialized — call initDb() first.');
  return kysely;
}
