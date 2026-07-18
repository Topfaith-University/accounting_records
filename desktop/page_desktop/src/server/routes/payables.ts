import crypto from 'crypto';
import { Router } from 'express';
import { Kysely } from 'kysely';
import { Database } from '../db/types';
import { requireAuth } from '../middleware/auth';
import { requireActiveCompany, requireLegacyGroup } from '../middleware/legacyRbac';
import { getActiveCompanyId, getActiveCompanyName } from '../lib/rbac';
import { nextInvoiceNumber, postPurchaseInvoice, recordApPayment, ServiceError, voidPurchaseInvoice, getVendorStatement } from '../services/payables.service';
import { sendXlsx } from '../exports/xlsx';
import { sendTablePdf, sendPdf, titleBlock, ledgerTable, doubleRule, summaryLine, money, today } from '../exports/pdf';

async function serializeVendor(db: Kysely<Database>, v: any) {
  const invoices = await db.selectFrom('purchase_invoices').select(['total_amount', 'amount_paid']).where('vendor_id', '=', v.vendor_id).where('status', 'in', ['POSTED', 'PAID']).execute();
  const balance = Math.round(invoices.reduce((s, i) => s + Math.max(0, i.total_amount - i.amount_paid), 0) * 100) / 100;
  return {
    vendor_id: v.vendor_id,
    name: v.name,
    email: v.email,
    phone: v.phone,
    address: v.address,
    is_active: !!v.is_active,
    created_at: v.created_at,
    balance,
  };
}

async function serializeItem(item: any) {
  return {
    item_id: item.item_id,
    name: item.name,
    description: item.description,
    cost_price: item.cost_price,
    selling_price: item.selling_price,
    item_type: item.item_type,
    is_active: !!item.is_active,
    created_at: item.created_at,
    vendor_id: item.vendor_id,
    expense_account_id: item.expense_account_id,
    revenue_account_id: item.revenue_account_id,
  };
}

async function serializeInvoice(db: Kysely<Database>, inv: any) {
  const lines = await db
    .selectFrom('purchase_invoice_lines')
    .innerJoin('accounts', 'accounts.account_id', 'purchase_invoice_lines.expense_account_id')
    .where('invoice_id', '=', inv.invoice_id)
    .select([
      'purchase_invoice_lines.line_id as line_id',
      'purchase_invoice_lines.description as description',
      'purchase_invoice_lines.quantity as quantity',
      'purchase_invoice_lines.unit_price as unit_price',
      'purchase_invoice_lines.amount as amount',
      'accounts.account_id as expense_account_id',
      'accounts.code as expense_account_code',
      'accounts.name as expense_account_name',
    ])
    .execute();
  const apAccount = await db.selectFrom('accounts').select(['code', 'name']).where('account_id', '=', inv.ap_account_id).executeTakeFirst();
  return {
    invoice_id: inv.invoice_id,
    invoice_number: inv.invoice_number,
    date: inv.date,
    due_date: inv.due_date,
    description: inv.description,
    status: inv.status,
    total_amount: inv.total_amount,
    amount_paid: inv.amount_paid,
    created_by: inv.created_by,
    created_at: inv.created_at,
    vendor_id: inv.vendor_id,
    ap_account_id: inv.ap_account_id,
    vendor_name: (await db.selectFrom('vendors').select('name').where('vendor_id', '=', inv.vendor_id).executeTakeFirst())?.name ?? null,
    ap_account_label: apAccount ? `${apAccount.code} — ${apAccount.name}` : null,
    lines,
  };
}

