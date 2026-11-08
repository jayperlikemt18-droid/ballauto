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
MAX_MATCHES = 40  # แต่ละคู่ใช้ 1 ครั้ง (ราคา) โควตาฟรีวันละ 100 รัน 2 รอบ


class Quota(Exception):
    pass


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
        er = d["errors"]
        if isinstance(er, dict) and any(k in er for k in ("requests", "token", "access")):
            raise Quota(str(er))
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


def _key(n):
    n = "".join(c for c in unicodedata.normalize("NFD", n.lower()) if unicodedata.category(c) != "Mn")
    n = "".join(c if c.isalnum() else "" for c in n)
    for w in ("fc", "afc", "cf", "sc", "ac", "as", "fk", "sv", "vfb", "vfl", "fsv", "1899", "1", "ssc", "us", "rc", "cd", "ud"):
        if n.startswith(w) and len(n) > len(w) + 3:
            n = n[len(w):]
    return n


ALIAS = {"manchestercity": "mancity", "manchesterunited": "manunited", "nottinghamforest": "forest",
         "bayernmunich": "bayern", "borussiadortmund": "dortmund", "bayerleverkusen": "leverkusen",
         "rbleipzig": "leipzig", "borussiamonchengladbach": "gladbach", "eintrachtfrankfurt": "frankfurt",
         "parissaintgermain": "parissg", "atleticomadrid": "atletico", "athleticclub": "athletic",
         "inter": "inter", "acmilan": "milan", "milan": "milan", "wolves": "wolves", "westham": "westham",
         "newcastle": "newcastle", "tottenham": "tottenham", "brighton": "brighton", "leeds": "leeds",
         "sportingcp": "sportingcp", "celticfc": "celtic", "stuttgart": "stuttgart", "werderbremen": "werderbremen",
         "unionberlin": "unionberlin", "mainz05": "mainz", "mainz": "mainz", "hoffenheim": "hoffenheim",
         "realsociedad": "sociedad", "celtavigo": "celta", "rayovallecano": "rayovallecano", "olympiquelyonnais": "lyon",
         "olympiquedemarseille": "marseille", "asmonaco": "monaco", "ogcnice": "nice"}


def load_elo():
    day = datetime.now(timezone.utc).date().isoformat()
    txt = None
    for base in ("http://api.clubelo.com/", "https://api.clubelo.com/"):
        try:
            with urllib.request.urlopen(base + day, timeout=30) as r:
                txt = r.read().decode("utf-8", "replace")
            break
        except Exception as e:
            print("ClubElo ไม่ได้:", e)
    elo = {}
    if txt:
        for line in txt.splitlines()[1:]:
            p = line.split(",")
            if len(p) >= 5:
                try:
                    elo[_key(p[1])] = float(p[4])
                except ValueError:
                    pass
    print("ClubElo %d ทีม" % len(elo))
    return elo


def elo_of(elo, name):
    if not elo:
        return None
    k = _key(name)
    k = ALIAS.get(k, k)
    if k in elo:
        return elo[k]
    cands = [x for x in elo if len(x) >= 4 and len(k) >= 4 and (x.startswith(k) or k.startswith(x))]
    if not cands:
        cands = [x for x in elo if len(x) >= 6 and x in k]
    if len(cands) == 1:
        return elo[cands[0]]
    import difflib
    m = difflib.get_close_matches(k, list(elo), n=1, cutoff=0.85)
    return elo[m[0]] if m else None


def get_pred(fid):
    try:
        d = api("/predictions", fixture=fid)
        pc = d[0]["predictions"]["percent"]
        r = {"h": int(pc["home"].strip("%")), "d": int(pc["draw"].strip("%")), "a": int(pc["away"].strip("%"))}
        if (r["h"], r["d"], r["a"]) in ((10, 45, 45), (45, 45, 10)):  # ค่าเริ่มต้นของแหล่งข้อมูลเมื่อไม่มีสถิติพอ
            return None
        return r
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
    hp = {"L": best[1]} if best else None
    w = {v["value"]: float(v["odd"]) for v in find_bet(res, 1) if v.get("value") in ("Home", "Draw", "Away")}
    if hp is not None and len(w) == 3:
        tot = sum(1 / o for o in w.values())
        hp["m"] = {"h": round(100 / w["Home"] / tot), "d": round(100 / w["Draw"] / tot), "a": round(100 / w["Away"] / tot)}
    if best:
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
        a = (ou["pct"], "%s %s" % (tn(g), ou["lab"]), "ou")
    if hp:
        b = (hp["pct"], _swap(m, hp["lab"]), "hp")
    if a and b:
        return a if a[0] >= b[0] else b
    return a or b


