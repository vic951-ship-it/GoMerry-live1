from flask import Flask,request,jsonify,send_file
import sqlite3,os,random
from datetime import datetime
app=Flask(__name__)
BASE=os.path.dirname(os.path.abspath(__file__))
DB=os.path.join(BASE,"gomerry.db")
ADMIN_KEY="merry2025"

# PUT YOUR LIVE PAYPAL CLIENT ID HERE
PAYPAL_CLIENT_ID="YOUR_LIVE_PAYPAL_ID_HERE"

def db():
 c=sqlite3.connect(DB)
 c.row_factory=sqlite3.Row
 return c

def init_db():
 con=db()
 con.executescript("""
 CREATE TABLE IF NOT EXISTS users(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT,phone TEXT UNIQUE,
 range_min INTEGER,range_max INTEGER,
 amount INTEGER,lifetime_amount INTEGER,
 lifetime_paid INTEGER DEFAULT 0,
 paypal_order_id TEXT,
 created_at TEXT);
 CREATE TABLE IF NOT EXISTS groups(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 range_min INTEGER,range_max INTEGER,
 group_number INTEGER,status TEXT DEFAULT 'OPEN',
 total_amount INTEGER DEFAULT 0,
 beneficiary_id INTEGER,created_at TEXT);
 CREATE TABLE IF NOT EXISTS group_members(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 group_id INTEGER,user_id INTEGER,
 amount INTEGER,UNIQUE(group_id,user_id));
 CREATE TABLE IF NOT EXISTS payments(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 phone TEXT, order_id TEXT, type TEXT, amount REAL, created_at TEXT);
 """)
 con.commit()
 con.close()
init_db()

@app.route("/")
def home():
 # inject paypal ID into picker.html
 path=os.path.join(BASE,"picker.html")
 with open(path,"r") as f:
   html=f.read()
 html=html.replace("PAYPAL_CLIENT_ID_PLACEHOLDER", PAYPAL_CLIENT_ID)
 return html

@app.route("/admin")
def admin_page():
 if request.args.get("key")!=ADMIN_KEY:
  return "Add?key=merry2025",403
 return send_file(os.path.join(BASE,"admin.html"))

@app.route("/api/verify_registration",methods=["POST"])
def verify_registration():
 d=request.get_json()
 phone=d.get("phone")
 order_id=d.get("orderID")
 amount=d.get("amount",1)
 # In LIVE mode you should verify with PayPal API using secret
 # For now we trust client + save
 con=db()
 con.execute("INSERT INTO payments(phone,order_id,type,amount,created_at) VALUES(?,?,?,?,?)",(phone,order_id,"REGISTRATION",amount,datetime.now().isoformat()))
 # mark user as paid or create user
 u=con.execute("SELECT * FROM users WHERE phone=?",(phone,)).fetchone()
 if not u:
  con.execute("INSERT INTO users(name,phone,lifetime_paid,paypal_order_id,created_at) VALUES(?,?,1,?,?)",(d.get("name",""),phone,order_id,datetime.now().isoformat()))
 else:
  con.execute("UPDATE users SET lifetime_paid=1, paypal_order_id=? WHERE phone=?",(order_id,phone))
 con.commit()
 con.close()
 return jsonify({"ok":True, "message":"$1 registration paid!"})

