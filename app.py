import os
from functools import wraps
from datetime import datetime

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from dotenv import load_dotenv

import firebase_admin
from firebase_admin import credentials, firestore, auth as firebase_auth

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@carepulse.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

FIREBASE_WEB_CONFIG = {
    "apiKey": os.environ.get("FIREBASE_API_KEY", ""),
    "authDomain": os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
    "projectId": os.environ.get("FIREBASE_PROJECT_ID", ""),
    "storageBucket": os.environ.get("FIREBASE_STORAGE_BUCKET", ""),
    "messagingSenderId": os.environ.get("FIREBASE_MESSAGING_SENDER_ID", ""),
    "appId": os.environ.get("FIREBASE_APP_ID", ""),
}

# ================= FIREBASE ADMIN INIT =================
db = None
FIREBASE_READY = False
try:
    cred_path = os.environ.get("FIREBASE_CONFIG_PATH", "firebase_config.json")
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        FIREBASE_READY = True
    else:
        print(f"[CarePulse] No Firebase service account found at '{cred_path}'. "
              f"API routes will return a setup error until you add it. See README.md.")
except Exception as e:
    print(f"[CarePulse] Firebase init failed: {e}")


def firebase_required(f):
    """Guard API routes that need Firestore configured."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not FIREBASE_READY:
            return jsonify({
                "error": "Firebase is not configured yet. Add firebase_config.json "
                         "and your FIREBASE_* web keys in .env, then restart the server."
            }), 503
        return f(*args, **kwargs)
    return wrapper


def verify_patient_token():
    """Reads the Firebase ID token from the Authorization header and verifies it.
    Returns the decoded token dict (with 'uid', 'email') or None if invalid/missing."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    id_token = header.split("Bearer ", 1)[1].strip()
    try:
        return firebase_auth.verify_id_token(id_token)
    except Exception:
        return None


def patient_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        decoded = verify_patient_token()
        if not decoded:
            return jsonify({"error": "Not authenticated. Please log in again."}), 401
        request.patient = decoded
        return f(*args, **kwargs)
    return wrapper


