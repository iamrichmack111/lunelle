from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response, send_from_directory
import sqlite3, os, csv, io, statistics, math, calendar
from collections import Counter
from datetime import datetime, date, timedelta, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import swisseph as swe

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("LUNELLE_DB_PATH", os.path.join(APP_DIR, "period_tracker.db"))

app = Flask(__name__)

# Keep sessions valid across restarts. If SECRET_KEY is not supplied, create a
# local persistent key once instead of generating a new one every launch.
def _load_secret_key():
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    key_path = os.path.join(APP_DIR, ".secret_key")
    try:
        if os.path.exists(key_path):
            key = open(key_path, "r", encoding="utf-8").read().strip()
            if key:
                return key
        import secrets
        key = secrets.token_hex(32)
        with open(key_path, "w", encoding="utf-8") as f:
            f.write(key)
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
        return key
    except OSError:
        # Last-resort development fallback when the app directory is read-only.
        return "lunelle-local-development-key-change-me"

app.secret_key = _load_secret_key()
app.config.update(
    SESSION_COOKIE_NAME="lunelle_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)


def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _ensure_columns(conn, table, columns):
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for col, sql_type in columns:
        if col not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {sql_type}")


def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS periods (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT,
        flow TEXT DEFAULT 'medium',
        notes TEXT DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS daily_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        log_date TEXT NOT NULL,
        mood TEXT DEFAULT '',
        pain INTEGER DEFAULT 0,
        energy INTEGER DEFAULT 5,
        flow TEXT DEFAULT '',
        symptoms TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, log_date),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS journal_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        entry_date TEXT NOT NULL,
        title TEXT DEFAULT '',
        body TEXT NOT NULL,
        vibe TEXT DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS custom_symptoms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, name),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS medications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        dose TEXT DEFAULT '',
        schedule_time TEXT DEFAULT '20:00',
        notes TEXT DEFAULT '',
        active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS medication_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        medication_id INTEGER NOT NULL,
        log_date TEXT NOT NULL,
        taken INTEGER DEFAULT 1,
        taken_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, medication_id, log_date),
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(medication_id) REFERENCES medications(id)
    );

    CREATE TABLE IF NOT EXISTS product_inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        category TEXT DEFAULT 'Period care',
        quantity INTEGER DEFAULT 0,
        low_at INTEGER DEFAULT 3,
        notes TEXT DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)

    _ensure_columns(conn, "users", [
        ("birth_date", "TEXT"), ("birth_time", "TEXT"), ("birth_place", "TEXT"),
        ("reminder_period_days", "INTEGER DEFAULT 3"),
        ("reminder_daily_log", "INTEGER DEFAULT 1"),
        ("reminder_log_time", "TEXT DEFAULT '20:00'"),
        ("lock_pin_hash", "TEXT"), ("lock_enabled", "INTEGER DEFAULT 0"),
        ("sleep_goal", "REAL DEFAULT 8"), ("hydration_goal", "INTEGER DEFAULT 8"),
        ("display_name", "TEXT"), ("focus", "TEXT DEFAULT 'cycle'"),
        ("onboarding_complete", "INTEGER DEFAULT 0"), ("plan", "TEXT DEFAULT 'free'"),
    ])
    _ensure_columns(conn, "daily_logs", [
        ("stress", "INTEGER DEFAULT 0"), ("sleep_hours", "REAL"),
        ("hydration", "INTEGER DEFAULT 0"), ("libido", "TEXT DEFAULT ''"),
        ("discharge", "TEXT DEFAULT ''"), ("exercise", "TEXT DEFAULT ''"),
        ("temperature", "REAL"), ("medication", "TEXT DEFAULT ''"),
    ])
    conn.commit()
    conn.close()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


@app.before_request
def require_optional_app_lock():
    if not session.get("user_id"):
        return None
    endpoint = request.endpoint or ""
    allowed = {"unlock", "logout", "static", "service_worker"}
    if endpoint in allowed or endpoint.startswith("static"):
        return None
    conn = db()
    user = conn.execute("SELECT lock_enabled FROM users WHERE id=?", (session["user_id"],)).fetchone()
    conn.close()
    if user and user["lock_enabled"] and not session.get("unlocked"):
        return redirect(url_for("unlock"))
    return None


def medication_status(conn, user_id, target=None):
    target = target or date.today()
    meds = conn.execute("SELECT * FROM medications WHERE user_id=? AND active=1 ORDER BY schedule_time,name", (user_id,)).fetchall()
    logs = conn.execute("SELECT medication_id FROM medication_logs WHERE user_id=? AND log_date=? AND taken=1", (user_id, target.isoformat())).fetchall()
    taken = {r["medication_id"] for r in logs}
    return [{**dict(m), "taken_today": m["id"] in taken} for m in meds]


def cycle_lengths(periods):
    ordered = sorted(periods, key=lambda r: r["start_date"])
    starts = [parse_date(r["start_date"]) for r in ordered]
    vals = [(starts[i] - starts[i - 1]).days for i in range(1, len(starts))]
    return [x for x in vals if 15 <= x <= 60]


def cycle_stats(periods):
    if not periods:
        return {
            "avg_cycle": None, "avg_period": None, "next_period": None,
            "days_until": None, "current_status": "No cycle data yet",
            "current_period_end": None,
        }

    ordered = sorted(periods, key=lambda r: r["start_date"])
    lengths = cycle_lengths(ordered)
    period_lengths = []
    for r in ordered:
        if r["end_date"]:
            d = (parse_date(r["end_date"]) - parse_date(r["start_date"])).days + 1
            if 1 <= d <= 14:
                period_lengths.append(d)

    avg_cycle = round(statistics.mean(lengths)) if lengths else 28
    avg_period = round(statistics.mean(period_lengths)) if period_lengths else 5
    last = ordered[-1]
    last_start = parse_date(last["start_date"])
    predicted = last_start + timedelta(days=avg_cycle)
    today = date.today()

    if last["end_date"] is None:
        current_status = "Period currently active"
        current_period_end = last_start + timedelta(days=avg_period - 1)
    else:
        current_status = "Cycle tracking active"
        current_period_end = None

    return {
        "avg_cycle": avg_cycle,
        "avg_period": avg_period,
        "next_period": predicted.isoformat(),
        "days_until": (predicted - today).days,
        "current_status": current_status,
        "current_period_end": current_period_end.isoformat() if current_period_end else None,
    }


def cycle_phase(periods, target=None):
    target = target or date.today()
    if not periods:
        return {"name": "Not enough data", "icon": "✦", "day": None, "description": "Add a period start date to unlock phase estimates."}
    stats = cycle_stats(periods)
    avg_cycle = stats["avg_cycle"] or 28
    avg_period = stats["avg_period"] or 5
    starts = sorted(parse_date(p["start_date"]) for p in periods if parse_date(p["start_date"]) <= target)
    if not starts:
        return {"name": "Not enough data", "icon": "✦", "day": None, "description": "No tracked cycle starts before this date."}
    last_start = starts[-1]
    day = (target - last_start).days + 1
    if day > avg_cycle + 7:
        return {"name": "Cycle timing unclear", "icon": "♡", "day": day, "description": "Your predicted date has passed; logging the next period will reset the estimate."}
    ovulation_day = max(10, avg_cycle - 14)
    fertile_start, fertile_end = max(avg_period + 1, ovulation_day - 5), ovulation_day + 1
    if day <= avg_period:
        return {"name": "Menstrual", "icon": "🌷", "day": day, "description": "Estimated menstrual phase based on your tracked period length."}
    if day < fertile_start:
        return {"name": "Follicular", "icon": "🌱", "day": day, "description": "Estimated follicular phase as your next ovulation estimate approaches."}
    if fertile_start <= day <= fertile_end:
        return {"name": "Estimated fertile window", "icon": "✨", "day": day, "description": "Cycle-awareness estimate only — not reliable contraception."}
    return {"name": "Luteal", "icon": "🌙", "day": day, "description": "Estimated luteal phase before the next predicted period."}



def wellness_score(today_log, sleep_goal=8, hydration_goal=8):
    """A lightweight reflection score from today's self-reported wellness data.
    It is intentionally not a medical score or diagnosis.
    """
    if not today_log:
        return None
    try:
        sleep = float(today_log["sleep_hours"] or 0)
        water = int(today_log["hydration"] or 0)
        energy = int(today_log["energy"] or 0)
        stress = int(today_log["stress"] or 0)
    except Exception:
        return None
    sleep_part = min(1.0, sleep / max(float(sleep_goal or 8), 1)) * 30
    water_part = min(1.0, water / max(int(hydration_goal or 8), 1)) * 25
    energy_part = max(0, min(10, energy)) / 10 * 25
    stress_part = (10 - max(0, min(10, stress))) / 10 * 20
    return round(sleep_part + water_part + energy_part + stress_part)


