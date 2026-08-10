# CarePulse — Hospital Appointment & Patient Management System

Flask + Firebase (Auth + Firestore) + Tailwind CSS + Vanilla JS.

Patients sign up/log in with real Firebase Authentication, book appointments with
real doctors stored in Firestore, and manage their own bookings. Admin staff log in
separately (Flask session) to manage doctors and approve/reject/complete appointments.

---

## 1. Create a Firebase project

1. Go to https://console.firebase.google.com → **Add project** → give it a name (e.g. `carepulse`).
2. Once created, open **Build → Authentication → Get started** → enable the
   **Email/Password** sign-in provider.
3. Open **Build → Firestore Database → Create database** → start in **production mode**
   (fine either way — only your Flask server touches Firestore, using the admin key below,
   so client-side security rules aren't in play).

## 2. Get your two sets of credentials

You need **two different things** from Firebase — don't mix them up:

**A. Server credentials (secret — for Flask/Firestore)**
- Project settings (gear icon) → **Service accounts** → **Generate new private key**.
- This downloads a JSON file. Rename it `firebase_config.json` and put it in the
  project root (same folder as `app.py`). It's already in `.gitignore` — never commit it.

**B. Web app credentials (public — for the browser login widget)**
- Project settings → **General** → scroll to "Your apps" → click the `</>` (web) icon
  → register an app (nickname anything, no need for hosting).
- Copy the `firebaseConfig` object it shows you (apiKey, authDomain, projectId, etc.)
  into your `.env` file (see below). These are safe to expose in the browser.

## 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:
- `FLASK_SECRET_KEY` — any long random string.
- `ADMIN_EMAIL` / `ADMIN_PASSWORD` — the login for the Admin/Doctor dashboard
  (this is a simple Flask-session login, separate from patient accounts).
- `FIREBASE_API_KEY`, `FIREBASE_AUTH_DOMAIN`, `FIREBASE_PROJECT_ID`,
  `FIREBASE_STORAGE_BUCKET`, `FIREBASE_MESSAGING_SENDER_ID`, `FIREBASE_APP_ID`
  — paste from step 2B.

## 4. Install & run

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Visit **http://127.0.0.1:5000**

- Patients: `/signup` → creates a real Firebase Auth account + a `patients/{uid}`
  Firestore document.
- Admin: `/admin/login` → uses the `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env`.
  From there, add a few doctors at `/admin/doctors` so `/doctors/search` has
  something to show.

## 5. How the pieces fit together

| Layer | What it does |
|---|---|
| **Firebase Auth (client SDK, loaded in `base.html`)** | Patient signup/login/logout in the browser. |
| **Firebase ID token** | Sent as `Authorization: Bearer <token>` on every patient API call (booking, my-appointments, profile) so Flask knows *which* patient is asking. |
| **Firebase Admin SDK (`app.py`)** | Server-side Firestore reads/writes (doctors, appointments, patient profiles) and token verification. |
| **Flask session** | Admin/doctor login only — protects `/admin/*` pages and their write APIs. |

## 6. Project structure

```
hospital-management/
├── app.py                     # Flask app: pages + REST API
├── requirements.txt
├── .env.example                # copy to .env and fill in
├── firebase_config.example.json  # copy to firebase_config.json (real key) — gitignored
├── templates/
│   ├── base.html               # nav, footer, Firebase init
│   ├── index.html              # Landing page
│   ├── about.html              # Departments + doctor preview
│   ├── login.html               # Patient login (Firebase Auth)
│   ├── signup.html              # Patient signup (Firebase Auth)
│   ├── patient_dashboard.html   # Patient overview
│   ├── search_doctors.html      # Search/filter/sort doctors
│   ├── book_appointment.html    # Booking form
│   ├── my_appointments.html     # View/cancel/reschedule
│   ├── profile.html             # Patient profile + medical history
│   ├── admin_login.html         # Staff login
│   ├── admin_dashboard.html     # Stats
│   ├── admin_doctors.html       # Doctor CRUD
│   └── admin_appointments.html  # Approve/reject/complete
└── static/js/                 # (all JS is inline per-template for simplicity)
```

## 7. Firestore collections

| Collection | Fields |
|---|---|
| `doctors` | name, specialization, fee, rating, experience, availability |
| `appointments` | patientUid, patientEmail, doctorId, doctorName, specialization, date, timeSlot, notes, status (Pending/Approved/Rejected/Completed/Cancelled) |
| `patients` | name, phone, dob, bloodGroup, allergies, medicalHistory, email |

## 8. Troubleshooting

- **"Firebase is not configured yet" error on API calls** → you haven't added
  `firebase_config.json` yet, or the path in `.env` (`FIREBASE_CONFIG_PATH`) is wrong.
- **Login button does nothing** → open browser dev tools console; usually means the
  `FIREBASE_*` values in `.env` are missing/wrong, so `firebaseConfig` in `base.html`
  is empty.
- **Signup works but "My Appointments" is empty after booking** → make sure you're
  booking while logged in as that same patient (check the top-right nav shows your email).

## 9. Suggested next steps (from the original project brief)

- Payment gateway integration (Razorpay/UPI) for consultation fees.
- SMS/WhatsApp appointment reminders.
- Doctor-side upload of prescriptions/lab reports into the patient profile.
