#!/usr/bin/env python3
"""ดึงตารางแข่งและราคาจาก api-football แล้วเขียน data.json ให้หน้าเว็บอ่าน"""
import json, os, sys, time, unicodedata, urllib.error, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone

KEY = os.environ.get("API_FOOTBALL_KEY", "").strip()
BASE = "https://v3.football.api-sports.io"
TH = timezone(timedelta(hours=7))
DAYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
LEAGUES = {  # id: (ธง, ชื่อลีก)
    39: ("🏴󠁧󠁢󠁥󠁮󠁧󠁿", "พรีเมียร์ลีก อังกฤษ"), 78: ("🇩🇪", "บุนเดสลีกา เยอรมัน"),
    135: ("🇮🇹", "เซเรีย อา อิตาลี"), 61: ("🇫🇷", "ลีกเอิง ฝรั่งเศส"),
    140: ("🇪🇸", "ลาลีกา สเปน"), 2: ("🏆", "แชมเปียนส์ลีก"), 3: ("🏆", "ยูโรปาลีก"),
    40: ("🏴󠁧󠁢󠁥󠁮󠁧󠁿", "แชมเปี้ยนชิป อังกฤษ"), 88: ("🇳🇱", "เอเรดิวิซี่ เนเธอร์แลนด์"),
    94: ("🇵🇹", "พรีเมร่าลีกา โปรตุเกส"), 203: ("🇹🇷", "ซูเปอร์ลีก ตุรกี"),
    144: ("🇧🇪", "โปรลีก เบลเยียม"), 179: ("🏴󠁧󠁢󠁳󠁣󠁴󠁿", "พรีเมียร์ชิพ สกอตแลนด์"),
    79: ("🇩🇪", "บุนเดสลีกา 2"), 136: ("🇮🇹", "เซเรีย บี"), 141: ("🇪🇸", "ลาลีกา 2"), 62: ("🇫🇷", "ลีกเอิง 2"),
    71: ("🇧🇷", "เซเรีย อา บราซิล"), 253: ("🇺🇸", "เมเจอร์ลีก ซอคเกอร์"), 98: ("🇯🇵", "เจลีก"),
    292: ("🇰🇷", "เคลีก"), 307: ("🇸🇦", "ซาอุ โปรลีก"), 296: ("🇹🇭", "ไทยลีก"), 45: ("🏆", "เอฟเอ คัพ"),
}
ORDER = list(LEAGUES)
MIN_PROB = 0.56
MAX_MATCHES = 22  # แต่ละคู่ใช้ 2 ครั้ง (ราคา + % ชนะ) โควตาฟรีวันละ 100


def api(path, **params):
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"x-apisports-key": KEY})
    for attempt in range(4):
        time.sleep(7)  # แพ็กเกจฟรีจำกัด 10 ครั้งต่อนาที
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            print("HTTP", e.code, path)
            if e.code == 429 and attempt < 3:
                time.sleep(30)
                continue
            raise
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


def _r(d):
    return 1 if d > 0 else (-1 if d < 0 else 0)


def halves(x):
    return [x] if (abs(x) * 4) % 2 == 0 else [x - 0.25, x + 0.25]


def res_total(goals, side, x):
    v = [(_r(goals - l) * (1 if side == "over" else -1)) for l in halves(x)]
    return sum(v) / len(v)


def res_hc(diff, h):
    v = [_r(diff + l) for l in halves(h)]
    return sum(v) / len(v)


def get_pred(fid):
    try:
        d = api("/predictions", fixture=fid)
        pc = d[0]["predictions"]["percent"]
        return {"h": int(pc["home"].strip("%")), "d": int(pc["draw"].strip("%")), "a": int(pc["away"].strip("%"))}
    except Exception as e:
        print("ไม่มี % ชนะ:", e)
        return None


def settle(history):
    now = datetime.now(timezone.utc).timestamp()
    pend = [e for e in history if e.get("res") is None and e["ts"] < now - 3 * 3600]
    days = sorted({datetime.fromtimestamp(e["ts"], timezone.utc).date().isoformat() for e in pend})[:3]
    done = {}
    for day in days:
        for f in api("/fixtures", date=day):
            if f["fixture"]["status"]["short"] in ("FT", "AET", "PEN"):
                ft = f["score"]["fulltime"]
                if ft["home"] is not None:
                    done[f["fixture"]["id"]] = (ft["home"], ft["away"])
    for e in pend:
        if e["id"] in done:
            gh, ga = done[e["id"]]
            e["gh"], e["ga"] = gh, ga
            if e["k"] == "ou":
                e["res"] = res_total(gh + ga, e["s"], e["x"])
            else:
                diff = (gh - ga) if e["side"] == "home" else (ga - gh)
                e["res"] = res_hc(diff, e["h"])