export function payablesRouter(db: Kysely<Database>): Router {
  const vendors = Router();
  vendors.use(requireAuth);

  vendors.get('/', requireActiveCompany, async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const rows = await db.selectFrom('vendors').selectAll().where('company_id', '=', companyId).where('is_active', '=', 1).execute();
    res.json(await Promise.all(rows.map((r) => serializeVendor(db, r))));
  });

  vendors.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
    const rows = await db.selectFrom('vendors').selectAll().where('company_id', '=', companyId ?? '').where('is_active', '=', 1).orderBy('name').execute();
    const headers = ['Name', 'Email', 'Phone', 'Address'];
    const dataRows = rows.map((v) => [v.name, v.email, v.phone, v.address]);
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'vendors', 'Vendors', headers, dataRows, companyName);
      return;
    }
    await sendXlsx(res, 'vendors', 'Vendors', headers, dataRows, companyName);
  });

  vendors.get('/:id/statement/', async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const companyName = getActiveCompanyName(req);
    const data = await getVendorStatement(db, req.params.id, companyId);
    if (!data) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const fmt = (req.query.format as string) || 'json';
    if (fmt === 'pdf') {
      sendPdf(res, `vendor-statement-${req.params.id}`, {
        content: [
          ...titleBlock('Vendor Statement', `${data.entity_name} · Generated ${today()}`),
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
      }, companyName, `Vendor Statement — ${data.entity_name}`);
      return;
    }
    if (fmt === 'xlsx') {
      const headers = ['Date', 'Type', 'Reference', 'Description', 'Debit (N)', 'Credit (N)', 'Running Balance (N)'];
      const dataRows: any[][] = data.lines.map((l) => [l.date, l.type, l.reference, l.description, l.debit, l.credit, l.running_balance]);
      dataRows.push(['', '', '', '', '', 'CLOSING BALANCE', data.closing_balance]);
      await sendXlsx(res, `vendor-statement-${req.params.id}`, 'Statement', headers, dataRows, companyName);
      return;
    }
    res.json(data);
  });

  vendors.get('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const vendor = await db.selectFrom('vendors').selectAll().where('vendor_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!vendor) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    res.json(await serializeVendor(db, vendor));
  });

  vendors.post('/', requireActiveCompany, async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const body = req.body ?? {};
    if (!body.name) {
      res.status(400).json({ name: ['This field is required.'] });
      return;
    }
    const vendorId = crypto.randomUUID();
    await db
      .insertInto('vendors')
      .values({ vendor_id: vendorId, company_id: companyId, name: body.name, email: body.email ?? '', phone: body.phone ?? '', address: body.address ?? '', is_active: 1 })
      .execute();
    const vendor = await db.selectFrom('vendors').selectAll().where('vendor_id', '=', vendorId).executeTakeFirstOrThrow();
    res.status(201).json(await serializeVendor(db, vendor));
  });

  vendors.patch('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const vendor = await db.selectFrom('vendors').selectAll().where('vendor_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!vendor) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const body = { ...(req.body ?? {}) };
    delete body.vendor_id;
    delete body.created_at;
    delete body.balance;
    if ('is_active' in body) body.is_active = body.is_active ? 1 : 0;
    await db.updateTable('vendors').set(body).where('vendor_id', '=', req.params.id).execute();
    const updated = await db.selectFrom('vendors').selectAll().where('vendor_id', '=', req.params.id).executeTakeFirstOrThrow();
    res.json(await serializeVendor(db, updated));
  });

  vendors.delete('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const vendor = await db.selectFrom('vendors').select('vendor_id').where('vendor_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!vendor) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    await db.updateTable('vendors').set({ is_active: 0 }).where('vendor_id', '=', req.params.id).execute();
    res.status(204).send();
  });

  const invoices = Router();
  invoices.use(requireAuth);

  invoices.get('/', requireActiveCompany, async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    let query = db.selectFrom('purchase_invoices').selectAll().where('company_id', '=', companyId);
    const invStatus = req.query.status as string | undefined;
    const vendorId = req.query.vendor_id as string | undefined;
    if (invStatus) query = query.where('status', '=', invStatus.toUpperCase() as any);
    if (vendorId) query = query.where('vendor_id', '=', vendorId);
    const rows = await query.orderBy('date', 'desc').execute();
    res.json(await Promise.all(rows.map((r) => serializeInvoice(db, r))));
  });

  invoices.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
    const rows = await db.selectFrom('purchase_invoices').selectAll().where('company_id', '=', companyId ?? '').orderBy('date', 'desc').execute();
    const dataRows = await Promise.all(
      rows.map(async (inv) => {
        const vendor = await db.selectFrom('vendors').select('name').where('vendor_id', '=', inv.vendor_id).executeTakeFirst();
        return [inv.invoice_number, vendor?.name ?? '', inv.date, inv.due_date, inv.total_amount, inv.amount_paid, inv.status];
      }),
    );
    const headers = ['Invoice #', 'Vendor', 'Date', 'Due Date', 'Total (N)', 'Paid (N)', 'Status'];
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'purchase-invoices', 'Purchase Invoices', headers, dataRows, companyName);
      return;
    }
    await sendXlsx(res, 'purchase-invoices', 'Purchase Invoices', headers, dataRows, companyName);
  });

  invoices.get('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const invoice = await db.selectFrom('purchase_invoices').selectAll().where('invoice_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!invoice) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    res.json(await serializeInvoice(db, invoice));
  });

  invoices.get('/:id/print/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
    const invoice = await db.selectFrom('purchase_invoices').selectAll().where('invoice_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!invoice) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const data = await serializeInvoice(db, invoice);
    const outstanding = Math.max(0, invoice.total_amount - invoice.amount_paid);
    sendPdf(res, `purchase-invoice-${invoice.invoice_number}`, {
      content: [
        ...titleBlock(`Purchase Invoice ${invoice.invoice_number}`, `${invoice.status} · Date ${invoice.date} · Due ${invoice.due_date}`),
        { text: 'VENDOR', style: 'sectionHeader', margin: [0, 0, 0, 2] },
        { text: data.vendor_name ?? '', bold: true, fontSize: 10, margin: [0, 0, 0, 14] },
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
        summaryLine('Paid', money(invoice.amount_paid), { bold: false }),
        doubleRule(),
        summaryLine('Outstanding', money(outstanding), { tone: outstanding > 0 ? 'negative' : 'positive' }),
      ],
    }, companyName, `Purchase Invoice ${invoice.invoice_number}`);
  });

  invoices.post('/', requireActiveCompany, async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const body = req.body ?? {};
    const lines = body.lines ?? [];
    if (lines.length < 1) {
      res.status(400).json({ lines: 'At least one line is required.' });
      return;
    }
    if (!body.date || !body.due_date || !body.vendor_id || !body.ap_account_id) {
      res.status(400).json({ detail: 'date, due_date, vendor_id, ap_account_id are required.' });
      return;
    }
    const invoiceId = crypto.randomUUID();
    const invoiceNumber = body.invoice_number || (await nextInvoiceNumber(db, 'PI', 'purchase_invoices', companyId));
    const total = lines.reduce((s: number, l: any) => s + l.amount, 0);
    await db
      .insertInto('purchase_invoices')
      .values({
        invoice_id: invoiceId,
        company_id: companyId,
        invoice_number: invoiceNumber,
        date: body.date,
        due_date: body.due_date,
        description: body.description ?? '',
        status: 'DRAFT',
        total_amount: total,
        amount_paid: 0,
        vendor_id: body.vendor_id,
        ap_account_id: body.ap_account_id,
        journal_entry_id: null,
        created_by: req.auth!.username,
      })
      .execute();
    for (const line of lines) {
      await db
        .insertInto('purchase_invoice_lines')
        .values({
          line_id: crypto.randomUUID(),
          company_id: companyId,
          invoice_id: invoiceId,
          description: line.description ?? '',
          quantity: line.quantity ?? 1,
          unit_price: line.unit_price ?? 0,
          amount: line.amount,
          expense_account_id: line.expense_account_id,
        })
        .execute();
    }
    const invoice = await db.selectFrom('purchase_invoices').selectAll().where('invoice_id', '=', invoiceId).executeTakeFirstOrThrow();
    res.status(201).json(await serializeInvoice(db, invoice));
  });

  invoices.patch('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const invoice = await db.selectFrom('purchase_invoices').selectAll().where('invoice_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
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
    if (body.vendor_id) patch.vendor_id = body.vendor_id;
    if (body.ap_account_id) patch.ap_account_id = body.ap_account_id;
    if (body.lines) {
      await db.deleteFrom('purchase_invoice_lines').where('invoice_id', '=', invoice.invoice_id).execute();
      for (const line of body.lines) {
        await db
          .insertInto('purchase_invoice_lines')
          .values({
            line_id: crypto.randomUUID(),
            company_id: companyId!,
            invoice_id: invoice.invoice_id,
            description: line.description ?? '',
            quantity: line.quantity ?? 1,
            unit_price: line.unit_price ?? 0,
            amount: line.amount,
            expense_account_id: line.expense_account_id,
          })
          .execute();
      }
      patch.total_amount = body.lines.reduce((s: number, l: any) => s + l.amount, 0);
    }
    await db.updateTable('purchase_invoices').set(patch).where('invoice_id', '=', invoice.invoice_id).execute();
    const updated = await db.selectFrom('purchase_invoices').selectAll().where('invoice_id', '=', invoice.invoice_id).executeTakeFirstOrThrow();
    res.json(await serializeInvoice(db, updated));
  });

  invoices.delete('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const invoice = await db.selectFrom('purchase_invoices').selectAll().where('invoice_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!invoice) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    if (invoice.status !== 'DRAFT') {
      res.status(400).json({ detail: 'Only draft invoices can be deleted.' });
      return;
    }
    await db.deleteFrom('purchase_invoice_lines').where('invoice_id', '=', invoice.invoice_id).execute();
    await db.deleteFrom('purchase_invoices').where('invoice_id', '=', invoice.invoice_id).execute();
    res.status(204).send();
  });

  invoices.post('/:id/post/', requireLegacyGroup(db, ['Manager', 'Admin']), async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    try {
      await postPurchaseInvoice(db, req.params.id, companyId, req.auth!.username);
    } catch (e) {
      res.status(400).json({ detail: e instanceof ServiceError ? e.message : 'Unexpected error.' });
      return;
    }
    const invoice = await db.selectFrom('purchase_invoices').selectAll().where('invoice_id', '=', req.params.id).executeTakeFirstOrThrow();
    res.json(await serializeInvoice(db, invoice));
  });

  invoices.post('/:id/void/', requireLegacyGroup(db, ['Manager', 'Admin']), async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    try {
      await voidPurchaseInvoice(db, req.params.id, companyId, req.auth!.username);
    } catch (e) {
      res.status(400).json({ detail: e instanceof ServiceError ? e.message : 'Unexpected error.' });
      return;
    }
    const invoice = await db.selectFrom('purchase_invoices').selectAll().where('invoice_id', '=', req.params.id).executeTakeFirstOrThrow();
    res.json(await serializeInvoice(db, invoice));
  });

  invoices.post('/:id/pay/', async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const { payment_date, amount, bank_account_id } = req.body ?? {};
    if (!payment_date || amount === undefined || !bank_account_id) {
      res.status(400).json({ detail: 'payment_date, amount, and bank_account_id are required.' });
      return;
    }
    const amt = Number(amount);
    if (Number.isNaN(amt)) {
      res.status(400).json({ detail: 'amount must be a valid number.' });
      return;
    }
    try {
      const paymentId = await recordApPayment(db, req.params.id, companyId, payment_date, amt, req.body.reference ?? '', bank_account_id, req.auth!.username);
      const payment = await db.selectFrom('ap_payments').selectAll().where('payment_id', '=', paymentId).executeTakeFirstOrThrow();
      res.status(201).json({
        payment_id: payment.payment_id,
        payment_date: payment.payment_date,
        amount: payment.amount,
        reference: payment.reference,
        created_by: payment.created_by,
        created_at: payment.created_at,
        invoice_id: payment.invoice_id,
      });
    } catch (e) {
      res.status(400).json({ detail: e instanceof ServiceError ? e.message : 'Unexpected error.' });
    }
  });

  const items = Router();
  items.use(requireAuth);

  items.get('/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const rows = await db.selectFrom('items').selectAll().where('company_id', '=', companyId ?? '').where('is_active', '=', 1).execute();
    res.json(await Promise.all(rows.map(serializeItem)));
  });

  items.get('/export/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const companyName = getActiveCompanyName(req);
    const rows = await db.selectFrom('items').selectAll().where('company_id', '=', companyId ?? '').where('is_active', '=', 1).orderBy('name').execute();
    const dataRows = await Promise.all(
      rows.map(async (i) => {
        const vendor = i.vendor_id ? await db.selectFrom('vendors').select('name').where('vendor_id', '=', i.vendor_id).executeTakeFirst() : null;
        return [i.name, i.item_type, vendor?.name ?? '', i.cost_price, i.selling_price];
      }),
    );
    const headers = ['Name', 'Type', 'Vendor', 'Cost Price (N)', 'Selling Price (N)'];
    const fmt = (req.query.format as string) || 'xlsx';
    if (fmt === 'pdf') {
      sendTablePdf(res, 'items', 'Items', headers, dataRows, companyName);
      return;
    }
    await sendXlsx(res, 'items', 'Items', headers, dataRows, companyName);
  });

  items.get('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const item = await db.selectFrom('items').selectAll().where('item_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!item) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    res.json(await serializeItem(item));
  });

  items.post('/', requireActiveCompany, async (req, res) => {
    const companyId = getActiveCompanyId(req)!;
    const body = req.body ?? {};
    if (!body.name) {
      res.status(400).json({ name: ['This field is required.'] });
      return;
    }
    const itemId = crypto.randomUUID();
    await db
      .insertInto('items')
      .values({
        item_id: itemId,
        company_id: companyId,
        name: body.name,
        description: body.description ?? '',
        cost_price: body.cost_price ?? 0,
        selling_price: body.selling_price ?? 0,
        item_type: body.item_type ?? 'SERVICE',
        vendor_id: body.vendor_id || null,
        expense_account_id: body.expense_account_id || null,
        revenue_account_id: body.revenue_account_id || null,
        is_active: 1,
      })
      .execute();
    const item = await db.selectFrom('items').selectAll().where('item_id', '=', itemId).executeTakeFirstOrThrow();
    res.status(201).json(await serializeItem(item));
  });

  items.patch('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const item = await db.selectFrom('items').selectAll().where('item_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!item) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    const body = { ...(req.body ?? {}) };
    delete body.item_id;
    delete body.created_at;
    if ('is_active' in body) body.is_active = body.is_active ? 1 : 0;
    if ('vendor_id' in body) body.vendor_id = body.vendor_id || null;
    if ('expense_account_id' in body) body.expense_account_id = body.expense_account_id || null;
    if ('revenue_account_id' in body) body.revenue_account_id = body.revenue_account_id || null;
    await db.updateTable('items').set(body).where('item_id', '=', req.params.id).execute();
    const updated = await db.selectFrom('items').selectAll().where('item_id', '=', req.params.id).executeTakeFirstOrThrow();
    res.json(await serializeItem(updated));
  });

  items.delete('/:id/', async (req, res) => {
    const companyId = getActiveCompanyId(req);
    const item = await db.selectFrom('items').select('item_id').where('item_id', '=', req.params.id).where('company_id', '=', companyId ?? '').executeTakeFirst();
    if (!item) {
      res.status(404).json({ detail: 'Not found.' });
      return;
    }
    await db.updateTable('items').set({ is_active: 0 }).where('item_id', '=', req.params.id).execute();
    res.status(204).send();
  });

  return Router().use('/vendors', vendors).use('/invoices', invoices).use('/items', items);
}
