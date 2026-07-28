import express, { Express } from 'express';
import path from 'path';
import fs from 'fs';
import { Kysely } from 'kysely';
import { Database } from './db/types';
import { authRouter } from './routes/auth';
import { usersRouter } from './routes/users';
import { accountsRouter } from './routes/accounts';
import { journalsRouter } from './routes/journals';
import { banksRouter } from './routes/banks';
import { payablesRouter } from './routes/payables';
import { receivablesRouter } from './routes/receivables';
import { budgetRouter } from './routes/budget';
import { reportsRouter } from './routes/reports';

export function createApp(db: Kysely<Database>, staticDir: string): Express {
  const app = express();
  app.use(express.json());

  app.use('/api/auth', authRouter(db));
  app.use('/api/users', usersRouter(db));
  app.use('/api/accounts', accountsRouter(db));
  app.use('/api/journals', journalsRouter(db));
  app.use('/api/banks', banksRouter(db));
  app.use('/api/payables', payablesRouter(db));
  app.use('/api/receivables', receivablesRouter(db));
  app.use('/api/budget', budgetRouter(db));
  app.use('/api/reports', reportsRouter(db));

  app.get('/api/health', (_req, res) => res.json({ status: 'ok' }));

  if (fs.existsSync(staticDir)) {
    app.use(express.static(staticDir));
    // Angular client-side routing: any non-API GET falls back to index.html.
    app.get(/^(?!\/api).*/, (_req, res) => {
      res.sendFile(path.join(staticDir, 'index.html'));
    });
  }

  app.use((err: any, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
    // eslint-disable-next-line no-console
    console.error(err);
    res.status(500).json({ detail: 'Internal server error.' });
  });

  return app;
}
