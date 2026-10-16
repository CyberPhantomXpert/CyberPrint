-- CyberPrint Pay - Supabase setup (free tier)
-- Run the WHOLE file at once: SQL Editor -> New query -> paste -> Run.
-- Safe to re-run.
--
-- NOTE: if any single statement fails, the statements AFTER it do not run.
-- So if you ever see an error, fix the cause and run the whole file again.
-- The access rules are deliberately placed BEFORE the riskier table tweaks,
-- so a failure near the end can never leave the app unable to accept uploads.

-- 1. Jobs table --------------------------------------------------------------
create extension if not exists pgcrypto;

create table if not exists public.jobs (
  id           uuid primary key,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  customer_name text,
  file_name    text not null,
  file_path    text,                     -- set to null once the file is deleted
  file_type    text,
  file_deleted boolean not null default false,
  page_count   int  not null default 1 check (page_count between 1 and 500),
  copies       int  not null default 1 check (copies between 1 and 50),
  color_mode   text not null default 'bw'  check (color_mode in ('bw','color')),
  paper_size   text not null default 'A4',
  orientation  text not null default 'portrait' check (orientation in ('portrait','landscape')),
  status       text not null default 'pending',
  note         text,
  -- Price is calculated by the database, not the browser.
  -- Keep the 5 and 10 here in sync with config.js (PRICE_BW / PRICE_COLOR).
  total_price  int generated always as (
                 page_count * copies * (case when color_mode = 'color' then 10 else 5 end)
               ) stored
);

-- upgrades, in case you already ran an earlier version of this file
alter table public.jobs add column if not exists file_deleted boolean not null default false;
alter table public.jobs alter column file_path drop not null;

-- 2. Keep updated_at fresh on every change -----------------------------------
create or replace function public.touch_updated_at() returns trigger as $$
begin new.updated_at = now(); return new; end; $$ language plpgsql;

drop trigger if exists trg_jobs_touch on public.jobs;
create trigger trg_jobs_touch before update on public.jobs
for each row execute function public.touch_updated_at();

-- 3. Access rules on the jobs table (Row Level Security) ---------------------
alter table public.jobs enable row level security;

-- allow a signed-out customer (anon) and, harmlessly, a signed-in browser too
-- (the customer page can otherwise inherit an operator login on the same browser)
drop policy if exists "anon can create jobs" on public.jobs;
create policy "anon can create jobs" on public.jobs
  for insert to anon, authenticated with check (status = 'pending');

drop policy if exists "operator can read jobs" on public.jobs;
create policy "operator can read jobs" on public.jobs
  for select to authenticated using (true);

drop policy if exists "operator can update jobs" on public.jobs;
create policy "operator can update jobs" on public.jobs
  for update to authenticated using (true) with check (true);

-- 4. Private storage bucket and its access rules -----------------------------
insert into storage.buckets (id, name, public)
values ('jobs','jobs', false)
on conflict (id) do nothing;

drop policy if exists "anon can upload job files" on storage.objects;
create policy "anon can upload job files" on storage.objects
  for insert to anon, authenticated with check (bucket_id = 'jobs');

drop policy if exists "operator can read job files" on storage.objects;
create policy "operator can read job files" on storage.objects
  for select to authenticated using (bucket_id = 'jobs');

-- The operator panel deletes files (on approve/print, on reject, and after 10 min).
drop policy if exists "operator can delete job files" on storage.objects;
create policy "operator can delete job files" on storage.objects
  for delete to authenticated using (bucket_id = 'jobs');

-- 5. Tidy old status values, then lock the status rule -----------------------
-- Kept LAST on purpose: this is the only step that can fail on an existing table.
update public.jobs set status = 'approved' where status not in ('pending','approved','rejected','cancelled');

alter table public.jobs drop constraint if exists jobs_status_check;
alter table public.jobs add  constraint jobs_status_check
  check (status in ('pending','approved','rejected','cancelled'));

-- 6. Optional: clear old job records -----------------------------------------
-- Files are removed by the panel; the row (amount, time) stays as a record.
-- delete from public.jobs where created_at < now() - interval '30 days';