def admin_required(view=True):
    """Decorator factory. view=True -> redirect to admin login page (for HTML routes).
    view=False -> return 401 JSON (for API routes)."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not session.get("is_admin"):
                if view:
                    return redirect(url_for("admin_login"))
                return jsonify({"error": "Admin login required."}), 401
            return f(*args, **kwargs)
        return wrapper
    return decorator


@app.context_processor
def inject_globals():
    return {
        "firebase_config": FIREBASE_WEB_CONFIG,
        "is_admin": session.get("is_admin", False),
    }


# ================= PAGE ROUTES =================
@app.route('/')
def home():
    return render_template('index.html')


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/login')
def login():
    return render_template('login.html')


@app.route('/signup')
def signup():
    return render_template('signup.html')


@app.route('/dashboard')
def patient_dashboard():
    return render_template('patient_dashboard.html')


@app.route('/doctors/search')
def search_doctors():
    return render_template('search_doctors.html')


@app.route('/book/<doctor_id>')
def book_appointment(doctor_id):
    return render_template('book_appointment.html', doctor_id=doctor_id)


@app.route('/my-appointments')
def my_appointments():
    return render_template('my_appointments.html')


@app.route('/profile')
def profile():
    return render_template('profile.html')


# ---- Admin auth (separate from patient Firebase Auth) ----
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        email = request.form.get('email', '')
        password = request.form.get('password', '')
        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session['is_admin'] = True
            session['admin_email'] = email
            return redirect(url_for('admin_dashboard'))
        error = "Invalid admin credentials."
    return render_template('admin_login.html', error=error)


@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    session.pop('admin_email', None)
    return redirect(url_for('admin_login'))


@app.route('/admin/dashboard')
@admin_required()
def admin_dashboard():
    return render_template('admin_dashboard.html')


@app.route('/admin/doctors')
@admin_required()
def admin_doctors():
    return render_template('admin_doctors.html')


@app.route('/admin/appointments')
@admin_required()
def admin_appointments():
    return render_template('admin_appointments.html')


# ================= DOCTOR API =================
@app.route('/api/doctors', methods=['GET'])
@firebase_required
def get_doctors():
    try:
        docs = db.collection('doctors').stream()
        doctors = [dict(doc.to_dict(), id=doc.id) for doc in docs]
        return jsonify(doctors), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/doctors/<doc_id>', methods=['GET'])
@firebase_required
def get_doctor(doc_id):
    try:
        doc = db.collection('doctors').document(doc_id).get()
        if not doc.exists:
            return jsonify({"error": "Doctor not found"}), 404
        return jsonify(dict(doc.to_dict(), id=doc.id)), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/doctors', methods=['POST'])
@firebase_required
@admin_required(view=False)
def add_doctor():
    data = request.json or {}
    required = ["name", "specialization", "fee"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400
    data.setdefault("rating", 4.5)
    data.setdefault("experience", "N/A")
    data.setdefault("availability", "Mon-Sat, 10am-5pm")
    data["createdAt"] = datetime.utcnow().isoformat()
    doc_ref = db.collection('doctors').add(data)
    return jsonify({"success": True, "id": doc_ref[1].id}), 201


@app.route('/api/doctors/<doc_id>', methods=['PUT'])
@firebase_required
@admin_required(view=False)
def update_doctor(doc_id):
    data = request.json or {}
    db.collection('doctors').document(doc_id).update(data)
    return jsonify({"success": True}), 200


@app.route('/api/doctors/<doc_id>', methods=['DELETE'])
@firebase_required
@admin_required(view=False)
def delete_doctor(doc_id):
    db.collection('doctors').document(doc_id).delete()
    return jsonify({"success": True}), 200


# ================= APPOINTMENT API =================
@app.route('/api/appointments', methods=['POST'])
@firebase_required
@patient_required
def create_appointment():
    data = request.json or {}
    required = ["doctorId", "doctorName", "date", "timeSlot"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    data["patientUid"] = request.patient["uid"]
    data["patientEmail"] = request.patient.get("email", "")
    data["status"] = "Pending"
    data["createdAt"] = datetime.utcnow().isoformat()
    doc_ref = db.collection('appointments').add(data)
    return jsonify({"success": True, "id": doc_ref[1].id}), 201


@app.route('/api/appointments/mine', methods=['GET'])
@firebase_required
@patient_required
def my_appointments_api():
    uid = request.patient["uid"]
    docs = db.collection('appointments').where('patientUid', '==', uid).stream()
    appts = [dict(doc.to_dict(), id=doc.id) for doc in docs]
    appts.sort(key=lambda a: a.get('createdAt', ''), reverse=True)
    return jsonify(appts), 200


@app.route('/api/appointments/<app_id>/cancel', methods=['PATCH'])
@firebase_required
@patient_required
def cancel_appointment(app_id):
    ref = db.collection('appointments').document(app_id)
    doc = ref.get()
    if not doc.exists:
        return jsonify({"error": "Appointment not found"}), 404
    if doc.to_dict().get("patientUid") != request.patient["uid"]:
        return jsonify({"error": "Not your appointment"}), 403
    ref.update({"status": "Cancelled"})
    return jsonify({"success": True}), 200


@app.route('/api/appointments/<app_id>/reschedule', methods=['PATCH'])
@firebase_required
@patient_required
def reschedule_appointment(app_id):
    data = request.json or {}
    ref = db.collection('appointments').document(app_id)
    doc = ref.get()
    if not doc.exists:
        return jsonify({"error": "Appointment not found"}), 404
    if doc.to_dict().get("patientUid") != request.patient["uid"]:
        return jsonify({"error": "Not your appointment"}), 403
    update = {"status": "Pending"}
    if data.get("date"):
        update["date"] = data["date"]
    if data.get("timeSlot"):
        update["timeSlot"] = data["timeSlot"]
    ref.update(update)
    return jsonify({"success": True}), 200


# ---- Admin appointment management ----
@app.route('/api/appointments', methods=['GET'])
@firebase_required
@admin_required(view=False)
def list_all_appointments():
    docs = db.collection('appointments').stream()
    appts = [dict(doc.to_dict(), id=doc.id) for doc in docs]
    appts.sort(key=lambda a: a.get('createdAt', ''), reverse=True)
    return jsonify(appts), 200


@app.route('/api/appointments/<app_id>', methods=['PATCH'])
@firebase_required
@admin_required(view=False)
def update_appointment_status(app_id):
    data = request.json or {}
    if data.get("status") not in ["Pending", "Approved", "Rejected", "Completed", "Cancelled"]:
        return jsonify({"error": "Invalid status"}), 400
    db.collection('appointments').document(app_id).update({"status": data["status"]})
    return jsonify({"success": True}), 200


# ================= PATIENT PROFILE API =================
@app.route('/api/patients/profile', methods=['GET'])
@firebase_required
@patient_required
def get_profile():
    uid = request.patient["uid"]
    doc = db.collection('patients').document(uid).get()
    if doc.exists:
        return jsonify(doc.to_dict()), 200
    return jsonify({}), 200


@app.route('/api/patients/profile', methods=['PUT'])
@firebase_required
@patient_required
def update_profile():
    uid = request.patient["uid"]
    data = request.json or {}
    data["email"] = request.patient.get("email", "")
    data["updatedAt"] = datetime.utcnow().isoformat()
    db.collection('patients').document(uid).set(data, merge=True)
    return jsonify({"success": True}), 200


@app.route('/api/patients/register', methods=['POST'])
@firebase_required
@patient_required
def register_profile():
    """Called right after Firebase signup to create the initial patient doc."""
    uid = request.patient["uid"]
    data = request.json or {}
    data["email"] = request.patient.get("email", "")
    data["role"] = "patient"
    data["createdAt"] = datetime.utcnow().isoformat()
    db.collection('patients').document(uid).set(data, merge=True)
    return jsonify({"success": True}), 201


# ================= ADMIN DASHBOARD STATS =================
@app.route('/api/admin/stats', methods=['GET'])
@firebase_required
@admin_required(view=False)
def admin_stats():
    doctors_count = len(list(db.collection('doctors').stream()))
    appt_docs = list(db.collection('appointments').stream())
    appointments = [d.to_dict() for d in appt_docs]
    patients_count = len(list(db.collection('patients').stream()))

    today = datetime.utcnow().strftime('%Y-%m-%d')
    today_appts = [a for a in appointments if a.get('date') == today]
    pending = [a for a in appointments if a.get('status') == 'Pending']

    return jsonify({
        "totalAppointments": len(appointments),
        "totalDoctors": doctors_count,
        "totalPatients": patients_count,
        "todayAppointments": len(today_appts),
        "pendingAppointments": len(pending),
    }), 200


if __name__ == '__main__':
    app.run(debug=True, port=5000)