@app.route("/api/join",methods=["POST"])
def join():
 d=request.get_json()
 name=d.get("name","").strip()
 phone=d.get("phone","").strip()
 rmin=int(d.get("range_min"))
 rmax=int(d.get("range_max"))
 amt=int(d.get("amount"))

 con=db()
 # CHECK $1 PAID FIRST
 u=con.execute("SELECT * FROM users WHERE phone=?",(phone,)).fetchone()
 if not u or u["lifetime_paid"]==0:
  con.close()
  return jsonify({"error":"Pay $1 registration first with PayPal!"}),400

 if amt<rmin or amt>rmax:
  con.close()
  return jsonify({"error":"Bad amount"}),400
 life=rmax*10

 cur=con.cursor()
 ex=cur.execute("SELECT * FROM users WHERE phone=?",(phone,)).fetchone()
 if ex and ex["lifetime_paid"]==1 and ex["range_min"] is not None:
  # check already in this range group
  g=cur.execute("SELECT g.id FROM groups g JOIN group_members gm ON gm.group_id=g.id WHERE gm.user_id=? AND g.range_min=? AND g.range_max=?",(ex["id"],rmin,rmax)).fetchone()
  if g:
   con.close()
   return jsonify({"error":"Already joined this range"}),400
  uid=ex["id"]
  cur.execute("UPDATE users SET name=?,range_min=?,range_max=?,amount=?,lifetime_amount=? WHERE id=?",(name,rmin,rmax,amt,life,uid))
 else:
  if not ex:
   cur.execute("INSERT INTO users(name,phone,range_min,range_max,amount,lifetime_amount,lifetime_paid,created_at) VALUES(?,?,?,?,?,?,1,?)",(name,phone,rmin,rmax,amt,life,datetime.now().isoformat()))
   uid=cur.lastrowid
  else:
   uid=ex["id"]
   cur.execute("UPDATE users SET name=?,range_min=?,range_max=?,amount=?,lifetime_amount=? WHERE id=?",(name,rmin,rmax,amt,life,uid))

 group=cur.execute("SELECT * FROM groups WHERE range_min=? AND range_max=? AND status='OPEN' ORDER BY id ASC",(rmin,rmax)).fetchone()
 if not group:
  last=cur.execute("SELECT MAX(group_number) as m FROM groups WHERE range_min=? AND range_max=?",(rmin,rmax)).fetchone()["m"]
  num=(last or 0)+1
  cur.execute("INSERT INTO groups(range_min,range_max,group_number,created_at) VALUES(?,?,?,?)",(rmin,rmax,num,datetime.now().isoformat()))
  gid=cur.lastrowid
 else:
  gid=group["id"]
  cnt=cur.execute("SELECT COUNT(*) as c FROM group_members WHERE group_id=?",(gid,)).fetchone()["c"]
  if cnt>=10:
   cur.execute("UPDATE groups SET status='FULL' WHERE id=?",(gid,))
   last=cur.execute("SELECT MAX(group_number) as m FROM groups WHERE range_min=? AND range_max=?",(rmin,rmax)).fetchone()["m"]
   num=(last or 0)+1
   cur.execute("INSERT INTO groups(range_min,range_max,group_number,created_at) VALUES(?,?,?,?)",(rmin,rmax,num,datetime.now().isoformat()))
   gid=cur.lastrowid
 try:
  cur.execute("INSERT INTO group_members(group_id,user_id,amount) VALUES(?,?,?)",(gid,uid,amt))
 except:
  con.close()
  return jsonify({"error":"Already in group"}),400
 total=cur.execute("SELECT SUM(amount) as s FROM group_members WHERE group_id=?",(gid,)).fetchone()["s"] or 0
 cur.execute("UPDATE groups SET total_amount=? WHERE id=?",(total,gid))
 cnt=cur.execute("SELECT COUNT(*) as c FROM group_members WHERE group_id=?",(gid,)).fetchone()["c"]
 ben=None
 if cnt>=10:
  cur.execute("UPDATE groups SET status='FULL' WHERE id=?",(gid,))
  mems=cur.execute("SELECT user_id FROM group_members WHERE group_id=?",(gid,)).fetchall()
  ben_id=random.choice(mems)["user_id"]
  cur.execute("UPDATE groups SET beneficiary_id=? WHERE id=?",(ben_id,gid))
  b=cur.execute("SELECT name FROM users WHERE id=?",(ben_id,)).fetchone()
  ben={"name":b["name"]}
 con.commit()
 ginfo=cur.execute("SELECT * FROM groups WHERE id=?",(gid,)).fetchone()
 con.close()
 return jsonify({"group_number":ginfo["group_number"],"range":f"{rmin}-{rmax}","total":total,"count":cnt,"is_full":cnt>=10,"beneficiary":ben,"lifetime_amount":life})

@app.route("/api/group_status/<int:rmin>/<int:rmax>")
def group_status(rmin,rmax):
 con=db()
 g=con.execute("SELECT * FROM groups WHERE range_min=? AND range_max=? AND status='OPEN' ORDER BY id DESC LIMIT 1",(rmin,rmax)).fetchone()
 if not g:
  con.close()
  return jsonify({"count":0,"total":0})
 cnt=con.execute("SELECT COUNT(*) as c FROM group_members WHERE group_id=?",(g["id"],)).fetchone()["c"]
 ben=None
 if g["beneficiary_id"]:
  b=con.execute("SELECT name FROM users WHERE id=?",(g["beneficiary_id"],)).fetchone()
  ben=b["name"] if b else None
 con.close()
 return jsonify({"count":cnt,"total":g["total_amount"],"status":g["status"],"beneficiary":ben,"group_number":g["group_number"]})

@app.route("/api/admin_data")
def admin_data():
 if request.args.get("key")!=ADMIN_KEY:
  return jsonify({"error":"No"}),403
 con=db()
 users=[dict(r) for r in con.execute("SELECT * FROM users ORDER BY id DESC LIMIT 100").fetchall()]
 groups=[]
 for g in con.execute("SELECT * FROM groups ORDER BY id DESC").fetchall():
  members=[dict(m) for m in con.execute("SELECT u.id,u.name,u.phone,gm.amount FROM group_members gm JOIN users u ON u.id=gm.user_id WHERE gm.group_id=?",(g["id"],)).fetchall()]
  ben=None
  if g["beneficiary_id"]:
   b=con.execute("SELECT name,phone FROM users WHERE id=?",(g["beneficiary_id"],)).fetchone()
   ben=dict(b) if b else None
  groups.append({"group":dict(g),"members":members,"beneficiary":ben})
 con.close()
 return jsonify({"users":users,"groups":groups})

if __name__=="__main__":
 app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5003)))
