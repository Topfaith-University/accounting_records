# Printable Invoice PDFs Design

## Goal

Allow authenticated users to download a stable, printable PDF for an individual sales invoice or purchase invoice.

## Scope

The feature covers individual invoice documents only. Existing invoice-list exports, payment and receipt flows, and invoice data models remain unchanged.

## Architecture

Each invoice viewset exposes an authenticated `GET` detail action at `invoices/<id>/print/`. The action loads the invoice and its relationships, derives document totals, and renders a dedicated Django template through the existing `config.export_utils.pdf_response` helper.

The Angular invoice-detail components invoke their respective service methods. The services request the PDF as a blob through the existing authenticated Axios configuration and initiate a download using the invoice number in the filename.

## Document Content

Both documents show the invoice number, status, issue date, due date, description when present, recipient (customer or vendor), line-item description, quantity, unit price, line amount, total, settled amount, and outstanding amount. Sales invoices use customer and amount-received terminology; purchase invoices use vendor and amount-paid terminology.

## Error Handling

The print actions return the established `404 Not found.` response for unknown invoice IDs. Existing authentication and Axios error interception apply to PDF requests. No invoice state is mutated while generating a document.

## Testing

Backend tests cover each print endpoint's successful PDF response, filename, content type, and missing-invoice response. The test fixtures mock PDF rendering and invoice relationships so they do not require a running Neo4j or WeasyPrint installation.

## Constraints

- Reuse Django, WeasyPrint, and `pdf_response`; add no dependency.
- Keep the existing API routes and list-export behavior intact.
- Do not modify existing user changes outside the files required by this feature.
