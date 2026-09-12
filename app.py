from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3, os, time
from datetime import datetime

app = Flask(__name__, static_folder='.')
CORS(app)
DB = 'gomerry.db'

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY, name TEXT, phone TEXT UNIQUE,
                  paypal_order TEXT, registered_at TIMESTAMP, paid_1 INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS joins
                 (id INTEGER PRIMARY KEY, phone TEXT, name TEXT,
                  range_min INT, range_max INT, amount INT,
                  lifetime_amount INT, group_number INT,
                  joined_at TIMESTAMP, is_beneficiary INT DEFAULT 0)''')
    conn.commit(); conn.close()

init_db()

def get_group_number(rmin, rmax):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT COALESCE(MAX(group_number),0) FROM joins WHERE range_min=? AND range_max=?', (rmin,rmax))
    last_group = c.fetchone()[0]
    if last_group==0:
        return 1
    c.execute('SELECT COUNT(*) FROM joins WHERE range_min=? AND range_max=? AND group_number=?', (rmin,rmax,last_group))
    count = c.fetchone()[0]
    conn.close()
    return last_group+1 if count>=10 else last_group

@app.route('/')
def index(): return send_from_directory('.', 'picker.html')

@app.route('/api/verify_registration', methods=['POST'])
def verify():
    d=request.json
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute('INSERT OR REPLACE INTO users (phone,name,paypal_order,registered_at,paid_1) VALUES (?,?,?,?,1)',
              (d['phone'],d['name'],d.get('orderID',''),datetime.now()))
    conn.commit(); conn.close()
    return jsonify({"ok":True})

@app.route('/api/join', methods=['POST'])
def join():
    d=request.json
    rmin=int(d['range_min']); rmax=int(d['range_max']); amt=int(d['amount'])
    phone=d['phone']; name=d['name']

    # Lifetime: highest in range *10 - ONCE
    lifetime = rmax * 10

    conn=sqlite3.connect(DB); c=conn.cursor()
    # Check if already got lifetime in this range
    c.execute('SELECT lifetime_amount FROM joins WHERE phone=? AND range_min=? AND range_max=? AND is_beneficiary=1', (phone,rmin,rmax))
    if c.fetchone():
        conn.close(); return jsonify({"error":"You already won lifetime $"+str(lifetime)+" in this range! Try different range."})

    gnum = get_group_number(rmin,rmax)
    c.execute('INSERT INTO joins (phone,name,range_min,range_max,amount,lifetime_amount,group_number,joined_at) VALUES (?,?,?,?,?,?,?,?)',
              (phone,name,rmin,rmax,amt,lifetime,gnum,datetime.now()))

    c.execute('SELECT COUNT(*), SUM(amount) FROM joins WHERE range_min=? AND range_max=? AND group_number=?', (rmin,rmax,gnum))
    count,total = c.fetchone()
    total = total or 0

    is_full = count>=10
    beneficiary = None
    if is_full:
        c.execute('SELECT name,phone FROM joins WHERE range_min=? AND range_max=? AND group_number=? ORDER BY id ASC LIMIT 1', (rmin,rmax,gnum))
        ben = c.fetchone()
        if ben:
            c.execute('UPDATE joins SET is_beneficiary=1 WHERE phone=? AND range_min=? AND range_max=? AND group_number=? ORDER BY id ASC LIMIT 1', (ben[1],rmin,rmax,gnum))
            beneficiary = {"name":ben[0],"phone":ben[1],"wins":lifetime}

    conn.commit()

    # Get all members in this range
    c.execute('SELECT name,amount,joined_at FROM joins WHERE range_min=? AND range_max=? AND group_number=? ORDER BY id DESC', (rmin,rmax,gnum))
    members = [{"name":r[0],"amount":r[1],"time":r[2]} for r in c.fetchall()]
    conn.close()

    return jsonify({
        "group_number":gnum, "count":count, "total":total, "range":f"${rmin}-${rmax}",
        "lifetime_amount":lifetime, "your_amount":amt, "is_full":is_full,
        "beneficiary":beneficiary, "members":members
    })

@app.route('/api/group_status/<int:rmin>/<int:rmax>')
def status(rmin,rmax):
    conn=sqlite3.connect(DB); c=conn.cursor()
    gnum = get_group_number(rmin,rmax)
    c.execute('SELECT COUNT(*), SUM(amount) FROM joins WHERE range_min=? AND range_max=? AND group_number=?', (rmin,rmax,gnum))
    count,total = c.fetchone()
    c.execute('SELECT name,amount FROM joins WHERE range_min=? AND range_max=? AND group_number=? ORDER BY id DESC LIMIT 10', (rmin,rmax,gnum))
    members=[{"name":r[0],"amount":r[1]} for r in c.fetchall()]
    conn.close()
    return jsonify({"group_number":gnum,"count":count or 0,"total":total or 0,"members":members})

@app.route('/api/monitor')
def monitor():
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute('SELECT * FROM users ORDER BY id DESC LIMIT 50')
    users=c.fetchall()
    c.execute('SELECT range_min,range_max,group_number,COUNT(*),SUM(amount) FROM joins GROUP BY range_min,range_max,group_number')
    groups=c.fetchall()
    conn.close()
    html="<h1>GoMerry Monitor</h1><h2>Users (paid $1)</h2>"
    for u in users: html+=f"<p>{u[1]} - {u[2]} - {u[4]} - {u[3]}</p>"
    html+="<h2>Groups</h2>"
    for g in groups: html+=f"<p>Range ${g[0]}-${g[1]} Group {g[2]}: {g[3]}/10 members Pool ${g[4]}</p>"
    return html

if __name__=='__main__':
    app.run(host='0.0.0.0',port=int(os.environ.get('PORT',10000)))
