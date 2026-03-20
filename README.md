# Transition Deployment Tracker

A decision tool for leadership to view bench capacity, filter by vertical and experience, and deploy the right person fast.

## Purpose

- **View bench capacity** — See who is available for transitions
- **Filter by vertical + experience** — Find the right fit quickly
- **Compare nominees** — Experience level, title, current assignment
- **Export** — Grab filtered views for placement planning

**Logo:** Replace `static/logo.svg` with your company logo, or add `assets/logo.png` (or `.svg`, `.jpg`, `.webp`). Logo appears in the header.

## Flow

1. Export responses from **Microsoft Forms** (Transition Team Member Nomination Form) as CSV
2. Add the CSV to `Data/` and push to GitHub (or deploy)
3. Use the **Executive Snapshot** and **Deployment Grid** to scan capacity
4. **Filter** and **Export** as needed for placement decisions

**Succession Planning tab:** Export the Microsoft Forms succession survey as CSV into `Succsession/` (or `Succession/`). The app loads the **highest-numbered** `Succession Planning (N).csv` first, then falls back to `Succession Planning.csv` — same preference pattern as the numbered nomination files in `Data/`.

## Run Locally

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000 (or the port shown). If `Data/Transition Team Member Nomination Form(Sheet1).csv` exists, it loads automatically for testing.

## Deploy to Heroku

```bash
heroku create your-app-name
git push heroku main
```

**Note:** Data is stored in memory. On dyno restart (deploy, sleep), you’ll need to re-upload the CSV. For persistent storage, add Heroku Postgres and update the app to use it.

## CSV Format

Expected columns from Microsoft Forms export:

- `Who are you Nominating` — Nominee name
- `Vertical` — Manufacturing, Life Sciences, Technology, etc.
- `Experience Level` — Novice / Intermediate / Expert (parsed from form text)
- `Current Title` — Site Manager, Account Manager, Account Director, etc.
- `Current Account / Site Assignment` — Current placement
- `Summary of Prior Transition Experience` — Context
