# CyberPrint Pay — simple, free version

A tiny two-page website for a cybercafé:

- **Customer page** (`index.html`) — the customer scans a QR code, opens the page on their phone, uploads a file, picks print settings, and gets a job number.
- **Operator panel** (`admin.html`) — the operator opens this on the café's Windows PC, sees incoming jobs, and **approves and prints** them (or rejects them). Each job also has **Open** and **Download** buttons.

No build step, no framework to install, no paid service.

---

## How printing works

The operator panel prints **from the browser**. When the operator clicks **Approve & print**, the panel renders the document and opens the browser's print dialog. The printer installed on the PC is shown there (Windows' default printer is preselected) and the operator clicks Print. The job is then marked approved; the file is removed separately, 10 minutes after upload.

A web page cannot list the PC's printers on its own — no browser exposes that to a site — so the print dialog is where the printer is chosen. Set the café printer as the Windows default once, and **Approve & print** then goes straight to it.

The loop is:

1. The printer is installed on the café's Windows PC (USB or Wi-Fi) and set as the default — Windows sees it as a normal printer.
2. The operator opens `admin.html` in Chrome on that PC.
3. A new job appears in **Queue**.
4. The operator clicks **Approve & print** — a print dialog opens with the printer preselected. They print.
5. The job moves to **Approved**. (The file is removed automatically 10 minutes after upload, not on approval.)

Each pending job also has **Open** (view the file in a new tab), **Download** (save it to the PC — handy if you want to print by another route), and **Reject**.

---

## When files are deleted

Every uploaded file is removed **10 minutes after upload**, no matter what the operator does. Approving or rejecting a job does *not* delete the file.

- A job nobody has acted on within 10 minutes is marked `cancelled` and drops out of the queue.
- Approving or rejecting only changes the job's status. The file stays until the 10-minute mark, so you can still **Open** or **Download** an approved job during that window.

The job *record* (job number, pages, amount, time, status) is always kept for the daily summary; only the uploaded file is deleted.

**One thing to know:** the 10-minute cleanup is carried out by the operator panel itself (it checks every few seconds while it is open). During business hours the panel is open on the café PC, so this works. If the panel is closed — say overnight — any leftover file is cleaned up the next time the panel opens.

---

## Files

| File | What it is |
|------|------------|
| `index.html` | Customer upload page |
| `admin.html` | Operator panel |
| `config.js` | Your settings (Supabase keys, shop name, prices, retention) |
| `supabase-setup.sql` | Database + storage setup (run once) |
| `README.md` | This file |

---

## Setup (about 15 minutes, all free)

**1. Create a Supabase project**
Go to supabase.com, sign up (free), and create a new project. Pick any region close to you. Wait for it to finish starting.

**2. Create the database and storage**
In the project, open **SQL Editor → New query**, paste the entire contents of `supabase-setup.sql`, and click **Run**. It should say success. (Re-running it later is safe.)

**3. Create the operator login**
Go to **Authentication → Users → Add user**, and create one user with your own email and a password. This is the login for the operator panel. Turn off public sign-ups under Authentication → Providers if it is on, so only you can make accounts.

**4. Fill in `config.js`**
In the project, open **Settings → API**. Copy:
- **Project URL** → paste into `SUPABASE_URL`
- **anon public key** → paste into `SUPABASE_ANON_KEY`

Set `SHOP_NAME` to your shop's name if you like. `RETENTION_MINUTES` is 10 by default.

**5. Put the site online (free)**
Any of these work; pick one:
- **Netlify Drop** — go to app.netlify.com/drop and drag the whole folder in. You get a free URL.
- **Cloudflare Pages** — create a project, upload the folder.
- **Vercel** — import as a static site.

(To test locally first: open a terminal in the folder, run `python -m http.server 8000`, and visit `http://localhost:8000`.)

**6. Make the QR code**
Turn the customer page URL into a QR code with any free generator, print it, and stick it at the counter. Point it at the deployed address (the one that opens `index.html`), e.g. `https://your-site.netlify.app`.