def find_bet(bookmakers, bet_id):
    for b in bookmakers:
        for bet in b.get("bets", []):
            if bet.get("id") == bet_id:
                return bet.get("values", [])
    return []


def find_totals(bookmakers):
    v = find_bet(bookmakers, 5)
    if v:
        return v
    for b in bookmakers:  # ลองบ่อนอื่น/ชื่ออื่นที่เป็นสูง/ต่ำเต็มเวลา
        for bet in b.get("bets", []):
            n = (bet.get("name") or "").lower()
            if "over/under" in n and not any(w in n for w in ("half", "home", "away", "team", "corner", "card", "exact")):
                if any(str(x.get("value", "")).startswith("Over ") for x in bet.get("values", [])):
                    return bet["values"]
    names = sorted({bet.get("name") for b in bookmakers for bet in b.get("bets", [])})
    print("ไม่พบสูง/ต่ำ มีแต่:", names[:12])
    return []


def analyse(odds, home, away):
    res = odds[0].get("bookmakers", []) if odds else []
    ou = None
    vals = {v["value"]: float(v["odd"]) for v in find_totals(res)}
    best_t = None
    for k, o in vals.items():
        if not k.startswith("Over "):
            continue
        try:
            x = float(k.split()[1])
        except ValueError:
            continue
        u = vals.get("Under %g" % x) or vals.get("Under " + k.split()[1])
        if not u:
            continue
        gap = abs(o - u)
        if best_t is None or gap < best_t[0]:
            best_t = (gap, x, o, u)
    if best_t:
        _, x, o, u = best_t
        po = (1 / o) / ((1 / o) + (1 / u))
        if po >= 0.5:
            ou = {"lab": "สูง " + thai_line(x), "line": thai_line(x), "pct": round(po * 100), "weak": po < 0.53, "s": "over", "x": x}
        else:
            ou = {"lab": "ต่ำ " + thai_line(x), "line": thai_line(x), "pct": round((1 - po) * 100), "weak": (1 - po) < 0.53, "s": "under", "x": x}
    hc = None
    best = None
    hcs, ous = [], []
    for v in find_bet(res, 4):
        if v["value"].startswith("Home "):
            try:
                line = float(v["value"].split()[1])
                odd = float(v["odd"])
            except ValueError:
                continue
            if best is None or abs(odd - 2.0) < best[0]:
                best = (abs(odd - 2.0), line)
            if 1.5 <= odd <= 2.6:
                hcs.append(abs(line))
    for k, odd in vals.items():
        if k.startswith("Over ") and 1.5 <= odd <= 2.6:
            try:
                ous.append(float(k.split()[1]))
            except ValueError:
                pass
    hp = None
    if best:
        ho = ao = None
        for v in find_bet(res, 4):
            try:
                if v["value"] == "Home %s" % v["value"].split()[1] and float(v["value"].split()[1]) == best[1]:
                    ho = float(v["odd"])
                if v["value"].startswith("Away ") and float(v["value"].split()[1]) == -best[1]:
                    ao = float(v["odd"])
            except (ValueError, IndexError):
                pass
        if ho and ao and abs(ho - ao) >= 0.04:
            ph = (1 / ho) / ((1 / ho) + (1 / ao))
            home_lean = ho < ao
            pct = round((ph if home_lean else 1 - ph) * 100)
            L = best[1]
            team = home if home_lean else away
            giver = (home_lean and L < 0) or ((not home_lean) and L > 0)
            if L != 0 and pct >= 52:
                hp = {"lab": "%s %s %s" % (team, "ต่อ" if giver else "รอง", thai_line(L)), "pct": pct,
                      "team": team, "giver": giver, "lt": thai_line(L), "side": "home" if home_lean else "away",
                      "h": L if home_lean else -L}
            elif L == 0 and pct >= 52:
                hp = {"lab": "%s เสมอ" % team, "pct": pct, "team": team, "giver": False, "lt": "เสมอ",
                      "side": "home" if home_lean else "away", "h": 0}
        line = best[1]
        hc = ("%s ต่อ %s" % (home, thai_line(line))) if line < 0 else (
            ("%s ต่อ %s" % (away, thai_line(line))) if line > 0 else "เสมอ")
    return hc, ou, hp, [thai_line(x) for x in sorted(set(hcs))], ["%g" % x for x in sorted(set(ous))]