def ritual_for(phase, today_log=None):
    base = {
        "Menstrual": ("Soft reset", "Keep today gentle: hydrate, choose an easy stretch, and give yourself extra quiet time."),
        "Follicular": ("Fresh-start energy", "Pick one thing you want to begin, take a walk, and use the journal to capture new ideas."),
        "Estimated fertile window": ("Bright window", "Use the energy check-in, hydrate, and choose movement that feels good for you."),
        "Luteal": ("Protect your peace", "Lower the noise: tidy one small space, hydrate, and make tonight a little slower."),
    }
    title, text = base.get(phase.get("name"), ("Tune in", "Check in with your energy, water, sleep and mood, then choose what feels supportive today."))
    if today_log:
        if (today_log["stress"] or 0) >= 7:
            text = "Stress looks high in today's check-in. Try a low-demand reset: water, a short walk, quiet music, or a few journal lines."
        elif (today_log["energy"] or 0) <= 3:
            text = "Energy is low today. Keep the plan small: hydrate, rest when you can, and choose one easy win."
    return {"title": title, "text": text}


def checkin_streak(logs):
    dates = {parse_date(r["log_date"]) for r in logs}
    cursor = date.today() if date.today() in dates else date.today() - timedelta(days=1)
    streak = 0
    while cursor in dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak



def same_cycle_day_compare(periods, logs, target=None):
    """Compare today's cycle day with the same day in prior tracked cycles."""
    target = target or date.today()
    starts = sorted(parse_date(p["start_date"]) for p in periods if parse_date(p["start_date"]) <= target)
    if not starts:
        return {"ready": False, "reason": "Add a period start to unlock cycle comparisons."}
    current_start = starts[-1]
    cycle_day = (target - current_start).days + 1
    log_map = {parse_date(r["log_date"]): dict(r) for r in logs}
    current_log = log_map.get(target)
    prior = []
    for start in reversed(starts[:-1]):
        match_date = start + timedelta(days=cycle_day - 1)
        next_starts = [x for x in starts if x > start]
        if next_starts and match_date >= min(next_starts):
            continue
        prior.append({"cycle_start": start, "date": match_date, "log": log_map.get(match_date)})
        if len(prior) >= 4:
            break
    if not prior:
        return {"ready": False, "reason": "Track another cycle to compare the same cycle day."}

    fields = [("energy", "Energy", "higher"), ("pain", "Pain", "lower"), ("stress", "Stress", "lower"), ("sleep_hours", "Sleep", "higher")]
    metrics = []
    for key, label, favorable in fields:
        now = None if not current_log or current_log.get(key) in (None, "") else float(current_log[key])
        vals = [float(x["log"][key]) for x in prior if x["log"] and x["log"].get(key) not in (None, "")]
        prev = round(statistics.mean(vals), 1) if vals else None
        delta = round(now - prev, 1) if now is not None and prev is not None else None
        metrics.append({"key": key, "label": label, "now": now, "previous": prev, "delta": delta, "favorable": favorable})
    return {
        "ready": True, "cycle_day": cycle_day, "current_date": target, "current_log": current_log,
        "previous": prior[0], "prior": prior, "metrics": metrics,
    }


def pattern_discoveries(periods, logs):
    """Generate descriptive, non-diagnostic observations from self-reported history."""
    if len(logs) < 5:
        return [{"icon": "✦", "title": "Keep checking in", "text": "Five or more check-ins will unlock personal pattern observations.", "sample": len(logs), "tone": "neutral"}]
    cards = []
    log_rows = [dict(r) for r in logs]
    log_by_date = {parse_date(r["log_date"]): r for r in log_rows}

    # Symptoms in the three days before tracked periods.
    pre = Counter(); pre_days = 0
    for p in periods:
        start = parse_date(p["start_date"])
        for off in (1, 2, 3):
            row = log_by_date.get(start - timedelta(days=off))
            if row:
                pre_days += 1
                pre.update(x.strip() for x in (row.get("symptoms") or "").split(",") if x.strip())
    if pre:
        symptom, count = pre.most_common(1)[0]
        cards.append({"icon": "◌", "title": "Before your period", "text": f"{symptom} appeared {count} time(s) in check-ins from the three days before a tracked period.", "sample": pre_days, "tone": "rose"})

    # Phase averages.
    phase_vals = {}
    for r in log_rows:
        ph = cycle_phase(periods, parse_date(r["log_date"]))["name"]
        if ph in {"Not enough data", "Cycle timing unclear"}: continue
        bucket = phase_vals.setdefault(ph, {"energy": [], "pain": [], "stress": [], "sleep": []})
        for src, dst in [("energy","energy"),("pain","pain"),("stress","stress"),("sleep_hours","sleep")]:
            if r.get(src) not in (None, ""):
                bucket[dst].append(float(r[src]))
    energy_phase = [(ph, statistics.mean(v["energy"]), len(v["energy"])) for ph,v in phase_vals.items() if v["energy"]]
    if len(energy_phase) >= 2:
        low = min(energy_phase, key=lambda x:x[1]); high = max(energy_phase, key=lambda x:x[1])
        cards.append({"icon": "↕", "title": "Energy rhythm", "text": f"Your logged energy averaged {low[1]:.1f}/10 during {low[0]} and {high[1]:.1f}/10 during {high[0]}.", "sample": low[2]+high[2], "tone": "violet"})

    # Sleep on high-stress vs lower-stress days.
    high_sleep = [float(r["sleep_hours"]) for r in log_rows if r.get("sleep_hours") not in (None, "") and float(r.get("stress") or 0) >= 7]
    lower_sleep = [float(r["sleep_hours"]) for r in log_rows if r.get("sleep_hours") not in (None, "") and float(r.get("stress") or 0) <= 4]
    if len(high_sleep) >= 2 and len(lower_sleep) >= 2:
        a,b=statistics.mean(high_sleep),statistics.mean(lower_sleep)
        cards.append({"icon": "☾", "title": "Sleep × stress", "text": f"On high-stress check-ins you logged {a:.1f}h sleep on average, compared with {b:.1f}h on lower-stress days.", "sample": len(high_sleep)+len(lower_sleep), "tone": "blue"})

    # Mood leader.
    moods = Counter(r.get("mood") for r in log_rows if r.get("mood"))
    if moods:
        mood, count = moods.most_common(1)[0]
        cards.append({"icon": "♡", "title": "Most logged mood", "text": f"{mood} is your most common recent mood ({count} check-ins).", "sample": sum(moods.values()), "tone": "pink"})

    return cards[:6]


def universe_timeline(periods, logs, journal_entries, limit=16):
    events=[]
    for p in periods[-8:]:
        events.append({"date": p["start_date"], "kind":"period", "icon":"●", "title":"Period started", "detail":f"{p['flow'].title()} flow"})
        if p["end_date"]:
            events.append({"date": p["end_date"], "kind":"period-end", "icon":"○", "title":"Period ended", "detail":"Cycle history updated"})
    for r in logs[-30:]:
        detail=[]
        if r["mood"]: detail.append(r["mood"])
        detail.append(f"energy {r['energy']}/10")
        if r["symptoms"]: detail.append((r["symptoms"].split(",")[0]))
        events.append({"date":r["log_date"],"kind":"checkin","icon":"✦","title":"Daily check-in","detail":" · ".join(detail)})
    for j in journal_entries[-20:]:
        events.append({"date":j["entry_date"],"kind":"journal","icon":"◇","title":j["title"] or "Journal entry","detail":j["vibe"] or "Private reflection"})
    events.sort(key=lambda e:e["date"], reverse=True)
    return events[:limit]


ZODIAC = [
    ("Aries", "♈", "Fire", "Cardinal"), ("Taurus", "♉", "Earth", "Fixed"),
    ("Gemini", "♊", "Air", "Mutable"), ("Cancer", "♋", "Water", "Cardinal"),
    ("Leo", "♌", "Fire", "Fixed"), ("Virgo", "♍", "Earth", "Mutable"),
    ("Libra", "♎", "Air", "Cardinal"), ("Scorpio", "♏", "Water", "Fixed"),
    ("Sagittarius", "♐", "Fire", "Mutable"), ("Capricorn", "♑", "Earth", "Cardinal"),
    ("Aquarius", "♒", "Air", "Fixed"), ("Pisces", "♓", "Water", "Mutable"),
]
PLANETS = [
    ("Sun", "☉", swe.SUN), ("Moon", "☽", swe.MOON), ("Mercury", "☿", swe.MERCURY),
    ("Venus", "♀", swe.VENUS), ("Mars", "♂", swe.MARS), ("Jupiter", "♃", swe.JUPITER),
    ("Saturn", "♄", swe.SATURN), ("Uranus", "♅", swe.URANUS),
    ("Neptune", "♆", swe.NEPTUNE), ("Pluto", "♇", swe.PLUTO),
]


