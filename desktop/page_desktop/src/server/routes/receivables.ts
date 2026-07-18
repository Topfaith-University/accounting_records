import crypto from 'crypto';
import { Router } from 'express';
import { Kysely } from 'kysely';
import { Database } from '../db/types';
import { requireAuth } from '../middleware/auth';
import { requireActiveCompany, requireLegacyGroup } from '../middleware/legacyRbac';
import { getActiveCompanyId, getActiveCompanyName } from '../lib/rbac';
import { nextInvoiceNumber } from '../services/payables.service';
import { postSalesInvoice, recordArReceipt, ServiceError, voidSalesInvoice, getCustomerStatement } from '../services/receivables.service';
import { sendXlsx } from '../exports/xlsx';
import { sendTablePdf, sendPdf, titleBlock, ledgerTable, doubleRule, summaryLine, money, today } from '../exports/pdf';

async function serializeCustomer(db: Kysely<Database>, c: any) {
  const invoices = await db.selectFrom('sales_invoices').select(['total_amount', 'amount_received']).where('customer_id', '=', c.customer_id).where('status', 'in', ['POSTED', 'PAID']).execute();
  const balance = Math.round(invoices.reduce((s, i) => s + Math.max(0, i.total_amount - i.amount_received), 0) * 100) / 100;
  return {
    customer_id: c.customer_id,
    name: c.name,
    email: c.email,
    phone: c.phone,
    address: c.address,
    customer_type: c.customer_type,
    is_active: !!c.is_active,
    created_at: c.created_at,
    balance,
  };
}

async function serializeInvoice(db: Kysely<Database>, inv: any) {
  const lines = await db
    .selectFrom('sales_invoice_lines')
    .innerJoin('accounts', 'accounts.account_id', 'sales_invoice_lines.revenue_account_id')
    .where('invoice_id', '=', inv.invoice_id)
    .select([
      'sales_invoice_lines.line_id as line_id',
      'sales_invoice_lines.description as description',
      'sales_invoice_lines.quantity as quantity',
      'sales_invoice_lines.unit_price as unit_price',
      'sales_invoice_lines.amount as amount',
      'accounts.account_id as revenue_account_id',
      'accounts.code as revenue_account_code',
      'accounts.name as revenue_account_name',
    ])
    .execute();
  const arAccount = await db.selectFrom('accounts').select(['code', 'name']).where('account_id', '=', inv.ar_account_id).executeTakeFirst();
  return {
    invoice_id: inv.invoice_id,
    invoice_number: inv.invoice_number,
    date: inv.date,
    due_date: inv.due_date,
    description: inv.description,
    status: inv.status,
    total_amount: inv.total_amount,
    amount_received: inv.amount_received,
    created_by: inv.created_by,
    created_at: inv.created_at,
    customer_id: inv.customer_id,
    ar_account_id: inv.ar_account_id,
    customer_name: (await db.selectFrom('customers').select('name').where('customer_id', '=', inv.customer_id).executeTakeFirst())?.name ?? null,
    ar_account_label: arAccount ? `${arAccount.code} — ${arAccount.name}` : null,
    lines,
  };
}

