# SASTRA Moot Competition — Frontend Revamp

## What's changed
- Updated the competition timeline:
  - Registration opens: 10 November 2026
  - Registration closes: 26 November 2026
  - Preliminary rounds and knock-out round: 5–7 February 2027
  - Semi-finals and final: 13–14 February 2027
- Replaced the restrained Apple-inspired palette with a punchier violet, coral, teal and gold palette.
- Kept the existing React form, country calling-code picker, and API endpoint configuration.
- The frontend enables registration submission only during the specified registration window.

## Run
```bash
npm install
npm run dev
```

Set `VITE_API_URL` in the frontend environment if the FastAPI backend is not at `http://127.0.0.1:8000`.

## Backend follow-up required
This archive contains the frontend only, as requested. Update the backend's authoritative registration dates as well (currently in `backend/app/config.json`) before deployment. Frontend date checks are a user-interface convenience, not a security boundary; the backend must enforce the same window. Suggested values:
- `registration_open`: `2026-11-10T00:00:00`
- `registration_close`: `2026-11-26T23:59:59`
- `event_start`: `2027-02-05T00:00:00`
- `event_end`: `2027-02-14T23:59:59`
- `timezone`: `Asia/Kolkata`

The production build was not verified in this environment because dependencies (`vite`) are not installed here. Run `npm install` and `npm run build` locally before deployment.