def zodiac_position(longitude):
    lon = longitude % 360
    idx = int(lon // 30)
    degree = lon % 30
    name, symbol, element, modality = ZODIAC[idx]
    return {"name": name, "symbol": symbol, "degree": degree, "element": element, "modality": modality}


def jd_for_date(d, hour=12.0):
    return swe.julday(d.year, d.month, d.day, hour)


def planet_positions(d, hour=12.0):
    jd = jd_for_date(d, hour)
    out = []
    for name, symbol, body in PLANETS:
        values, _ = swe.calc_ut(jd, body, swe.FLG_MOSEPH | swe.FLG_SPEED)
        lon, speed = values[0], values[3]
        z = zodiac_position(lon)
        out.append({
            "name": name, "symbol": symbol, "longitude": lon,
            "sign": z["name"], "sign_symbol": z["symbol"], "degree": z["degree"],
            "element": z["element"], "modality": z["modality"], "retrograde": speed < 0,
        })
    return out


def moon_phase_info(d, hour=12.0):
    jd = jd_for_date(d, hour)
    sun, _ = swe.calc_ut(jd, swe.SUN, swe.FLG_MOSEPH)
    moon, _ = swe.calc_ut(jd, swe.MOON, swe.FLG_MOSEPH)
    angle = (moon[0] - sun[0]) % 360
    illumination = (1 - math.cos(math.radians(angle))) / 2
    phases = [
        (22.5, "New Moon", "🌑"), (67.5, "Waxing Crescent", "🌒"),
        (112.5, "First Quarter", "🌓"), (157.5, "Waxing Gibbous", "🌔"),
        (202.5, "Full Moon", "🌕"), (247.5, "Waning Gibbous", "🌖"),
        (292.5, "Last Quarter", "🌗"), (337.5, "Waning Crescent", "🌘"),
        (360.0, "New Moon", "🌑"),
    ]
    phase_name, icon = "New Moon", "🌑"
    for limit, name, ico in phases:
        if angle < limit:
            phase_name, icon = name, ico
            break
    moon_z = zodiac_position(moon[0])
    return {
        "angle": angle, "illumination": round(illumination * 100), "name": phase_name,
        "icon": icon, "sign": moon_z["name"], "sign_symbol": moon_z["symbol"],
        "degree": moon_z["degree"],
    }


def natal_positions(birth_date, birth_time=None):
    hour = 12.0
    if birth_time:
        try:
            hh, mm = map(int, birth_time.split(":")[:2])
            hour = hh + mm / 60.0
        except Exception:
            pass
    return planet_positions(birth_date, hour)


def _signed_angle(deg):
    return ((deg + 180.0) % 360.0) - 180.0


def _moon_sun_angle_jd(jd):
    sun, _ = swe.calc_ut(jd, swe.SUN, swe.FLG_MOSEPH)
    moon, _ = swe.calc_ut(jd, swe.MOON, swe.FLG_MOSEPH)
    return (moon[0] - sun[0]) % 360.0


def next_lunar_phase(target_angle, start_dt=None):
    """Return next phase crossing as an aware UTC datetime."""
    start_dt = start_dt or datetime.now(timezone.utc)
    start_dt = start_dt.astimezone(timezone.utc)
    hour = start_dt.hour + start_dt.minute / 60 + start_dt.second / 3600
    start_jd = swe.julday(start_dt.year, start_dt.month, start_dt.day, hour)
    angle = _moon_sun_angle_jd(start_jd)
    delta = (target_angle - angle) % 360.0
    if delta < 0.08:
        delta += 360.0
    jd = start_jd + delta / 12.19075
    for _ in range(8):
        a = _moon_sun_angle_jd(jd)
        err = _signed_angle(a - target_angle)
        eps = 0.025
        ap = _moon_sun_angle_jd(jd + eps)
        am = _moon_sun_angle_jd(jd - eps)
        speed = _signed_angle(ap - am) / (2 * eps)
        if abs(speed) < 0.1:
            break
        jd -= err / speed
    if jd <= start_jd:
        jd += 29.530588853
    y, m, d, h = swe.revjul(jd, swe.GREG_CAL)
    hh = int(h); mmf = (h - hh) * 60; mm = int(mmf); ss = int(round((mmf - mm) * 60))
    if ss >= 60: ss=0; mm += 1
    if mm >= 60: mm=0; hh += 1
    base = datetime(y, m, d, tzinfo=timezone.utc) + timedelta(hours=hh, minutes=mm, seconds=ss)
    return base


def _fmt_clock(dt):
    return dt.strftime("%I:%M %p").lstrip("0")


def lunar_event_pack(start_dt=None, tz_name='UTC'):
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz = timezone.utc
    events=[]
    for name, angle, symbol in [
        ('New Moon', 0.0, '●'), ('First Quarter', 90.0, '◐'),
        ('Full Moon', 180.0, '○'), ('Last Quarter', 270.0, '◑')
    ]:
        dt = next_lunar_phase(angle, start_dt).astimezone(tz)
        events.append({'name':name,'symbol':symbol,'iso':dt.isoformat(),'date':dt.strftime('%b %d'),'time':_fmt_clock(dt)})
    events.sort(key=lambda x:x['iso'])
    return events


def _jd_from_utc(dt):
    dt = dt.astimezone(timezone.utc)
    h = dt.hour + dt.minute/60 + dt.second/3600 + dt.microsecond/3600000000
    return swe.julday(dt.year, dt.month, dt.day, h)


def _dt_from_jd(jd):
    y,m,d,h = swe.revjul(jd, swe.GREG_CAL)
    return datetime(y,m,d,tzinfo=timezone.utc) + timedelta(hours=h)


def _event_local(day, tz, lat, lon, body, rise=True, horizon=None):
    local_midnight = datetime(day.year, day.month, day.day, tzinfo=tz)
    jd0 = _jd_from_utc(local_midnight.astimezone(timezone.utc))
    mode = swe.CALC_RISE if rise else swe.CALC_SET
    try:
        if horizon is None:
            res, tret = swe.rise_trans(jd0, body, mode, (lon, lat, 0.0), 0.0, 10.0, swe.FLG_MOSEPH)
        else:
            mode |= swe.BIT_DISC_CENTER | swe.BIT_NO_REFRACTION
            res, tret = swe.rise_trans_true_hor(jd0, body, mode, (lon, lat, 0.0), 0.0, 10.0, horizon, swe.FLG_MOSEPH)
        if res != 0:
            return None
        local = _dt_from_jd(tret[0]).astimezone(tz)
        if local.date() != day:
            return None
        return local
    except Exception:
        return None


BRIGHT_STARS = [
    ('Sirius','Canis Major',6.7525,-16.7161,-1.46), ('Canopus','Carina',6.3992,-52.6957,-0.74),
    ('Arcturus','Boötes',14.2610,19.1824,-0.05), ('Vega','Lyra',18.6156,38.7837,0.03),
    ('Capella','Auriga',5.2782,45.9980,0.08), ('Rigel','Orion',5.2423,-8.2016,0.13),
    ('Procyon','Canis Minor',7.6550,5.2250,0.34), ('Betelgeuse','Orion',5.9195,7.4071,0.42),
    ('Altair','Aquila',19.8464,8.8683,0.76), ('Aldebaran','Taurus',4.5987,16.5093,0.86),
    ('Spica','Virgo',13.4199,-11.1614,0.97), ('Antares','Scorpius',16.4901,-26.4320,0.96),
    ('Pollux','Gemini',7.7553,28.0262,1.14), ('Fomalhaut','Piscis Austrinus',22.9608,-29.6222,1.16),
    ('Deneb','Cygnus',20.6905,45.2803,1.25), ('Regulus','Leo',10.1395,11.9672,1.35),
    ('Castor','Gemini',7.5767,31.8883,1.58), ('Polaris','Ursa Minor',2.5303,89.2641,1.98),
]


def _star_alt_az(dt_utc, lat, lon, ra_hours, dec_deg):
    jd = _jd_from_utc(dt_utc)
    t = (jd - 2451545.0) / 36525.0
    gmst = (280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933*t*t - t*t*t/38710000.0) % 360
    lst = (gmst + lon) % 360
    ha = math.radians(_signed_angle(lst - ra_hours*15.0))
    latr = math.radians(lat); decr = math.radians(dec_deg)
    alt = math.asin(math.sin(latr)*math.sin(decr)+math.cos(latr)*math.cos(decr)*math.cos(ha))
    az = math.atan2(-math.sin(ha)*math.cos(decr), math.sin(decr)*math.cos(latr)-math.cos(decr)*math.sin(latr)*math.cos(ha))
    return math.degrees(alt), (math.degrees(az)+360)%360


def _moon_altitude(dt_utc, lat, lon):
    jd=_jd_from_utc(dt_utc)
    vals,_=swe.calc_ut(jd,swe.MOON,swe.FLG_MOSEPH|swe.FLG_EQUATORIAL)
    ra_hours=vals[0]/15.0; dec=vals[1]
    return _star_alt_az(dt_utc,lat,lon,ra_hours,dec)[0]


def sky_snapshot(lat, lon, tz_name):
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('Coordinates out of range')
    try:
        tz=ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz=timezone.utc; tz_name='UTC'
    now_utc=datetime.now(timezone.utc); now=now_utc.astimezone(tz); day=now.date()
    sunrise=_event_local(day,tz,lat,lon,swe.SUN,True)
    sunset=_event_local(day,tz,lat,lon,swe.SUN,False)
    astro_dawn=_event_local(day,tz,lat,lon,swe.SUN,True,-18.0)
    astro_dusk=_event_local(day,tz,lat,lon,swe.SUN,False,-18.0)
    moonrise=_event_local(day,tz,lat,lon,swe.MOON,True)
    moonset=_event_local(day,tz,lat,lon,swe.MOON,False)
    moon=moon_phase_info(day, now.hour+now.minute/60)

    if astro_dawn and now < astro_dawn: state='stars'
    elif sunrise and now < sunrise: state='dawn'
    elif sunrise and now < sunrise+timedelta(minutes=55): state='sunrise'
    elif sunset and now < sunset-timedelta(minutes=55): state='day'
    elif sunset and now < sunset: state='golden'
    elif astro_dusk and now < astro_dusk: state='twilight'
    else: state='stars'

    view_local=datetime(day.year,day.month,day.day,22,0,tzinfo=tz)
    if now.hour >= 20:
        view_local=now.replace(second=0,microsecond=0)
    stars=[]
    for name,constellation,ra,dec,mag in BRIGHT_STARS:
        alt,az=_star_alt_az(view_local.astimezone(timezone.utc),lat,lon,ra,dec)
        if alt > 5:
            stars.append({'name':name,'constellation':constellation,'altitude':round(alt,1),'azimuth':round(az,1),'magnitude':mag})
    stars.sort(key=lambda x:x['magnitude'])
    view_utc=view_local.astimezone(timezone.utc)
    view_jd=_jd_from_utc(view_utc)
    visible_planets=[]
    for pname, psymbol, body in [("Venus","♀",swe.VENUS),("Jupiter","♃",swe.JUPITER),("Mars","♂",swe.MARS),("Saturn","♄",swe.SATURN),("Mercury","☿",swe.MERCURY)]:
        try:
            vals,_=swe.calc_ut(view_jd,body,swe.FLG_MOSEPH|swe.FLG_EQUATORIAL)
            alt,az=_star_alt_az(view_utc,lat,lon,vals[0]/15.0,vals[1])
            mag=swe.pheno_ut(view_jd,body,swe.FLG_MOSEPH)[4]
            if alt>5:
                visible_planets.append({"name":pname,"symbol":psymbol,"altitude":round(alt,1),"azimuth":round(az,1),"magnitude":round(mag,1)})
        except Exception:
            pass
    visible_planets.sort(key=lambda x:x["magnitude"])
    moon_alt=_moon_altitude(view_utc,lat,lon)
    score=max(5,round(100 - moon['illumination']*.55 - (18 if moon_alt>0 else 0)))
    if score>=75: quality='Excellent dark-sky potential'
    elif score>=55: quality='Good stargazing potential'
    elif score>=35: quality='Fair — moonlight may wash out faint stars'
    else: quality='Bright moon — best for planets and bright stars'

    def pack(dt):
        return None if not dt else {'iso':dt.isoformat(),'time':_fmt_clock(dt)}
    tomorrow=day+timedelta(days=1)
    next_dawn=_event_local(tomorrow,tz,lat,lon,swe.SUN,True,-18.0) if not astro_dawn or now>astro_dawn else astro_dawn
    dark_start=astro_dusk if astro_dusk and astro_dusk>now else None
    if state=='stars': dark_start=now

    return {
        'timezone':tz_name,'local_now':now.isoformat(),'date':day.isoformat(),'state':state,
        'sunrise':pack(sunrise),'sunset':pack(sunset),'astronomical_dawn':pack(astro_dawn),'astronomical_dusk':pack(astro_dusk),
        'moonrise':pack(moonrise),'moonset':pack(moonset),'moon':moon,
        'lunar_events':lunar_event_pack(now_utc,tz_name),
        'stars':stars[:14],'planets':visible_planets,'view_time':_fmt_clock(view_local),'moon_altitude':round(moon_alt,1),
        'stargazing_score':score,'stargazing_quality':quality,'dark_start':pack(dark_start),'dark_end':pack(next_dawn),
        'day_length_minutes': round((sunset-sunrise).total_seconds()/60) if sunrise and sunset else None,
        'location_note':'Coordinates are used for this calculation only and are not saved by Lunelle.'
    }


@app.template_filter("todate")
def todate_filter(value):
    return parse_date(value) if value else None


@app.route("/")
def index():
    # Lunelle behaves like an app, not a marketing site.
    return redirect(url_for("dashboard") if session.get("user_id") else url_for("login"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(username) < 2:
            flash("Username must be at least 2 characters.", "error")
            return render_template("signup.html", username=username)
        if any(ch.isspace() for ch in username):
            flash("Username cannot contain spaces.", "error")
            return render_template("signup.html", username=username)
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("signup.html", username=username)
        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("signup.html", username=username)

        conn = db()
        try:
            existing = conn.execute(
                "SELECT id FROM users WHERE lower(username)=lower(?) LIMIT 1",
                (username,)
            ).fetchone()
            if existing:
                flash("That username already exists. Try logging in.", "error")
                return render_template("signup.html", username=username)

            # Keep the legacy email column populated for database compatibility,
            # but Lunelle no longer asks for, displays, or authenticates with email.
            import secrets
            internal_email = f"local-{secrets.token_hex(12)}@lunelle.invalid"
            cur = conn.execute(
                "INSERT INTO users(username,email,password_hash,display_name,onboarding_complete) VALUES(?,?,?,?,1)",
                (username, internal_email, generate_password_hash(password), username)
            )
            conn.commit()
            session.clear()
            session.permanent = True
            session["user_id"] = cur.lastrowid
            session["username"] = username
            session["display_name"] = username
            session["unlocked"] = True
            flash("Account created. Welcome to Lunelle.", "success")
            return redirect(url_for("dashboard"))
        except sqlite3.IntegrityError:
            flash("That username already exists.", "error")
        finally:
            conn.close()
    return render_template("signup.html")


@app.route("/pricing")
def pricing():
    return render_template("pricing.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/onboarding", methods=["GET", "POST"])
@login_required
def onboarding():
    conn = db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()[:40]
        focus = request.form.get("focus", "cycle").strip()
        if focus not in {"cycle", "wellness", "cosmos", "privacy"}:
            focus = "cycle"
        conn.execute(
            "UPDATE users SET display_name=?, focus=?, onboarding_complete=1 WHERE id=?",
            (display_name or user["username"], focus, session["user_id"])
        )
        conn.commit()
        conn.close()
        if display_name:
            session["display_name"] = display_name
        flash("Your Lunelle space is ready.", "success")
        return redirect(url_for("dashboard"))
    conn.close()
    return render_template("onboarding.html", user=user)


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", request.form.get("identifier", "")).strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("Enter your username and password.", "error")
            return render_template("login.html", username=username)

        conn = db()
        user = conn.execute(
            "SELECT * FROM users WHERE lower(username)=lower(?) LIMIT 1",
            (username,)
        ).fetchone()
        conn.close()
        if not user:
            flash("That username was not found on this Lunelle installation.", "error")
            return render_template("login.html", username=username)
        if not check_password_hash(user["password_hash"], password):
            flash("Wrong password. Try again or use local reset.", "error")
            return render_template("login.html", username=username)

        session.clear()
        session.permanent = True
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["display_name"] = user["display_name"] or user["username"]
        session["unlocked"] = not bool(user["lock_enabled"])
        return redirect(url_for("unlock") if user["lock_enabled"] else url_for("dashboard"))
    return render_template("login.html")


def _is_local_request():
    # Local recovery is intentionally unavailable to remote visitors.
    host = (request.remote_addr or "").split("%")[0]
    return host in {"127.0.0.1", "::1"}


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if not _is_local_request():
        flash("Password reset is only available directly on the computer running Lunelle.", "error")
        return redirect(url_for("login"))
    identifier = request.form.get("identifier", "").strip() if request.method == "POST" else ""
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(password) < 8:
            flash("New password must be at least 8 characters.", "error")
            return render_template("reset_password.html", identifier=identifier)
        if password != confirm:
            flash("The two new passwords do not match.", "error")
            return render_template("reset_password.html", identifier=identifier)
        conn = db()
        user = conn.execute("SELECT id,username FROM users WHERE lower(username)=lower(?) LIMIT 1", (identifier,)).fetchone()
        if not user:
            conn.close()
            flash("No local account matched that username.", "error")
            return render_template("reset_password.html", identifier=identifier)
        conn.execute("UPDATE users SET password_hash=?, lock_enabled=0, lock_pin_hash=NULL WHERE id=?", (generate_password_hash(password), user["id"]))
        conn.commit(); conn.close()
        session.clear()
        flash("Password reset. You can log in now.", "success")
        return redirect(url_for("login"))
    return render_template("reset_password.html", identifier=identifier)


@app.route("/unlock", methods=["GET", "POST"])
def unlock():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    conn = db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    conn.close()
    if not user or not user["lock_enabled"]:
        session["unlocked"] = True
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        pin = request.form.get("pin", "")
        if user["lock_pin_hash"] and check_password_hash(user["lock_pin_hash"], pin):
            session["unlocked"] = True
            return redirect(url_for("dashboard"))
        flash("That PIN didn't match.", "error")
    return render_template("unlock.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    conn = db()
    periods = conn.execute("SELECT * FROM periods WHERE user_id=? ORDER BY start_date", (session["user_id"],)).fetchall()
    recent_logs = conn.execute("SELECT * FROM daily_logs WHERE user_id=? ORDER BY log_date DESC LIMIT 21", (session["user_id"],)).fetchall()
    all_logs = conn.execute("SELECT * FROM daily_logs WHERE user_id=? ORDER BY log_date LIMIT 240", (session["user_id"],)).fetchall()
    journal_entries = conn.execute("SELECT * FROM journal_entries WHERE user_id=? ORDER BY entry_date,id LIMIT 120", (session["user_id"],)).fetchall()
    today_log = conn.execute("SELECT * FROM daily_logs WHERE user_id=? AND log_date=?", (session["user_id"], date.today().isoformat())).fetchone()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    meds = medication_status(conn, session["user_id"])
    products = conn.execute("SELECT * FROM product_inventory WHERE user_id=? ORDER BY quantity ASC,name", (session["user_id"],)).fetchall()
    journal_count = conn.execute("SELECT COUNT(*) AS n FROM journal_entries WHERE user_id=?", (session["user_id"],)).fetchone()["n"]
    conn.close()

    stats = cycle_stats(periods)
    phase = cycle_phase(periods)
    moon = moon_phase_info(date.today())
    lunar_events = lunar_event_pack(datetime.now(timezone.utc), 'UTC')
    streak = checkin_streak(recent_logs)
    reminders = []
    if not today_log and user["reminder_daily_log"]:
        reminders.append({"icon": "✦", "text": "Your daily check-in is still open."})
    if stats.get("days_until") is not None and 0 <= stats["days_until"] <= (user["reminder_period_days"] or 3):
        reminders.append({"icon": "◌", "text": f"Your next period is estimated in about {stats['days_until']} day(s)."})
    untaken = [m for m in meds if not m["taken_today"]]
    if untaken:
        reminders.append({"icon": "＋", "text": f"{len(untaken)} medication reminder(s) still open today."})
    low_stock = [dict(p) for p in products if int(p["quantity"] or 0) <= int(p["low_at"] or 0)]
    if low_stock:
        reminders.append({"icon": "◇", "text": f"{len(low_stock)} period-care item(s) are running low."})

    goals = {
        "sleep_goal": user["sleep_goal"] or 8, "hydration_goal": user["hydration_goal"] or 8,
        "sleep": float(today_log["sleep_hours"]) if today_log and today_log["sleep_hours"] is not None else 0,
        "water": int(today_log["hydration"]) if today_log else 0,
    }
    score = wellness_score(today_log, goals["sleep_goal"], goals["hydration_goal"])
    ritual = ritual_for(phase, today_log)
    forecast = []
    for offset in range(7):
        d = date.today() + timedelta(days=offset)
        ph = cycle_phase(periods, d)
        mn = moon_phase_info(d)
        forecast.append({"date": d, "label": "Today" if offset == 0 else d.strftime("%a"), "phase": ph, "moon": mn})

    universe_days = []
    for offset in range(-14, 22):
        d = date.today() + timedelta(days=offset)
        ph = cycle_phase(periods, d)
        mn = moon_phase_info(d)
        universe_days.append({
            "offset": offset, "date": d.isoformat(), "label": d.strftime("%a · %b %-d") if os.name != "nt" else d.strftime("%a · %b %d").replace(" 0", " "),
            "phase": ph["name"], "phase_icon": ph["icon"], "cycle_day": ph.get("day"),
            "moon": mn["name"], "moon_icon": mn["icon"], "illumination": mn["illumination"],
            "moon_sign": mn["sign"],
        })
    compare = same_cycle_day_compare(periods, all_logs)
    discoveries = pattern_discoveries(periods, all_logs)
    timeline = universe_timeline(periods, all_logs, journal_entries)

    return render_template(
        "dashboard.html", periods=periods, recent_logs=recent_logs, stats=stats,
        phase=phase, moon=moon, streak=streak, reminders=reminders, meds=meds, goals=goals,
        score=score, ritual=ritual, forecast=forecast, low_stock=low_stock, journal_count=journal_count,
        today_log=today_log, today=date.today().isoformat(), user=user, lunar_events=lunar_events,
        universe_days=universe_days, compare=compare, discoveries=discoveries[:3], timeline=timeline
    )


@app.route("/mood-pulse", methods=["POST"])
@login_required
def mood_pulse():
    mood = request.form.get("mood", "").strip()[:40]
    allowed = {"Radiant", "Good", "Calm", "Tender", "Low", "Over it"}
    if mood not in allowed:
        return redirect(url_for("dashboard"))
    conn = db()
    conn.execute("""
        INSERT INTO daily_logs(user_id,log_date,mood) VALUES(?,?,?)
        ON CONFLICT(user_id,log_date) DO UPDATE SET mood=excluded.mood
    """, (session["user_id"], date.today().isoformat(), mood))
    conn.commit(); conn.close()
    flash(f"Mood pulse saved: {mood}.", "success")
    return redirect(url_for("dashboard"))


@app.route("/period/start", methods=["POST"])
@login_required
def start_period():
    start_date = request.form["start_date"]
    flow = request.form.get("flow", "medium")
    notes = request.form.get("notes", "")
    conn = db()
    active = conn.execute("SELECT id FROM periods WHERE user_id=? AND end_date IS NULL ORDER BY start_date DESC LIMIT 1", (session["user_id"],)).fetchone()
    if active:
        flash("You already have an active period. End it first.", "error")
    else:
        conn.execute("INSERT INTO periods(user_id,start_date,flow,notes) VALUES(?,?,?,?)", (session["user_id"], start_date, flow, notes))
        conn.commit()
        flash("Period started. 🌷", "success")
    conn.close()
    return redirect(url_for("dashboard"))


@app.route("/period/end/<int:period_id>", methods=["POST"])
@login_required
def end_period(period_id):
    end_date = request.form["end_date"]
    conn = db()
    row = conn.execute("SELECT * FROM periods WHERE id=? AND user_id=?", (period_id, session["user_id"])).fetchone()
    if not row:
        conn.close()
        return "Not found", 404
    if parse_date(end_date) < parse_date(row["start_date"]):
        flash("End date cannot be before start date.", "error")
    else:
        conn.execute("UPDATE periods SET end_date=? WHERE id=? AND user_id=?", (end_date, period_id, session["user_id"]))
        conn.commit()
        flash("Period ended. Your estimates were refreshed.", "success")
    conn.close()
    return redirect(url_for("dashboard"))


@app.route("/log", methods=["GET", "POST"])
@login_required
def daily_log():
    selected = request.args.get("date", date.today().isoformat())
    try:
        parse_date(selected)
    except Exception:
        selected = date.today().isoformat()

    conn = db()
    if request.method == "POST":
        log_date = request.form["log_date"]
        fields = (
            session["user_id"], log_date, request.form.get("mood", ""),
            int(request.form.get("pain", 0)), int(request.form.get("energy", 5)),
            request.form.get("flow", ""), ",".join(request.form.getlist("symptoms")),
            request.form.get("notes", ""), int(request.form.get("stress", 0)),
            float(request.form["sleep_hours"]) if request.form.get("sleep_hours") else None,
            int(request.form.get("hydration", 0)), request.form.get("libido", ""),
            request.form.get("discharge", ""), request.form.get("exercise", ""),
            float(request.form["temperature"]) if request.form.get("temperature") else None,
            request.form.get("medication", "")
        )
        conn.execute("""
            INSERT INTO daily_logs(user_id,log_date,mood,pain,energy,flow,symptoms,notes,stress,sleep_hours,hydration,libido,discharge,exercise,temperature,medication)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id,log_date) DO UPDATE SET
              mood=excluded.mood,pain=excluded.pain,energy=excluded.energy,flow=excluded.flow,
              symptoms=excluded.symptoms,notes=excluded.notes,stress=excluded.stress,
              sleep_hours=excluded.sleep_hours,hydration=excluded.hydration,libido=excluded.libido,
              discharge=excluded.discharge,exercise=excluded.exercise,temperature=excluded.temperature,
              medication=excluded.medication
        """, fields)
        conn.commit()
        conn.close()
        flash("Daily check-in saved. ✨", "success")
        return redirect(url_for("dashboard"))

    existing = conn.execute("SELECT * FROM daily_logs WHERE user_id=? AND log_date=?", (session["user_id"], selected)).fetchone()
    custom = conn.execute("SELECT name FROM custom_symptoms WHERE user_id=? ORDER BY name", (session["user_id"],)).fetchall()
    conn.close()
    base_symptoms = ["Cramps","Headache","Bloating","Back pain","Cravings","Acne","Tender breasts","Fatigue","Nausea","Poor sleep","Spotting","Constipation","Diarrhea","Dizziness","Mood swings","Breast swelling"]
    all_symptoms = base_symptoms + [r["name"] for r in custom if r["name"] not in base_symptoms]
    return render_template("log.html", today=selected, existing=existing, all_symptoms=all_symptoms)


@app.route("/calendar")
@login_required
def cycle_calendar():
    raw = request.args.get("month", date.today().strftime("%Y-%m"))
    try:
        year, month = map(int, raw.split("-"))
        first = date(year, month, 1)
    except Exception:
        first = date.today().replace(day=1)
        year, month = first.year, first.month

    conn = db()
    periods = conn.execute("SELECT * FROM periods WHERE user_id=? ORDER BY start_date", (session["user_id"],)).fetchall()
    logs = conn.execute("SELECT * FROM daily_logs WHERE user_id=?", (session["user_id"],)).fetchall()
    conn.close()

    stats = cycle_stats(periods)
    actual_period_days = set()
    for p in periods:
        s = parse_date(p["start_date"])
        e = parse_date(p["end_date"]) if p["end_date"] else date.today()
        e = min(e, s + timedelta(days=13))
        cursor = s
        while cursor <= e:
            actual_period_days.add(cursor)
            cursor += timedelta(days=1)

    predicted_period_days, fertile_days, ovulation_days = set(), set(), set()
    if periods and stats["avg_cycle"]:
        avg_cycle, avg_period = stats["avg_cycle"], stats["avg_period"] or 5
        anchor = max(parse_date(p["start_date"]) for p in periods)
        for k in range(-12, 13):
            start = anchor + timedelta(days=k * avg_cycle)
            if start not in {parse_date(p["start_date"]) for p in periods}:
                for j in range(avg_period):
                    predicted_period_days.add(start + timedelta(days=j))
            ov = start + timedelta(days=max(10, avg_cycle - 14) - 1)
            ovulation_days.add(ov)
            for j in range(-5, 2):
                fertile_days.add(ov + timedelta(days=j))

    log_map = {parse_date(r["log_date"]): r for r in logs}
    cal = calendar.Calendar(firstweekday=6)
    weeks = []
    for week in cal.monthdatescalendar(year, month):
        row = []
        for d in week:
            moon = moon_phase_info(d)
            row.append({
                "date": d, "in_month": d.month == month, "today": d == date.today(),
                "actual_period": d in actual_period_days,
                "predicted_period": d in predicted_period_days and d not in actual_period_days,
                "fertile": d in fertile_days, "ovulation": d in ovulation_days,
                "log": log_map.get(d), "moon": moon,
            })
        weeks.append(row)

    prev_first = (first - timedelta(days=1)).replace(day=1)
    next_first = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    return render_template(
        "calendar.html", weeks=weeks, month_name=first.strftime("%B %Y"),
        month_value=first.strftime("%Y-%m"), prev_month=prev_first.strftime("%Y-%m"),
        next_month=next_first.strftime("%Y-%m"), stats=stats
    )


@app.route("/insights")
@login_required
def insights():
    conn = db()
    periods = conn.execute("SELECT * FROM periods WHERE user_id=? ORDER BY start_date", (session["user_id"],)).fetchall()
    logs = conn.execute("SELECT * FROM daily_logs WHERE user_id=? ORDER BY log_date", (session["user_id"],)).fetchall()
    conn.close()

    lengths = cycle_lengths(periods)
    variability = round(statistics.stdev(lengths), 1) if len(lengths) >= 2 else None
    consistency = None
    if variability is not None:
        consistency = "Very consistent" if variability <= 2 else "Fairly consistent" if variability <= 5 else "Variable"

    def avg(field):
        vals = [float(r[field]) for r in logs if r[field] is not None and str(r[field]) != ""]
        return round(statistics.mean(vals), 1) if vals else None

    symptoms = Counter()
    moods = Counter()
    for r in logs:
        moods.update([r["mood"]] if r["mood"] else [])
        symptoms.update(x.strip() for x in (r["symptoms"] or "").split(",") if x.strip())

    phase_counts = Counter()
    for r in logs:
        p = cycle_phase(periods, parse_date(r["log_date"]))
        phase_counts[p["name"]] += 1

    trend_logs = [dict(r) for r in logs[-30:]]
    return render_template(
        "insights.html", stats=cycle_stats(periods), variability=variability,
        consistency=consistency, avg_pain=avg("pain"), avg_energy=avg("energy"),
        avg_stress=avg("stress"), avg_sleep=avg("sleep_hours"),
        top_symptoms=symptoms.most_common(8), moods=moods.most_common(),
        phase_counts=phase_counts.most_common(), streak=checkin_streak(logs), log_count=len(logs), trend_logs=trend_logs
    )


@app.route("/compare")
@login_required
def cycle_compare():
    conn = db()
    periods = conn.execute("SELECT * FROM periods WHERE user_id=? ORDER BY start_date", (session["user_id"],)).fetchall()
    logs = conn.execute("SELECT * FROM daily_logs WHERE user_id=? ORDER BY log_date", (session["user_id"],)).fetchall()
    conn.close()
    compare = same_cycle_day_compare(periods, logs)
    stats = cycle_stats(periods)
    phase = cycle_phase(periods)
    moon = moon_phase_info(date.today())
    return render_template("compare.html", compare=compare, stats=stats, phase=phase, moon=moon)


@app.route("/discoveries")
@login_required
def discoveries():
    conn = db()
    periods = conn.execute("SELECT * FROM periods WHERE user_id=? ORDER BY start_date", (session["user_id"],)).fetchall()
    logs = conn.execute("SELECT * FROM daily_logs WHERE user_id=? ORDER BY log_date", (session["user_id"],)).fetchall()
    conn.close()
    cards = pattern_discoveries(periods, logs)
    return render_template("discoveries.html", cards=cards, log_count=len(logs), cycle_count=len(periods), stats=cycle_stats(periods))


@app.route("/wrapped")
@login_required
def wrapped():
    raw_month = request.args.get("month", date.today().strftime("%Y-%m"))
    try:
        year, month = map(int, raw_month.split("-"))
        start = date(year, month, 1)
    except Exception:
        start = date.today().replace(day=1); year, month = start.year, start.month
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    end = next_month - timedelta(days=1)
    conn = db()
    logs = conn.execute("SELECT * FROM daily_logs WHERE user_id=? AND log_date>=? AND log_date<=? ORDER BY log_date", (session["user_id"], start.isoformat(), end.isoformat())).fetchall()
    periods = conn.execute("SELECT * FROM periods WHERE user_id=? ORDER BY start_date", (session["user_id"],)).fetchall()
    journals = conn.execute("SELECT * FROM journal_entries WHERE user_id=? AND entry_date>=? AND entry_date<=? ORDER BY entry_date", (session["user_id"], start.isoformat(), end.isoformat())).fetchall()
    conn.close()
    moods = Counter(r["mood"] for r in logs if r["mood"])
    symptoms = Counter()
    for r in logs:
        symptoms.update(x.strip() for x in (r["symptoms"] or "").split(",") if x.strip())
    def avg(field):
        vals=[float(r[field]) for r in logs if r[field] not in (None,"")]
        return round(statistics.mean(vals),1) if vals else None
    best_energy = max((dict(r) for r in logs), key=lambda r: int(r.get("energy") or 0), default=None)
    checkin_days = {r["log_date"] for r in logs}
    period_starts = [p for p in periods if start <= parse_date(p["start_date"]) <= end]
    stories = [
        {"kicker":"YOUR MONTH", "big": start.strftime("%B"), "title": f"{len(logs)} check-ins", "copy": f"You captured {len(logs)} days of your rhythm and {len(journals)} private journal entr{'y' if len(journals)==1 else 'ies'}.", "kind":"intro"},
        {"kicker":"ENERGY", "big": f"{avg('energy') or '—'}/10", "title":"average energy", "copy": (f"Your brightest logged day was {best_energy['log_date']}." if best_energy else "Keep checking in to see your energy story."), "kind":"energy"},
        {"kicker":"MOOD", "big": moods.most_common(1)[0][0] if moods else "—", "title":"most logged mood", "copy": (f"It appeared in {moods.most_common(1)[0][1]} check-ins." if moods else "Your mood pattern will appear here."), "kind":"mood"},
        {"kicker":"BODY", "big": symptoms.most_common(1)[0][0] if symptoms else "—", "title":"most common symptom", "copy": (f"Logged {symptoms.most_common(1)[0][1]} time(s) this month." if symptoms else "No symptoms dominated this month."), "kind":"body"},
        {"kicker":"REST", "big": f"{avg('sleep_hours') or '—'}h", "title":"average sleep", "copy": f"Average stress was {avg('stress') or '—'}/10 and pain was {avg('pain') or '—'}/10.", "kind":"rest"},
        {"kicker":"RHYTHM", "big": str(len(period_starts)), "title":"period start" if len(period_starts)==1 else "period starts", "copy": f"Your current cycle average is {cycle_stats(periods).get('avg_cycle') or '—'} days.", "kind":"cycle"},
    ]
    return render_template("wrapped.html", stories=stories, month=start.strftime("%B %Y"), month_value=start.strftime("%Y-%m"), has_data=bool(logs or journals or period_starts))


@app.route("/journal", methods=["GET", "POST"])
@login_required
def journal():
    conn = db()
    if request.method == "POST":
        body = request.form.get("body", "").strip()
        if body:
            conn.execute(
                "INSERT INTO journal_entries(user_id,entry_date,title,body,vibe) VALUES(?,?,?,?,?)",
                (session["user_id"], request.form.get("entry_date") or date.today().isoformat(),
                 request.form.get("title", "").strip(), body, request.form.get("vibe", ""))
            )
            conn.commit()
            flash("Journal entry saved privately. ♡", "success")
        entries = conn.execute("SELECT * FROM journal_entries WHERE user_id=? ORDER BY entry_date DESC,id DESC", (session["user_id"],)).fetchall()
        conn.close()
        return redirect(url_for("journal"))
    entries = conn.execute("SELECT * FROM journal_entries WHERE user_id=? ORDER BY entry_date DESC,id DESC", (session["user_id"],)).fetchall()
    conn.close()
    seed_title = (request.args.get("title") or "")[:80]
    seed_prompt = (request.args.get("prompt") or "")[:500]
    seed_vibe = (request.args.get("vibe") or "")[:60]
    return render_template("journal.html", entries=entries, today=date.today().isoformat(), seed_title=seed_title, seed_prompt=seed_prompt, seed_vibe=seed_vibe)


@app.route("/journal/delete/<int:entry_id>", methods=["POST"])
@login_required
def delete_journal(entry_id):
    conn = db()
    conn.execute("DELETE FROM journal_entries WHERE id=? AND user_id=?", (entry_id, session["user_id"]))
    conn.commit()
    conn.close()
    flash("Journal entry deleted.", "success")
    return redirect(url_for("journal"))


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    conn = db()
    if request.method == "POST":
        days = max(0, min(14, int(request.form.get("reminder_period_days", 3))))
        daily = 1 if request.form.get("reminder_daily_log") == "on" else 0
        log_time = request.form.get("reminder_log_time", "20:00")
        sleep_goal = max(1, min(14, float(request.form.get("sleep_goal", 8))))
        hydration_goal = max(1, min(30, int(request.form.get("hydration_goal", 8))))
        conn.execute("UPDATE users SET reminder_period_days=?,reminder_daily_log=?,reminder_log_time=?,sleep_goal=?,hydration_goal=? WHERE id=?", (days, daily, log_time, sleep_goal, hydration_goal, session["user_id"]))
        conn.commit()
        flash("Preferences saved. 🎀", "success")
    user = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    custom_symptoms = conn.execute("SELECT * FROM custom_symptoms WHERE user_id=? ORDER BY name", (session["user_id"],)).fetchall()
    conn.close()
    return render_template("settings.html", user=user, custom_symptoms=custom_symptoms)


@app.route("/settings/symptoms/add", methods=["POST"])
@login_required
def add_custom_symptom():
    name = " ".join(request.form.get("name", "").strip().split())[:40]
    if name:
        conn = db()
        try:
            conn.execute("INSERT OR IGNORE INTO custom_symptoms(user_id,name) VALUES(?,?)", (session["user_id"], name))
            conn.commit()
        finally:
            conn.close()
        flash(f"Added {name} to your check-in list. ✨", "success")
    return redirect(url_for("settings"))


@app.route("/settings/symptoms/delete/<int:symptom_id>", methods=["POST"])
@login_required
def delete_custom_symptom(symptom_id):
    conn = db(); conn.execute("DELETE FROM custom_symptoms WHERE id=? AND user_id=?", (symptom_id, session["user_id"])); conn.commit(); conn.close()
    flash("Custom symptom removed.", "success")
    return redirect(url_for("settings"))


@app.route("/settings/app-lock", methods=["POST"])
@login_required
def app_lock_settings():
    action = request.form.get("action", "enable")
    conn = db()
    if action == "disable":
        conn.execute("UPDATE users SET lock_enabled=0,lock_pin_hash=NULL WHERE id=?", (session["user_id"],))
        session["unlocked"] = True
        flash("App PIN lock disabled.", "success")
    else:
        pin = request.form.get("pin", "")
        if not (pin.isdigit() and 4 <= len(pin) <= 8):
            conn.close(); flash("Use a 4–8 digit PIN.", "error"); return redirect(url_for("settings"))
        conn.execute("UPDATE users SET lock_enabled=1,lock_pin_hash=? WHERE id=?", (generate_password_hash(pin), session["user_id"]))
        session["unlocked"] = True
        flash("App PIN lock enabled. 🔒", "success")
    conn.commit(); conn.close()
    return redirect(url_for("settings"))


@app.route("/lock")
@login_required
def lock_now():
    session["unlocked"] = False
    return redirect(url_for("unlock"))


@app.route("/medications", methods=["GET", "POST"])
@login_required
def medications():
    conn = db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:80]
        if name:
            conn.execute("INSERT INTO medications(user_id,name,dose,schedule_time,notes) VALUES(?,?,?,?,?)", (session["user_id"], name, request.form.get("dose", "")[:80], request.form.get("schedule_time", "20:00"), request.form.get("notes", "")[:300]))
            conn.commit(); flash("Medication reminder added. 💊", "success")
        conn.close(); return redirect(url_for("medications"))
    meds = medication_status(conn, session["user_id"])
    conn.close()
    return render_template("medications.html", meds=meds, today=date.today().isoformat())


@app.route("/medications/<int:med_id>/taken", methods=["POST"])
@login_required
def medication_taken(med_id):
    conn = db()
    med = conn.execute("SELECT id FROM medications WHERE id=? AND user_id=?", (med_id, session["user_id"])).fetchone()
    if med:
        conn.execute("INSERT INTO medication_logs(user_id,medication_id,log_date,taken) VALUES(?,?,?,1) ON CONFLICT(user_id,medication_id,log_date) DO UPDATE SET taken=1,taken_at=CURRENT_TIMESTAMP", (session["user_id"], med_id, date.today().isoformat()))
        conn.commit(); flash("Marked taken for today. ♡", "success")
    conn.close(); return redirect(request.referrer or url_for("medications"))


@app.route("/medications/<int:med_id>/delete", methods=["POST"])
@login_required
def medication_delete(med_id):
    conn = db(); conn.execute("DELETE FROM medication_logs WHERE user_id=? AND medication_id=?", (session["user_id"], med_id)); conn.execute("DELETE FROM medications WHERE id=? AND user_id=?", (med_id, session["user_id"])); conn.commit(); conn.close()
    flash("Medication reminder removed.", "success")
    return redirect(url_for("medications"))


@app.route("/products", methods=["GET", "POST"])
@login_required
def products():
    conn = db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:80]
        if name:
            try:
                quantity = max(0, int(request.form.get("quantity", 0)))
                low_at = max(0, int(request.form.get("low_at", 3)))
            except ValueError:
                quantity, low_at = 0, 3
            conn.execute("INSERT INTO product_inventory(user_id,name,category,quantity,low_at,notes) VALUES(?,?,?,?,?,?)",
                         (session["user_id"], name, request.form.get("category", "Period care")[:40], quantity, low_at, request.form.get("notes", "")[:240]))
            conn.commit(); flash("Added to your care cabinet.", "success")
        conn.close(); return redirect(url_for("products"))
    items = conn.execute("SELECT * FROM product_inventory WHERE user_id=? ORDER BY quantity ASC,name", (session["user_id"],)).fetchall()
    conn.close()
    return render_template("products.html", items=items)


@app.route("/products/<int:item_id>/adjust", methods=["POST"])
@login_required
def product_adjust(item_id):
    try: delta = int(request.form.get("delta", 0))
    except ValueError: delta = 0
    conn = db()
    item = conn.execute("SELECT quantity FROM product_inventory WHERE id=? AND user_id=?", (item_id, session["user_id"])).fetchone()
    if item:
        new_q = max(0, int(item["quantity"] or 0) + delta)
        conn.execute("UPDATE product_inventory SET quantity=? WHERE id=? AND user_id=?", (new_q, item_id, session["user_id"]))
        conn.commit()
    conn.close(); return redirect(url_for("products"))


@app.route("/products/<int:item_id>/delete", methods=["POST"])
@login_required
def product_delete(item_id):
    conn = db(); conn.execute("DELETE FROM product_inventory WHERE id=? AND user_id=?", (item_id, session["user_id"])); conn.commit(); conn.close()
    flash("Item removed.", "success")
    return redirect(url_for("products"))


@app.route("/recap")
@login_required
def recap():
    conn = db()
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    logs = conn.execute("SELECT * FROM daily_logs WHERE user_id=? AND log_date>=? ORDER BY log_date", (session["user_id"], cutoff)).fetchall()
    periods = conn.execute("SELECT * FROM periods WHERE user_id=? ORDER BY start_date DESC LIMIT 8", (session["user_id"],)).fetchall()
    journal_count = conn.execute("SELECT COUNT(*) AS n FROM journal_entries WHERE user_id=? AND entry_date>=?", (session["user_id"], cutoff)).fetchone()["n"]
    conn.close()
    moods = Counter(r["mood"] for r in logs if r["mood"])
    symptoms = Counter()
    for r in logs: symptoms.update(x.strip() for x in (r["symptoms"] or "").split(",") if x.strip())
    def avg(field):
        vals=[float(r[field]) for r in logs if r[field] is not None and str(r[field]) != ""]
        return round(statistics.mean(vals),1) if vals else None
    return render_template("recap.html", month=date.today().strftime("%B"), log_count=len(logs), journal_count=journal_count,
                           top_moods=moods.most_common(4), top_symptoms=symptoms.most_common(5), avg_energy=avg("energy"),
                           avg_pain=avg("pain"), avg_sleep=avg("sleep_hours"), stats=cycle_stats(periods), moon=moon_phase_info(date.today()))


@app.route("/doctor-summary")
@login_required
def doctor_summary():
    conn = db()
    periods = conn.execute("SELECT * FROM periods WHERE user_id=? ORDER BY start_date DESC LIMIT 12", (session["user_id"],)).fetchall()
    logs = conn.execute("SELECT * FROM daily_logs WHERE user_id=? ORDER BY log_date DESC LIMIT 90", (session["user_id"],)).fetchall()
    meds = conn.execute("SELECT * FROM medications WHERE user_id=? AND active=1 ORDER BY name", (session["user_id"],)).fetchall()
    conn.close()
    symptoms = Counter()
    for r in logs: symptoms.update(x.strip() for x in (r["symptoms"] or "").split(",") if x.strip())
    def av(field):
        vals=[float(r[field]) for r in logs if r[field] is not None and str(r[field])!=""]
        return round(statistics.mean(vals),1) if vals else None
    return render_template("doctor_summary.html", stats=cycle_stats(periods), periods=periods, meds=meds, top_symptoms=symptoms.most_common(10), avg_pain=av("pain"), avg_energy=av("energy"), avg_sleep=av("sleep_hours"), generated=date.today().isoformat())


@app.route("/sw.js")
def service_worker():
    return send_from_directory(os.path.join(APP_DIR, "static"), "sw.js", mimetype="application/javascript")


@app.route("/history")
@login_required
def history():
    conn = db()
    periods = conn.execute("SELECT * FROM periods WHERE user_id=? ORDER BY start_date DESC", (session["user_id"],)).fetchall()
    logs = conn.execute("SELECT * FROM daily_logs WHERE user_id=? ORDER BY log_date DESC LIMIT 180", (session["user_id"],)).fetchall()
    conn.close()
    return render_template("history.html", periods=periods, logs=logs)


@app.route("/sky")
@login_required
def sky():
    moon = moon_phase_info(date.today())
    lunar_events = lunar_event_pack(datetime.now(timezone.utc), 'UTC')
    return render_template("sky.html", moon=moon, lunar_events=lunar_events)


@app.route("/api/sky")
@login_required
def sky_api():
    try:
        lat=float(request.args.get('lat',''))
        lon=float(request.args.get('lon',''))
        tz_name=(request.args.get('tz') or 'UTC')[:80]
        return jsonify(sky_snapshot(lat,lon,tz_name))
    except (ValueError,TypeError) as exc:
        return jsonify({'error':str(exc) or 'Invalid location'}),400
    except Exception:
        return jsonify({'error':'Sky calculation failed for this location.'}),500


@app.route("/astrology")
@login_required
def astrology():
    raw_date = request.args.get("date", date.today().isoformat())
    try:
        selected = parse_date(raw_date)
    except Exception:
        selected = date.today()
    positions = planet_positions(selected)
    moon = moon_phase_info(selected)

    conn = db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    periods = conn.execute("SELECT * FROM periods WHERE user_id=? ORDER BY start_date DESC LIMIT 18", (session["user_id"],)).fetchall()
    conn.close()

    cycle_moons = []
    for p in periods:
        pd = parse_date(p["start_date"])
        m = moon_phase_info(pd)
        cycle_moons.append({"date": p["start_date"], **m})

    natal, natal_moon = [], None
    if user["birth_date"]:
        bd = parse_date(user["birth_date"])
        natal = natal_positions(bd, user["birth_time"])
        natal_moon = moon_phase_info(bd)

    stats = cycle_stats(periods)
    next_moon = moon_phase_info(parse_date(stats["next_period"])) if stats.get("next_period") else None
    return render_template(
        "astrology.html", selected=selected.isoformat(), positions=positions, moon=moon,
        user=user, natal=natal, natal_moon=natal_moon, cycle_moons=cycle_moons,
        next_moon=next_moon, stats=stats
    )


@app.route("/astrology/profile", methods=["POST"])
@login_required
def astrology_profile():
    birth_date = request.form.get("birth_date") or None
    birth_time = request.form.get("birth_time") or None
    birth_place = request.form.get("birth_place", "").strip() or None
    conn = db()
    conn.execute("UPDATE users SET birth_date=?, birth_time=?, birth_place=? WHERE id=?", (birth_date, birth_time, birth_place, session["user_id"]))
    conn.commit()
    conn.close()
    flash("Astrology profile saved.", "success")
    return redirect(url_for("astrology"))


@app.route("/api/calendar")
@login_required
def calendar_data():
    conn = db()
    periods = conn.execute("SELECT * FROM periods WHERE user_id=? ORDER BY start_date", (session["user_id"],)).fetchall()
    conn.close()
    return jsonify({"periods": [dict(r) for r in periods], "stats": cycle_stats(periods)})


@app.route("/backup.json")
@login_required
def backup_json():
    conn = db()
    uid = session["user_id"]
    payload = {
        "format": "lunelle-backup-v1",
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "periods": [dict(r) for r in conn.execute("SELECT start_date,end_date,flow,notes,created_at FROM periods WHERE user_id=? ORDER BY start_date", (uid,)).fetchall()],
        "daily_logs": [dict(r) for r in conn.execute("SELECT * FROM daily_logs WHERE user_id=? ORDER BY log_date", (uid,)).fetchall()],
        "journal": [dict(r) for r in conn.execute("SELECT entry_date,title,body,vibe,created_at FROM journal_entries WHERE user_id=? ORDER BY entry_date", (uid,)).fetchall()],
        "medications": [dict(r) for r in conn.execute("SELECT name,dose,schedule_time,notes,active,created_at FROM medications WHERE user_id=? ORDER BY name", (uid,)).fetchall()],
        "inventory": [dict(r) for r in conn.execute("SELECT name,category,quantity,low_at,notes,created_at FROM product_inventory WHERE user_id=? ORDER BY name", (uid,)).fetchall()],
    }
    conn.close()
    import json
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    return Response(body, mimetype="application/json", headers={"Content-Disposition":"attachment; filename=lunelle-backup.json"})


@app.route("/export.csv")
@login_required
def export_csv():
    conn = db()
    periods = conn.execute("SELECT start_date,end_date,flow,notes FROM periods WHERE user_id=? ORDER BY start_date", (session["user_id"],)).fetchall()
    logs = conn.execute("SELECT log_date,mood,pain,energy,stress,sleep_hours,hydration,flow,symptoms,libido,discharge,exercise,temperature,medication,notes FROM daily_logs WHERE user_id=? ORDER BY log_date", (session["user_id"],)).fetchall()
    journal_rows = conn.execute("SELECT entry_date,title,vibe,body FROM journal_entries WHERE user_id=? ORDER BY entry_date", (session["user_id"],)).fetchall()
    conn.close()

    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["PERIOD HISTORY"]); w.writerow(["start_date","end_date","flow","notes"])
    for r in periods: w.writerow(list(r))
    w.writerow([]); w.writerow(["DAILY LOGS"])
    w.writerow(["date","mood","pain","energy","stress","sleep_hours","hydration","flow","symptoms","libido","discharge","exercise","temperature","medication","notes"])
    for r in logs: w.writerow(list(r))
    w.writerow([]); w.writerow(["PRIVATE JOURNAL"]); w.writerow(["date","title","vibe","body"])
    for r in journal_rows: w.writerow(list(r))
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=lunelle-data.csv"})


@app.route("/delete-data", methods=["POST"])
@login_required
def delete_data():
    conn = db()
    conn.execute("DELETE FROM daily_logs WHERE user_id=?", (session["user_id"],))
    conn.execute("DELETE FROM periods WHERE user_id=?", (session["user_id"],))
    conn.execute("DELETE FROM journal_entries WHERE user_id=?", (session["user_id"],))
    conn.execute("DELETE FROM medication_logs WHERE user_id=?", (session["user_id"],))
    conn.execute("DELETE FROM medications WHERE user_id=?", (session["user_id"],))
    conn.execute("DELETE FROM custom_symptoms WHERE user_id=?", (session["user_id"],))
    conn.execute("DELETE FROM product_inventory WHERE user_id=?", (session["user_id"],))
    conn.commit(); conn.close()
    flash("Cycle, log, and journal data deleted.", "success")
    return redirect(url_for("dashboard"))


init_db()


def auth_self_test():
    """Exercise signup -> logout -> login against an isolated temporary database."""
    import tempfile
    global DB_PATH
    original_db = DB_PATH
    fd, test_path = tempfile.mkstemp(prefix="lunelle-auth-", suffix=".db")
    os.close(fd)
    try:
        os.unlink(test_path)
        DB_PATH = test_path
        init_db()
        client = app.test_client()
        username = "lunelle_selftest"
        password = "SelfTest!9382"
        r = client.post("/signup", data={"username": username, "password": password, "confirm_password": password}, follow_redirects=False)
        assert r.status_code in (302, 303) and "/dashboard" in r.headers.get("Location", ""), f"signup failed: {r.status_code} {r.headers.get('Location')}"
        client.get("/logout")
        r = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
        assert r.status_code in (302, 303) and "/dashboard" in r.headers.get("Location", ""), f"login failed: {r.status_code} {r.headers.get('Location')}"
        print("AUTH SELF-TEST: PASS")
        return 0
    finally:
        DB_PATH = original_db
        try: os.remove(test_path)
        except OSError: pass


if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        raise SystemExit(auth_self_test())
    app.run(host="0.0.0.0", port=5055, debug=False)