export function receivablesRouter(db: Kysely<Database>): Router {
  const customers = Router();
  customers.use(requireAuth);

  customers.get('/', requireActiveCompany, async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const rows = await db.selectFrom('customers').selectAll().where('company_id', '=', companyId).where('is_active', '=', 1).execute();
    res.json(await Promise.all(rows.map((r) => serializeCustomer(db, r))));
  });

  customers.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
    const rows = await db.selectFrom('customers').selectAll().where('company_id', '=', companyId ?? '').where('is_active', '=', 1).orderBy('name').execute();
    const headers = ['Name', 'Type', 'Email', 'Phone'];
    const dataRows = rows.map((c) => [c.name, c.customer_type, c.email, c.phone]);
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'customers', 'Customers', headers, dataRows, companyName);
      return;
    }
    await sendXlsx(res, 'customers', 'Customers', headers, dataRows, companyName);
  });

  customers.get('/:id/statement/', async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const companyName = getActiveCompanyName(req);
    const data = await getCustomerStatement(db, req.params.id, companyId);
    if (!data) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const fmt = (req.query.format as string) || 'json';
    if (fmt === 'pdf') {
      sendPdf(res, `customer-statement-${req.params.id}`, {
        content: [
          ...titleBlock('Customer Statement', `${data.entity_name} · Generated ${today()}`),
          ledgerTable(
            ['Date', 'Type', 'Reference', 'Description', 'Debit', 'Credit', 'Running Balance'],
            data.lines.map((l) => [
              { text: l.date, fontSize: 9 },
              { text: l.type, fontSize: 9 },
              { text: l.reference, fontSize: 9 },
              { text: l.description, fontSize: 9 },
              { text: l.debit ? money(l.debit) : '', fontSize: 9, alignment: 'right' },
              { text: l.credit ? money(l.credit) : '', fontSize: 9, alignment: 'right' },
              { text: money(l.running_balance), fontSize: 9, alignment: 'right' },
            ]),
            { widths: ['auto', 'auto', 'auto', '*', 'auto', 'auto', 'auto'] },
          ),
          doubleRule(),
          summaryLine('Closing Balance', money(data.closing_balance)),
        ],
      }, companyName, `Customer Statement — ${data.entity_name}`);
      return;
    }
    if (fmt === 'xlsx') {
      const headers = ['Date', 'Type', 'Reference', 'Description', 'Debit (N)', 'Credit (N)', 'Running Balance (N)'];
      const dataRows: any[][] = data.lines.map((l) => [l.date, l.type, l.reference, l.description, l.debit, l.credit, l.running_balance]);
      dataRows.push(['', '', '', '', '', 'CLOSING BALANCE', data.closing_balance]);
      await sendXlsx(res, `customer-statement-${req.params.id}`, 'Statement', headers, dataRows, companyName);
      return;
    }
    res.json(data);
  });

  customers.get('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const customer = await db.selectFrom('customers').selectAll().where('customer_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!customer) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    res.json(await serializeCustomer(db, customer));
  });

  customers.post('/', requireActiveCompany, async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const body = req.body ?? {};
    if (!body.name) {
      res.status(400).json({ name: ['This field is required.'] });
      return;
    }
    const customerId = crypto.randomUUID();
    await db
      .insertInto('customers')
      .values({
        customer_id: customerId,
        company_id: companyId,
        name: body.name,
        email: body.email ?? '',
        phone: body.phone ?? '',
        address: body.address ?? '',
        customer_type: body.customer_type ?? 'EXTERNAL',
        is_active: 1,
      })
      .execute();
    const customer = await db.selectFrom('customers').selectAll().where('customer_id', '=', customerId).executeTakeFirstOrThrow();
    res.status(201).json(await serializeCustomer(db, customer));
  });

  customers.patch('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const customer = await db.selectFrom('customers').selectAll().where('customer_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!customer) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const body = { ...(req.body ?? {}) };
    delete body.customer_id;
    delete body.created_at;
    delete body.balance;
    if ('is_active' in body) body.is_active = body.is_active ? 1 : 0;
    await db.updateTable('customers').set(body).where('customer_id', '=', req.params.id).execute();
    const updated = await db.selectFrom('customers').selectAll().where('customer_id', '=', req.params.id).executeTakeFirstOrThrow();
    res.json(await serializeCustomer(db, updated));
  });

  customers.delete('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const customer = await db.selectFrom('customers').select('customer_id').where('customer_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!customer) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    await db.updateTable('customers').set({ is_active: 0 }).where('customer_id', '=', req.params.id).execute();
    res.status(204).send();
  });

  const invoices = Router();
  invoices.use(requireAuth);

  invoices.get('/', requireActiveCompany, async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    let query = db.selectFrom('sales_invoices').selectAll().where('company_id', '=', companyId);
    const invStatus = req.query.status as string | undefined;
    const customerId = req.query.customer_id as string | undefined;
    if (invStatus) query = query.where('status', '=', invStatus.toUpperCase() as any);
    if (customerId) query = query.where('customer_id', '=', customerId);
    const rows = await query.orderBy('date', 'desc').execute();
    res.json(await Promise.all(rows.map((r) => serializeInvoice(db, r))));
  });

  invoices.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
    const rows = await db.selectFrom('sales_invoices').selectAll().where('company_id', '=', companyId ?? '').orderBy('date', 'desc').execute();
    const dataRows = await Promise.all(
      rows.map(async (inv) => {
        const customer = await db.selectFrom('customers').select('name').where('customer_id', '=', inv.customer_id).executeTakeFirst();
        return [inv.invoice_number, customer?.name ?? '', inv.date, inv.due_date, inv.total_amount, inv.amount_received, inv.status];
      }),
    );
    const headers = ['Invoice #', 'Customer', 'Date', 'Due Date', 'Total (N)', 'Received (N)', 'Status'];
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'sales-invoices', 'Sales Invoices', headers, dataRows, companyName);
      return;
    }
    await sendXlsx(res, 'sales-invoices', 'Sales Invoices', headers, dataRows, companyName);
  });

  invoices.get('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const invoice = await db.selectFrom('sales_invoices').selectAll().where('invoice_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!invoice) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    res.json(await serializeInvoice(db, invoice));
  });

  invoices.get('/:id/print/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
    const invoice = await db.selectFrom('sales_invoices').selectAll().where('invoice_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!invoice) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const data = await serializeInvoice(db, invoice);
    const outstanding = Math.max(0, invoice.total_amount - invoice.amount_received);
    sendPdf(res, `sales-invoice-${invoice.invoice_number}`, {
      content: [
        ...titleBlock(`Sales Invoice ${invoice.invoice_number}`, `${invoice.status} · Date ${invoice.date} · Due ${invoice.due_date}`),
        { text: 'CUSTOMER', style: 'sectionHeader', margin: [0, 0, 0, 2] },
        { text: data.customer_name ?? '', bold: true, fontSize: 10, margin: [0, 0, 0, 14] },
        ledgerTable(
          ['Description', 'Qty', 'Unit Price', 'Amount'],
          data.lines.map((l: any) => [
            { text: l.description, fontSize: 9 },
            { text: String(l.quantity), fontSize: 9, alignment: 'right' },
            { text: money(l.unit_price), fontSize: 9, alignment: 'right' },
            { text: money(l.amount), fontSize: 9, alignment: 'right' },
          ]),
          { widths: ['*', 'auto', 'auto', 'auto'] },
        ),
        { text: '', margin: [0, 12, 0, 0] },
        summaryLine('Total', money(invoice.total_amount)),
        summaryLine('Received', money(invoice.amount_received), { bold: false }),
        doubleRule(),
        summaryLine('Outstanding', money(outstanding), { tone: outstanding > 0 ? 'negative' : 'positive' }),
      ],
    }, companyName, `Sales Invoice ${invoice.invoice_number}`);
  });

  invoices.post('/', requireActiveCompany, async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const body = req.body ?? {};
    const lines = body.lines ?? [];
    if (lines.length < 1) {
      res.status(400).json({ lines: 'At least one line is required.' });
      return;
    }
    if (!body.date || !body.due_date || !body.customer_id || !body.ar_account_id) {
      res.status(400).json({ detail: 'date, due_date, customer_id, ar_account_id are required.' });
      return;
    }
    const invoiceId = crypto.randomUUID();
    const invoiceNumber = body.invoice_number || (await nextInvoiceNumber(db, 'SI', 'sales_invoices', companyId));
    const total = lines.reduce((s: number, l: any) => s + l.amount, 0);
    await db
      .insertInto('sales_invoices')
      .values({
        invoice_id: invoiceId,
        company_id: companyId,
        invoice_number: invoiceNumber,
        date: body.date,
        due_date: body.due_date,
        description: body.description ?? '',
        status: 'DRAFT',
        total_amount: total,
        amount_received: 0,
        customer_id: body.customer_id,
        ar_account_id: body.ar_account_id,
        journal_entry_id: null,
        created_by: req.auth!.username,
      })
      .execute();
    for (const line of lines) {
      await db
        .insertInto('sales_invoice_lines')
        .values({
          line_id: crypto.randomUUID(),
          company_id: companyId,
          invoice_id: invoiceId,
          description: line.description ?? '',
          quantity: line.quantity ?? 1,
          unit_price: line.unit_price ?? 0,
          amount: line.amount,
          revenue_account_id: line.revenue_account_id,
        })
        .execute();
    }
    const invoice = await db.selectFrom('sales_invoices').selectAll().where('invoice_id', '=', invoiceId).executeTakeFirstOrThrow();
    res.status(201).json(await serializeInvoice(db, invoice));
  });

  invoices.patch('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const invoice = await db.selectFrom('sales_invoices').selectAll().where('invoice_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!invoice) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    if (invoice.status !== 'DRAFT') {
      res.status(400).json({ detail: 'Only draft invoices can be edited.' });
      return;
    }
    const body = req.body ?? {};
    const patch: any = {};
    if (body.date) patch.date = body.date;
    if (body.due_date) patch.due_date = body.due_date;
    if (body.description !== undefined) patch.description = body.description;
    if (body.customer_id) patch.customer_id = body.customer_id;
    if (body.ar_account_id) patch.ar_account_id = body.ar_account_id;
    if (body.lines) {
      await db.deleteFrom('sales_invoice_lines').where('invoice_id', '=', invoice.invoice_id).execute();
      for (const line of body.lines) {
        await db
          .insertInto('sales_invoice_lines')
          .values({
            line_id: crypto.randomUUID(),
            company_id: companyId!,
            invoice_id: invoice.invoice_id,
            description: line.description ?? '',
            quantity: line.quantity ?? 1,
            unit_price: line.unit_price ?? 0,
            amount: line.amount,
            revenue_account_id: line.revenue_account_id,
          })
          .execute();
      }
      patch.total_amount = body.lines.reduce((s: number, l: any) => s + l.amount, 0);
    }
    await db.updateTable('sales_invoices').set(patch).where('invoice_id', '=', invoice.invoice_id).execute();
    const updated = await db.selectFrom('sales_invoices').selectAll().where('invoice_id', '=', invoice.invoice_id).executeTakeFirstOrThrow();
    res.json(await serializeInvoice(db, updated));
  });

  invoices.delete('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const invoice = await db.selectFrom('sales_invoices').selectAll().where('invoice_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!invoice) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    if (invoice.status !== 'DRAFT') {
      res.status(400).json({ detail: 'Only draft invoices can be deleted.' });
      return;
    }
    await db.deleteFrom('sales_invoice_lines').where('invoice_id', '=', invoice.invoice_id).execute();
    await db.deleteFrom('sales_invoices').where('invoice_id', '=', invoice.invoice_id).execute();
    res.status(204).send();
  });

  invoices.post('/:id/post/', requireLegacyGroup(db, ['Manager', 'Admin']), async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    try {
      await postSalesInvoice(db, req.params.id, companyId, req.auth!.username);
    } catch (e) {
      res.status(400).json({ detail: e instanceof ServiceError ? e.message : 'Unexpected error.' });
      return;
    }
    const invoice = await db.selectFrom('sales_invoices').selectAll().where('invoice_id', '=', req.params.id).executeTakeFirstOrThrow();
    res.json(await serializeInvoice(db, invoice));
  });

  invoices.post('/:id/void/', requireLegacyGroup(db, ['Manager', 'Admin']), async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    try {
      await voidSalesInvoice(db, req.params.id, companyId, req.auth!.username);
    } catch (e) {
      res.status(400).json({ detail: e instanceof ServiceError ? e.message : 'Unexpected error.' });
      return;
    }
    const invoice = await db.selectFrom('sales_invoices').selectAll().where('invoice_id', '=', req.params.id).executeTakeFirstOrThrow();
    res.json(await serializeInvoice(db, invoice));
  });

  invoices.post('/:id/receive/', async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const { receipt_date, amount, bank_account_id } = req.body ?? {};
    if (!receipt_date || amount === undefined || !bank_account_id) {
      res.status(400).json({ detail: 'receipt_date, amount, and bank_account_id are required.' });
      return;
    }
    const amt = Number(amount);
    if (Number.isNaN(amt)) {
      res.status(400).json({ detail: 'amount must be a valid number.' });
      return;
    }
    try {
      const receiptId = await recordArReceipt(db, req.params.id, companyId, receipt_date, amt, req.body.reference ?? '', bank_account_id, req.auth!.username);
      const receipt = await db.selectFrom('ar_receipts').selectAll().where('receipt_id', '=', receiptId).executeTakeFirstOrThrow();
      res.status(201).json({
        receipt_id: receipt.receipt_id,
        receipt_date: receipt.receipt_date,
        amount: receipt.amount,
        reference: receipt.reference,
        created_by: receipt.created_by,
        created_at: receipt.created_at,
        invoice_id: receipt.invoice_id,
      });
    } catch (e) {
      res.status(400).json({ detail: e instanceof ServiceError ? e.message : 'Unexpected error.' });
    }
  });

  return Router().use('/customers', customers).use('/invoices', invoices);
}