def load_names():
    try:
        with open("names.json", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


NAMES = load_names()


def tn(n):
    k = "".join(c for c in unicodedata.normalize("NFD", n.lower()) if unicodedata.category(c) != "Mn")
    return NAMES.get(k) or NAMES.get(n.lower()) or n


def _swap(m, t):
    return t.replace(m["h"]["n"], tn(m["h"]["n"])).replace(m["a"]["n"], tn(m["a"]["n"]))


def best_pick(m):
    a = b = None
    ou, hp = m.get("ou"), m.get("hp")
    if ou and not ou["weak"]:
        g = m["hc"].split(" ต่อ ")[0] if m.get("hc") and " ต่อ " in m["hc"] else m["h"]["n"]
        a = (ou["pct"], "%s %s" % (tn(g), ou["lab"]))
    if hp:
        b = (hp["pct"], _swap(m, hp["lab"]))
    if a and b:
        return a if a[0] >= b[0] else b
    return a or b


def build_message(data):
    picks = []
    for m in data["matches"]:
        pk = best_pick(m)
        if pk:
            picks.append((pk[0], m, pk[1]))
    picks.sort(key=lambda x: -x[0])
    out = ["⚽️บอลวันที่ %s⚽️" % data["date"], ""]
    for n, icon in ((3, "⚡"), (5, "🔥"), (7, "💣")):
        if len(picks) < n:
            continue
        out.append("%s สเต็ป %d" % (icon, n))
        for _, m, txt in sorted(picks[:n], key=lambda x: x[1]["ts"]):
            out.append("⏰%s %s" % (m["t"].replace(":", "."), txt))
        out.append("————————————")
    if picks:
        out.append("⭐ ตัวเน้นสุด")
        for medal, (_, _, txt) in zip("🥇🥈🥉", picks[:3]):
            out.append("%s %s" % (medal, txt))
        out.append("")
    return "\n".join(out).rstrip(), len(picks)


def send_telegram(text):
    tok, chat = os.environ.get("TELEGRAM_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT", "").strip()
    if not tok or not chat:
        print("ไม่ได้ตั้งเทเลแกรม ข้ามการส่ง")
        return
    body = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    try:
        urllib.request.urlopen("https://api.telegram.org/bot%s/sendMessage" % tok, data=body, timeout=30)
        print("ส่งเทเลแกรมแล้ว")
    except Exception as e:
        print("ส่งเทเลแกรมไม่สำเร็จ:", e)


def main():
    if not KEY:
        sys.exit("ไม่มี API_FOOTBALL_KEY")
    history = []
    try:
        with open("data.json", encoding="utf-8") as fh:
            history = json.load(fh).get("history", [])
    except Exception:
        pass
    try:
        settle(history)
    except Exception as e:
        print("เช็กผลไม่ได้:", e)
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
    out.sort(key=lambda x: (ORDER.index(x[1]["league"]["id"]), x[0]))
    out = sorted(out[:MAX_MATCHES], key=lambda x: x[0])
    matches = []
    for t, f in out:
        h, a = f["teams"]["home"], f["teams"]["away"]
        odds = api("/odds", fixture=f["fixture"]["id"])
        hc, ou, hp, hcs, ous = analyse(odds, h["name"], a["name"])
        pr = get_pred(f["fixture"]["id"])
        if hp and pr:  # ตลาดกับสถิติต้องเห็นตรงกัน ไม่งั้นไม่เลือกต่อรอง
            if (hp["side"] == "home" and pr["h"] < pr["a"]) or (hp["side"] == "away" and pr["a"] < pr["h"]):
                hp = None
        flag, lg = LEAGUES[f["league"]["id"]]
        if not any(e["id"] == f["fixture"]["id"] for e in history):
            base = {"id": f["fixture"]["id"], "ts": int(t.timestamp()), "d": "%02d/%02d" % (t.day, t.month),
                    "hn": h["name"], "an": a["name"], "lg": lg, "res": None}
            if ou and not ou["weak"]:
                history.append(dict(base, k="ou", s=ou["s"], x=ou["x"], lt=ou["line"], pct=ou["pct"]))
            if hp:
                history.append(dict(base, k="hp", side=hp["side"], h=hp["h"], lt=hp["lt"], team=hp["team"],
                                    giver=hp["giver"], pct=hp["pct"]))
        matches.append({
            "t": t.strftime("%H:%M"), "d": DAYS[t.weekday()], "ts": int(t.timestamp()),
            "flag": flag, "lg": lg,
            "h": {"n": h["name"], "l": h["logo"]}, "a": {"n": a["name"], "l": a["logo"]},
            "hc": hc, "ou": ou, "hp": hp, "pr": pr, "hcs": hcs, "ous": ous,
        })
    nt = datetime.now(TH)
    data = {"updated": "%s %02d/%02d %s น." % (DAYS[nt.weekday()], nt.day, nt.month, nt.strftime("%H:%M")),
            "date": "%d/%d/%s" % (nt.day, nt.month, str(nt.year + 543)[2:]), "matches": matches,
            "history": sorted(history, key=lambda e: e["ts"])[-150:]}
    with open("data.json", "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    print("เขียน data.json แล้ว %d คู่" % len(matches))
    if os.environ.get("SEND") == "1":
        text, n = build_message(data)
        if n:
            send_telegram(text)


if __name__ == "__main__":
    main()