def select(picks, n):
    cap = -(-n * 3 // 5)  # ชนิดเดียวกันไม่เกิน 60% ของสเต็ป
    chosen, rest, cnt = [], [], {}
    for p in picks:
        if len(chosen) < n and cnt.get(p[3], 0) < cap:
            chosen.append(p)
            cnt[p[3]] = cnt.get(p[3], 0) + 1
        else:
            rest.append(p)
    return (chosen + rest)[:n]


def build_message(data):
    picks = []
    for m in data["matches"]:
        pk = best_pick(m)
        if pk:
            picks.append((pk[0], m, pk[1], pk[2]))
    picks.sort(key=lambda x: -x[0])
    out = ["⚽️บอลวันที่ %s⚽️" % data["date"], ""]
    for n, icon in ((3, "⚡"), (5, "🔥"), (7, "💣")):
        if len(picks) < n:
            continue
        out.append("%s สเต็ป %d" % (icon, n))
        for _, m, txt, _k in sorted(select(picks, n), key=lambda x: x[1]["ts"]):
            out.append("⏰%s %s" % (m["t"].replace(":", "."), txt))
        out.append("————————————")
    if picks:
        out.append("⭐ ตัวเน้นสุด")
        for medal, (_, _, txt, _k) in zip("🥇🥈🥉", select(picks, 3)):
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
    try:
        run()
    except Quota as e:
        print("โควตา/สิทธิ์ api-football มีปัญหา ไม่เขียนทับข้อมูลเดิม:", e)


def run():
    if not KEY:
        sys.exit("ไม่มี API_FOOTBALL_KEY")
    history = []
    old = []
    try:
        with open("data.json", encoding="utf-8") as fh:
            _d = json.load(fh)
            history = _d.get("history", [])
            old = _d.get("matches", [])
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
    elo_map = load_elo()
    matches = []
    # ล็อกคู่เด็ดเดิมที่ยังไม่เตะ ไม่เปลี่ยนคู่ที่แจกไปแล้ว และไม่เสียโควตาดึงราคาซ้ำ
    locked = {m["id"]: m for m in old
              if m.get("id") and m["ts"] > now.timestamp() and (m.get("hp") or (m.get("ou") and not m["ou"].get("weak")))}
    for t, f in out:
        h, a = f["teams"]["home"], f["teams"]["away"]
        if f["fixture"]["id"] in locked:
            m0 = dict(locked[f["fixture"]["id"]], lock=True)
            matches.append(m0)
            continue
        odds = api("/odds", fixture=f["fixture"]["id"])
        hc, ou, hp, hcs, ous = analyse(odds, h["name"], a["name"])
        pr = get_pred(f["fixture"]["id"]) if os.environ.get("USE_PRED") == "1" else None  # ปิดไว้ประหยัดโควตา ใช้ % จากราคา 1X2 แทน
        base_line = hp["L"] if hp else None
        if not pr and hp:  # ไม่มีสถิติ ใช้ % ชนะที่คำนวณจากราคา 1X2 ของตลาดแทน
            pr = hp.get("m")
        hp = None
        eh, ea = elo_of(elo_map, h["name"]), elo_of(elo_map, a["name"])
        e = (100 / (1 + 10 ** (-(eh + 65 - ea) / 400))) if eh and ea else None
        if pr and base_line:  # เลือกทีมจาก % โอกาสชนะ ต่อใส่ (-) รองใส่ (+)
            fav = "home" if pr["h"] >= pr["a"] else "away"
            win = max(pr["h"], pr["a"])
            giver = "home" if base_line < 0 else "away"
            L = abs(base_line)
            team = h["name"] if fav == "home" else a["name"]
            if e is not None and ((e >= 50) != (fav == "home") or max(e, 100 - e) < 55):
                fav = None  # Elo ไม่เห็นด้วย ข้ามต่อรองคู่นี้
            if fav is None:
                pass
            elif win >= 55 and giver == fav and L <= 1:
                hp = {"lab": "%s -%s" % (team, thai_line(L)), "pct": win, "team": team, "giver": True,
                      "lt": thai_line(L), "side": fav, "h": -L}
            elif win >= 55 and giver != fav and L <= 2:
                hp = {"lab": "%s +%s" % (team, thai_line(L)), "pct": win, "team": team, "giver": False,
                      "lt": thai_line(L), "side": fav, "h": L}
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
            "id": f["fixture"]["id"], "t": t.strftime("%H:%M"), "d": DAYS[t.weekday()], "ts": int(t.timestamp()),
            "flag": flag, "lg": lg,
            "h": {"n": h["name"], "l": h["logo"]}, "a": {"n": a["name"], "l": a["logo"]},
            "hc": hc, "ou": ou, "hp": hp, "pr": pr, "elo": round(e) if e is not None else None, "hcs": hcs, "ous": ous,
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
