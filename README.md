# Influencers Performance Dashboard — FY26

An interactive **Streamlit** dashboard to track influencer-driven sales
performance on a monthly basis. The headline metric is **Quantity Purchased
(MT)** generated through influencers across distributors and dealers.

## Access control

The dashboard is password protected with two roles, differentiated by the
password entered on the login screen:

| Password | Role | Access |
| --- | --- | --- |
| `1111` | Viewer | Full read-only dashboard (all influencers) |
| `9999` | Admin | Everything + the **data upload** option |
| _phone number_ | Influencer | Their **own data only**, scoped automatically |

- The upload control is shown **only to admins**.
- **Influencers** sign in with their registered **phone number** as the
  password; the dashboard then shows only the rows belonging to that phone, with
  a personalised header. They also get a **rank callout** showing where they
  stand against all influencers by volume (rank, own volume, standing, and the
  gap to #1). Sensitive columns (phone number) are hidden from their data table
  and CSV export. Influencers whose phone number is missing from the data cannot
  log in this way.
- The `1111` / `9999` passwords are reserved and never collide with phone
  numbers. They are defined in the `PASSWORDS` map in `app.py` — for a
  production deployment move these into `st.secrets` rather than keeping them in
  code. Note that phone-number passwords are convenient but guessable, so this
  is light-touch gating rather than strong security.

## Features

- **KPI cards** — total volume (MT), transactions, active influencers,
  distributors, average volume per transaction, and verified share.
- **Overview tab** — volume by month, verification-status split, and a daily
  volume trend.
- **Influencers tab** — top-N influencer leaderboard by volume with
  transactions and dealer reach.
- **Distributors & Dealers tab** — top distributors and dealers, plus a
  distributor × verification-status breakdown.
- **Data tab** — filtered record table with CSV download.
- **Filters** (on the dashboard page, visible to everyone) — Month,
  Distributor, Verification Status, Quantity range, plus free-text search for
  Influencer and Dealer. Admins can also upload a refreshed `.xlsx` from the
  sidebar to swap the dataset live.

## Data

The bundled dataset lives at `data/Influencer_data_FY26.xlsx`. The loader
expects these columns:

| Column | Used as |
| --- | --- |
| Distributor Name | Distributor |
| Name of Influencer | Influencer |
| Name of Dealer | Dealer |
| Quantity Purchased (MT) | Quantity_MT (metric) |
| Date of Purchase (MM-DD-YYYY) | Purchase date → Month / Day |
| Remarks by Inside Sales (Verification Status) | Verification status |
| Phone Number | Phone |

The "Month" used in charts is **derived from the purchase date**, so the
dashboard automatically extends as new months are added to the file.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open http://localhost:8501.

## Deploy

Push to GitHub and deploy on [Streamlit Community Cloud](https://share.streamlit.io)
— point it at `app.py`. No secrets required.
