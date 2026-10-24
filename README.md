# CyberPrint Pay — simple, free version

A walk-in customer scans a QR code, uploads a file from their phone, pays by UPI, and gets a
job number. A small print agent on the café's Windows PC beeps, you check the payment and press
**Y**, and it prints — silently, no dialog.

Everything runs on free tiers. No build step, no framework to install.

---

## The three pieces

| Piece | Where it runs | What it does |
|-------|---------------|--------------|
| `index.html` | Customer's phone | Upload, choose settings, get a job number, see the UPI QR |
| `admin.html` | Café Windows PC (Chrome) | Watch the queue, open/download/reject, see the agent status |
| `agent/` | Café Windows PC (background) | Notifies you of new jobs and prints them on **Y** |

All three talk to one free **Supabase** project (database + private file storage + operator login).

---

## How a job flows

1. Customer uploads a file and picks pages/copies/colour → taps **Submit**.
2. They see their **job number**, the **amount**, and a **UPI QR** to pay.
3. The **print agent** on the café PC beeps and shows the job (file, pages, amount).
4. You check your UPI app / the cash, then press **Y** in the agent window to print, or **N** to reject.
5. The agent prints silently and marks the job **printed**. The panel updates.

---

## Files

```
index.html            customer page
admin.html            operator panel
config.js             website settings (Supabase URL + anon key, UPI ID, prices)
supabase-setup.sql    database + storage setup (run once)
README.md             this file
.gitignore            keeps secrets out of git
agent/
  agent.py            the Python print agent
  config.json         agent settings (secrets - never host this)
  run-agent.bat       double-click to start the agent
  README.txt          agent setup notes
```

---

## Setup

### A. Supabase (once)

1. Create a free project at supabase.com.
2. SQL Editor → New query → paste the whole `supabase-setup.sql` → Run. (Safe to re-run.)
3. Authentication → Users → Add user: create the operator email + password. Turn off public sign-ups.
4. Settings → API: copy the **Project URL** and the **anon public** key.

### B. The website

5. Put those two values into `config.js` (`SUPABASE_URL`, `SUPABASE_ANON_KEY`).
6. Deploy the folder to any free static host — **Netlify Drop** (drag the folder in),
   **Cloudflare Pages**, or **Vercel**. You get a free URL.
   - Local test: `python -m http.server 8000` in the folder, then open `http://localhost:8000`.
7. Make a QR code for the customer URL and put it at the counter.

### C. The print agent (on the café PC)

8. Download **SumatraPDF** (free, portable) from sumatrapdfreader.org and put `SumatraPDF.exe`
   in the `agent/` folder.
9. Edit `agent/config.json`: `supabase_url`, `anon_key` (same as `config.js`), the operator
   `email`/`password`, the `printer` (exact Windows name, or `""` for the default).
10. Set the café printer as the Windows default.
11. Double-click `agent/run-agent.bat`. Leave the window open. (For auto-start, put a shortcut
    in `shell:startup`.)

### Test

- Upload a PDF from your phone → the agent beeps with the job details.
- Check the amount, press **Y** → it prints and the job shows as **Printed** in the panel.

---

## Payment

There is **no automatic payment verification** — that needs a paid gateway. The free flow is:
the customer pays by UPI (QR or the "Pay with UPI app" button), and **you** confirm it before
pressing **Y**. The amount in the QR is locked, so the customer can't change it.

---

## When files are deleted

Every uploaded file is removed **10 minutes after upload**, whatever the operator does. The job
*record* (number, pages, amount, times, status) is always kept. A job nobody acts on within
10 minutes is marked `cancelled`. The sweep runs from the operator panel while it's open.

---

## Supported files

**PDF** (any pages), **JPG / PNG** (single page), up to 20 MB. Office formats (DOCX/XLSX/PPTX)
need the customer to "Save as PDF" first.

---

## Changing prices

₹5 per side B&W, ₹10 per side colour. Change them in **both** `config.js` (`PRICE_BW`,
`PRICE_COLOR`) and the `total_price` line in `supabase-setup.sql` (re-run the SQL after editing).

---

## Security — read this before hosting

- **The `anon` key in `config.js` is meant to be public.** It is the "public" key; your data is
  protected by row-level security, not by hiding it. It is safe to host.
- **Never put the `service_role` key in `config.js`** or anywhere in the website. It bypasses all
  security. Only the `anon` key belongs there.
- **`agent/config.json` holds the operator password in plain text.** It is in `.gitignore` — keep
  it local, never host or commit the `agent/` folder.
- Uploaded files are private; only the signed-in operator (and the agent) can read or delete them.
- Prices are calculated by the database, so a tampered phone can't change the amount.

---

## Troubleshooting

**Agent: `TABLE MISSING: jobs` or `agent_status`** — run `supabase-setup.sql` in the project's SQL
Editor, then restart the agent.

**Agent: `WRONG ANON KEY`** — the `anon_key` in `agent/config.json` doesn't match the project. Copy
the current key from Supabase → Settings → API into **both** `config.js` and `agent/config.json`,
then restart.

**Agent: `Initial sign-in failed`** — wrong operator email/password, or the user doesn't exist in
that project (creating a new project starts with an empty Auth list).

**Job lands in `failed`** — the card shows the reason. Common causes: SumatraPDF.exe missing from
`agent/`; wrong printer name; printer offline.

**Nothing prints on Y** — set `printer` in `agent/config.json` to the exact printer name
(`Get-Printer | Format-Table Name` in PowerShell). With `""` it uses the Windows *default*
printer, which is often "Microsoft Print to PDF".

**QR not showing / dead link** — `UPI_ID` must be filled in `config.js`. The page will say so
plainly if it's empty.

---

## What this deliberately leaves out

No payment-gateway integration, no automatic office-document conversion, no customer accounts,
and no server-side retention job (the panel does the 10-minute sweep).
