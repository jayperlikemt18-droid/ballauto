#!/usr/bin/env python3
"""ดึงตารางแข่งและราคาจาก api-football แล้วเขียน data.json ให้หน้าเว็บอ่าน"""
import json, os, sys, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone

KEY = os.environ.get("API_FOOTBALL_KEY", "").strip()
BASE = "https://v3.football.api-sports.io"
TH = timezone(timedelta(hours=7))
DAYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
LEAGUES = {  # id: (ธง, ชื่อลีก)
    39: ("🏴󠁧󠁢󠁥󠁮󠁧󠁿", "พรีเมียร์ลีก อังกฤษ"), 78: ("🇩🇪", "บุนเดสลีกา เยอรมัน"),
    135: ("🇮🇹", "เซเรีย อา อิตาลี"), 61: ("🇫🇷", "ลีกเอิง ฝรั่งเศส"),
    140: ("🇪🇸", "ลาลีกา สเปน"), 2: ("🏆", "แชมเปียนส์ลีก"), 3: ("🏆", "ยูโรปาลีก"),
}
MIN_PROB = 0.56
MAX_MATCHES = 30


def api(path, **params):
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"x-apisports-key": KEY})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read().decode("utf-8"))
    if d.get("errors"):
        print("API แจ้ง:", d["errors"])
    return d.get("response", [])


def thai_line(n):
    n = abs(n)
    if n == 0:
        return "เสมอ"
    if (n * 4) % 2 == 0:  # 0.5 ทวีคูณ
        return "%g" % n
    return "%g/%g" % (n - 0.25, n + 0.25)


def find_bet(bookmakers, bet_id):
    for b in bookmakers:
        for bet in b.get("bets", []):
            if bet.get("id") == bet_id:
                return bet.get("values", [])
    return []


def analyse(odds, home, away):
    res = odds[0].get("bookmakers", []) if odds else []
    ou = None
    vals = {v["value"]: float(v["odd"]) for v in find_bet(res, 5)}
    o, u = vals.get("Over 2.5"), vals.get("Under 2.5")
    if o and u:
        po = (1 / o) / ((1 / o) + (1 / u))
        if po >= MIN_PROB:
            ou = {"lab": "สูง 2.5", "pct": round(po * 100)}
        elif 1 - po >= MIN_PROB:
            ou = {"lab": "ต่ำ 2.5", "pct": round((1 - po) * 100)}
    hc = None
    best = None
    for v in find_bet(res, 4):
        if v["value"].startswith("Home "):
            try:
                line = float(v["value"].split()[1])
                odd = float(v["odd"])
            except ValueError:
                continue
            if best is None or abs(odd - 2.0) < best[0]:
                best = (abs(odd - 2.0), line)
    if best:
        line = best[1]
        hc = ("%s ต่อ %s" % (home, thai_line(line))) if line < 0 else (
            ("%s ต่อ %s" % (away, thai_line(line))) if line > 0 else "เสมอ")
    return hc, ou


def main():
    if not KEY:
        sys.exit("ไม่มี API_FOOTBALL_KEY")
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=24)
    fixtures = []
    for day in sorted({now.date(), end.date()}):
        fixtures += api("/fixtures", date=day.isoformat())
    out = []
    for f in fixtures:
        lid = f["league"]["id"]
        if lid not in LEAGUES or f["fixture"]["status"]["short"] != "NS":
            continue
        t = datetime.fromisoformat(f["fixture"]["date"]).astimezone(TH)
        if not (now <= t.astimezone(timezone.utc) <= end):
            continue
        out.append((t, f))
    out.sort(key=lambda x: x[0])
    matches = []
    for t, f in out[:MAX_MATCHES]:
        h, a = f["teams"]["home"], f["teams"]["away"]
        odds = api("/odds", fixture=f["fixture"]["id"])
        hc, ou = analyse(odds, h["name"], a["name"])
        flag, lg = LEAGUES[f["league"]["id"]]
        matches.append({
            "t": t.strftime("%H:%M"), "d": DAYS[t.weekday()], "ts": int(t.timestamp()),
            "flag": flag, "lg": lg,
            "h": {"n": h["name"], "l": h["logo"]}, "a": {"n": a["name"], "l": a["logo"]},
            "hc": hc, "ou": ou,
        })
    nt = datetime.now(TH)
    data = {"updated": "%s %02d/%02d %s น." % (DAYS[nt.weekday()], nt.day, nt.month, nt.strftime("%H:%M")),
            "date": "%d/%d/%s" % (nt.day, nt.month, str(nt.year + 543)[2:]), "matches": matches}
    with open("data.json", "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    print("เขียน data.json แล้ว %d คู่" % len(matches))


if __name__ == "__main__":
    main()
