from functools import wraps
from flask import session, redirect, url_for, abort
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db, init_db
from config import SUCURSAL_NAMES, ADMIN_USER

def seed_users():
    """Create default users if they don't exist."""
    conn = get_db()
    existing = {r['username'] for r in conn.execute('SELECT username FROM usuarios').fetchall()}
    to_create = []
    if ADMIN_USER not in existing:
        to_create.append((ADMIN_USER, generate_password_hash('admin123'), 'admin'))
    for name in SUCURSAL_NAMES:
        if name not in existing:
            pwd = name.lower().replace(' ','') + '123'
            to_create.append((name, generate_password_hash(pwd), 'sucursal'))
    if to_create:
        conn.executemany(
            'INSERT INTO usuarios (username, password_hash, rol) VALUES (?,?,?)',
            to_create
        )
        conn.commit()
    conn.close()

def verify_user(username, password):
    """Returns (username, rol) or None."""
    conn = get_db()
    row = conn.execute('SELECT * FROM usuarios WHERE username=?', (username,)).fetchone()
    conn.close()
    if row and check_password_hash(row['password_hash'], password):
        return row['username'], row['rol']
    return None

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('rol') != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated
