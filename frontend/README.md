# Chirp dashboard

React + Vite UI on port **5173**. Proxies `/api` to `http://127.0.0.1:8000` during development.

```bash
cd frontend
npm install
npm run dev
```

Production build (`npm run build`) serves static files from `frontend/dist`. Point `VITE_API_URL` at your API origin if the UI is not served behind the same host as the API.