**7. Test it end to end**
- On your phone, open the site, upload a PDF, choose settings, submit. Note the job number.
- On the Windows PC, open `admin.html` in Chrome, sign in with the operator account you made.
- The job appears under **Queue**. Click **Approve & print** — the print dialog opens with your printer preselected; print it. The file then disappears from storage and the job moves to **Approved**.

---

## Day-to-day use

- Keep the operator page open in Chrome on the café PC. It refreshes itself every 10 seconds (the little dot top-right turns green when connected).
- When a job arrives, check the amount, take payment in cash or UPI, then click **Approve & print** — the print dialog opens, choose your printer and print.
- Use **Download** if you'd rather print the file another way, **Open** to just view it, or **Reject** to decline.
- The file is deleted 10 minutes after the customer uploaded it, whatever you do — so **Download** it if you might need it later.
- The card shows a countdown ("file auto-deletes in ~N min") so you know how long you have before an untouched job expires.

---

## Supported files

- **PDF** — any number of pages.
- **JPG / PNG** — single page.
- Up to 20 MB each.

**Not supported directly:** DOCX, XLSX, PPTX, and other office formats. Ask the customer to "Save as PDF" before uploading, or open it on the counter PC and export to PDF there.

---

## Changing prices

Prices are ₹5 per side for B&W and ₹10 per side for colour. If you change them, change them in **both** places so the display and the stored amount agree:
- `config.js` → `PRICE_BW` and `PRICE_COLOR`
- `supabase-setup.sql` → the `5` and `10` in the `total_price` line (re-run the SQL after editing)

---

## Security and limits (worth knowing)

- Uploaded files are **private**. Only the signed-in operator can open or delete them; customers cannot see anyone else's files. The panel opens them with a short-lived link (5 minutes).
- Prices are calculated by the database, not the browser, so a tampered phone can't change the amount.
- **Free-tier limits:** roughly 1 GB of file storage. Because files are deleted quickly this is rarely an issue, but job *records* accumulate — see the optional delete statement at the bottom of the SQL file if you want to clear old rows.
- Free projects can pause after long inactivity; normal daily use keeps it awake.

---

## What this deliberately leaves out

To stay simple and free, this version has no payment records, no automatic file conversion, no background print agent, and no real-time push (it polls instead). Any of those can be added later without rebuilding what is here.

If you ever want the 10-minute deletion to happen even when the panel is closed, that needs a small scheduled job on the server (a Supabase Edge Function on a timer) — a later upgrade, not needed for normal use.

---

## Troubleshooting

**"check constraint jobs_status_check ... is violated by some row"** — you are re-running the SQL on a database that still has jobs with an old status (usually `printed`, from an earlier version of this file). The updated `supabase-setup.sql` now fixes this by itself: it re-labels those rows to `approved` just before tightening the rule. Either re-run the whole file, or run this one line first and then the rest:

```sql
update public.jobs set status = 'approved' where status not in ('pending','approved','rejected','cancelled');
```

**"Could not submit: new row violates row-level security policy" when a customer uploads** — the SQL did not finish running, so the access rules near the end of the file were never created (the usual cause is an earlier statement erroring, which makes the editor skip everything after it). Run the whole `supabase-setup.sql` again — it now completes, and the access rules are placed early in the file so this is much less likely to recur. To check whether the rules exist, run:

```sql
select policyname, tablename from pg_policies where tablename in ('jobs','objects');
```

You should see six policies (three on `jobs`, three on `objects`).

**Same error again even after that** — check where you are testing. If you open the customer page in the *same browser* where you signed into the operator panel, the customer page can inherit that login and try to insert as a signed-in user. The updated files prevent this (the customer page no longer loads any stored login), and the create/upload rules now accept both signed-out and signed-in browsers. If you are testing by hand, use your phone, or a private/incognito window, for the customer page.

