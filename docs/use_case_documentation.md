# Use Case: Invoice Processing Automation

## The problem

Right now, when an invoice comes in, someone on the accounts payable team has to open the PDF, find the invoice number, date, vendor, line items and totals, and type all of that into whatever system the company uses (SAP, DATEV, an ERP, sometimes just Excel). For a small company that's annoying. For a mid-size company getting a few hundred invoices a month, it's real hours every week, and it's exactly the kind of repetitive work where people make small typos - a wrong digit in a total, a swapped date format - that nobody notices until weeks later during reconciliation.

I built this pipeline to take that manual step out of the process: feed it a folder of invoice PDFs, and it gives you back structured, validated data, already flagging anything that looks off so a human only has to look at the invoices that actually need attention, not all of them.

## Who this is for

The accounts payable clerk or small finance team at a mid-size company. Not a huge enterprise with a dedicated SAP integration team, but a company that's still doing a meaningful chunk of this by hand and wants it automated without a massive IT project. Someone who currently opens each PDF, reads it, and retypes it.

## Input and output

**Input:** PDF invoices. I tested with German B2B invoices (the kind you'd get from a software vendor, an IT supplier, a hosting provider), since that's the most realistic case for a German-market client, but the pipeline doesn't assume anything specific to one vendor's layout.

**Output:** Each invoice becomes one structured record with:
- Invoice number, date, due date
- Vendor name, address, tax ID
- Customer name and address
- Every line item (description, quantity, unit price, line total)
- Subtotal, VAT rate, VAT amount, total
- A confidence score and a list of anything that looked questionable during extraction

This gets written into a small relational database (invoices + line items, linked), plus a status on every invoice - valid or needs_review - so someone can immediately filter down to just the handful that actually need a second look instead of re-checking everything.

## What this actually saves

Today this is 100% manual - someone reads the PDF and types the data in by hand, invoice by invoice. Even at a conservative 3-4 minutes per invoice (find the file, read it, type everything, double check the totals), a team processing a few hundred invoices a month is spending a real chunk of someone's working week just on data entry that doesn't require any actual judgment.

With this pipeline, that drops to seconds of machine processing per invoice, with the human only stepping in for the ones flagged needs_review - in my test run that was 1 out of 8, so roughly 12-13% needed a closer look, the rest were trusted automatically. That's not "no human in the loop" - it's "the human only looks at the invoices where their judgment is actually needed," which is a much better use of someone's time than retyping a clean line.

## How I'd measure if this is actually working

- **Extraction accuracy** - I don't have thousands of invoices to test against, but in my own test run, every required field (invoice number, date, vendor, total) extracted correctly on all 8 invoices, with line item totals matching what I'd expect by hand
- **Confidence score** - average across my test run was around 0.93, comfortably above the 0.8 threshold I set for flagging review
- **Processing speed** - in my test run, 8 invoices processed end to end (file check, Azure extraction, cleaning, validation, save to DB) in about 66 seconds total, so roughly 5-6 seconds per invoice for most of them. One invoice took closer to 30 seconds - Azure's response time wasn't perfectly consistent across the batch, which is worth knowing about rather than hiding, but even the slow case is still nothing compared to typing it by hand
- **Review rate** - 1 out of 8 invoices got flagged needs_review (a swapped due date), which is exactly the kind of catch this system is supposed to make - not a failure, the system working as intended
- **Zero crashes on a bad file** - I deliberately tested what happens with a duplicate invoice number hitting the database, and the pipeline correctly skipped that one file and kept processing the rest of the batch without stopping

None of these numbers are meant to be "production-scale proof" - it's 8 invoices, not 8,000. But they're real numbers from a real run of my own pipeline, not made-up targets, and they show the core idea works: extract reliably, flag what's uncertain, don't lose data, don't crash on one bad file.
