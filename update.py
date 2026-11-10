#!/usr/bin/env python3
"""ดึงตารางแข่งและราคาจาก api-football แล้วเขียน data.json ให้หน้าเว็บอ่าน"""
import json, math, os, sys, time, unicodedata, urllib.error, urllib.request, urllib.parse
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
    5: ("🌍", "เนชันส์ลีก"), 960: ("🌍", "ยูโร คัดเลือก"),
    32: ("🌍", "ฟุตบอลโลก คัดเลือก ยุโรป"), 34: ("🌎", "ฟุตบอลโลก คัดเลือก อเมริกาใต้"),
    31: ("🌎", "ฟุตบอลโลก คัดเลือก คอนคาเคฟ"), 29: ("🌍", "ฟุตบอลโลก คัดเลือก แอฟริกา"),
    143: ("🇪🇸", "โกปา เดล เรย์"),     30: ("🌏", "ฟุตบอลโลก คัดเลือก เอเชีย"), 36: ("🌍", "แอฟริกัน เนชันส์ คัดเลือก"),
}
ORDER = list(LEAGUES)
MIN_PROB = 0.56
MAX_MATCHES = 400
MAX_MODEL = 10  # คู่ที่เช็กสถิติย้อนหลัง คู่ละ 2 ครั้ง  # แต่ละคู่ใช้ 1 ครั้ง (ราคา) โควตาฟรีวันละ 100 รัน 2 รอบ


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
    api.paging = d.get("paging") or {}
    return d.get("response", [])


def bulk_odds(day, max_pages=20):
    """ดึงราคาทั้งวันทีละหน้า (10 คู่/หน้า) ประหยัดโควตากว่าดึงทีละคู่"""
    m = {}
    page = 1
    while page <= max_pages:
        try:
            r = api("/odds", date=day, page=page)
        except Quota:
            raise
        except Exception as e:
            print("odds หน้า", page, "พลาด:", e)
            break
        for x in r:
            m[x["fixture"]["id"]] = x
        total = (api.paging or {}).get("total", 1)
        if page >= total:
            break
        page += 1
    print("ราคา", day, len(m), "คู่")
    return m


def calibrate(history):
    """ดูผลย้อนหลัง: ชนิด/ลีกไหนแย่ชัดเจน ตัดทิ้ง (ต้องมีผลอย่างน้อย 30 / 10 คู่)"""
    def rate(a):
        w = sum(1 for e in a if e["res"] > 0)
        l = sum(1 for e in a if e["res"] < 0)
        return (w / (w + l), w + l) if w + l else (None, 0)
    done = [e for e in history if e.get("res") is not None]
    bad_kind, bad_lg = set(), set()
    for k in ("ou", "hp"):
        r, n = rate([e for e in done if e.get("k") == k])
        if n >= 30 and r < 0.48:
            bad_kind.add(k)
    for g in {e.get("lg") for e in done}:
        r, n = rate([e for e in done if e.get("lg") == g])
        if n >= 10 and r < 0.40:
            bad_lg.add(g)
    print("ตัดชนิด:", bad_kind, "ตัดลีก:", bad_lg)
    return bad_kind, bad_lg


def bm_ou(books, x, side):
    out = []
    for b in books:
        for bet in b.get("bets", []):
            if bet.get("id") != 5:
                continue
            v = {i.get("value"): i.get("odd") for i in bet.get("values", [])}
            o, u = v.get("Over %g" % x), v.get("Under %g" % x)
            try:
                po = (1 / float(o)) / ((1 / float(o)) + (1 / float(u)))
            except (TypeError, ValueError, ZeroDivisionError):
                continue
            out.append(round((po if side == "over" else 1 - po) * 100))
    return out


def ah_ladder(books):
    """ราคาต่อรองทุกบรรทัด: [(แต้มต่อมุมเจ้าบ้าน, โอกาสเจ้าบ้านผ่านราคา)] เฉลี่ยทุกเจ้ามือ ตัดค่าน้ำแล้ว"""
    acc = {}
    for b in books:
        for bet in b.get("bets", []):
            if bet.get("id") != 4:
                continue
            hm, am = {}, {}
            for v in bet.get("values", []):
                try:
                    kind, x = v["value"].split()
                    x, o = float(x), float(v["odd"])
                except (ValueError, KeyError):
                    continue
                if kind == "Home":
                    hm[x] = o
                elif kind == "Away":
                    am[-x] = o
            for ln in hm:
                if ln in am:
                    acc.setdefault(ln, []).append((1 / hm[ln]) / ((1 / hm[ln]) + (1 / am[ln])))
    return sorted((ln, sum(v) / len(v)) for ln, v in acc.items())


def bm_win(books, side):
    out = []
    for b in books:
        for bet in b.get("bets", []):
            if bet.get("id") != 1:
                continue
            v = {i.get("value"): i.get("odd") for i in bet.get("values", [])}
            try:
                tot = sum(1 / float(v[k]) for k in ("Home", "Draw", "Away"))
                out.append(round(100 / float(v["Home" if side == "home" else "Away"]) / tot))
            except (KeyError, TypeError, ValueError, ZeroDivisionError):
                continue
    return out


def team_form(tid):
    """ประตูได้/เสียเฉลี่ย 10 นัดหลังสุด (ต้องมีอย่างน้อย 5 นัด)"""
    fx = api("/fixtures", team=tid, last=10)
    gf = ga = n = 0
    for f in fx:
        if f["fixture"]["status"]["short"] not in ("FT", "AET", "PEN"):
            continue
        g = f["goals"]
        if g["home"] is None or g["away"] is None:
            continue
        mine = g["home"] if f["teams"]["home"]["id"] == tid else g["away"]
        gf += mine
        ga += (g["home"] + g["away"]) - mine
        n += 1
    return (gf / n, ga / n) if n >= 5 else None


def poisson_dist(lh, la, cap=10):
    def pm(l):
        p, out = math.exp(-l), []
        for k in range(cap + 1):
            out.append(p)
            p = p * l / (k + 1)
        return out
    ph, pa = pm(max(lh, 0.05)), pm(max(la, 0.05))
    return {(i, j): ph[i] * pa[j] for i in range(cap + 1) for j in range(cap + 1)}


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
    old_snap = {}
    try:
        with open("data.json", encoding="utf-8") as fh:
            _d = json.load(fh)
            history = _d.get("history", [])
            old = _d.get("matches", [])
            old_snap = _d.get("snap", {})
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
        if f["fixture"]["status"]["short"] != "NS":
            continue
        t = datetime.fromisoformat(f["fixture"]["date"]).astimezone(TH)
        if not (now <= t.astimezone(timezone.utc) <= end):
            continue
        out.append((t, f))
    out = list({x[1]["fixture"]["id"]: x for x in out}.values())
    odds_map = {}
    for day in sorted({now.date(), end.date()}):
        odds_map.update(bulk_odds(day.isoformat()))
    out = [x for x in out if x[1]["fixture"]["id"] in odds_map or x[1]["fixture"]["id"] in {m.get("id") for m in old}]
    out.sort(key=lambda x: x[0])
    out = out[:MAX_MATCHES]
    elo_map = load_elo()
    matches = []
    # ล็อกคู่เด็ดเดิมที่ยังไม่เตะ ไม่เปลี่ยนคู่ที่แจกไปแล้ว
    locked = {m["id"]: m for m in old
              if m.get("id") and m.get("v") == 2 and m["ts"] > now.timestamp() and (m.get("hp") or (m.get("ou") and not m["ou"].get("weak")))}
    snap = {k: v for k, v in old_snap.items() if v.get("ts", 0) > now.timestamp() - 86400}
    bad_kind, bad_lg = calibrate(history)
    cands = []
    for t, f in out:
        fid = f["fixture"]["id"]
        h, a = f["teams"]["home"], f["teams"]["away"]
        if fid in locked:
            matches.append(dict(locked[fid], lock=True))
            continue
        odds = [odds_map[fid]] if fid in odds_map else []
        books = odds[0].get("bookmakers", []) if odds else []
        hc, ou, hp, hcs, ous = analyse(odds, h["name"], a["name"])
        base_line = hp["L"] if hp else None
        pr = hp.get("m") if hp else None
        hp = None
        eh, ea = elo_of(elo_map, h["name"]), elo_of(elo_map, a["name"])
        e = (100 / (1 + 10 ** (-(eh + 65 - ea) / 400))) if eh and ea else None
        if pr:  # เลือกทีมเต็งจาก % ชนะ แล้วหาราคาต่อรองที่คุ้มที่สุดจากทุกราคาที่ตลาดเปิด
            fav = "home" if pr["h"] >= pr["a"] else "away"
            if max(pr["h"], pr["a"]) < 55:
                fav = None
            if fav and e is not None and ((e >= 50) != (fav == "home") or max(e, 100 - e) < 55):
                fav = None
            if fav:
                team = h["name"] if fav == "home" else a["name"]
                best_c = None
                for line, ph in ah_ladder(books):
                    ht = line if fav == "home" else -line   # แต้มต่อของทีมเต็ง (ลบ = ต่อ)
                    pc = ph if fav == "home" else 1 - ph
                    if pc < 0.60 or ht < -1 or ht > 2:
                        continue
                    if best_c is None or pc < best_c[0]:
                        best_c = (pc, ht)
                if best_c:
                    pc, ht = best_c
                    sgn = "-" if ht < 0 else "+"
                    lt = thai_line(abs(ht)) if ht != 0 else "0"
                    hp = {"lab": "%s %s%s" % (team, sgn if ht != 0 else "", lt), "pct": round(pc * 100), "team": team,
                          "giver": ht < 0, "lt": lt, "side": fav, "h": ht}
        if ou and ou["pct"] < 60:
            ou["weak"] = True
        lgid = f["league"]["id"]
        flag, lg = LEAGUES.get(lgid, ("⚽", f["league"]["name"]))
        sn = snap.setdefault(str(fid), {"ts": int(t.timestamp())})
        # 4) ปรับตามผลย้อนหลัง
        if ou and not ou["weak"] and ("ou" in bad_kind or lg in bad_lg):
            ou["weak"] = True
        if hp and ("hp" in bad_kind or lg in bad_lg):
            hp = None
        # 1) ตลาดเห็นตรงกันไหม (หลายเจ้ามือ)
        if ou and not ou["weak"]:
            ps = bm_ou(books, ou["x"], ou["s"])
            if len(ps) >= 2 and max(ps) - min(ps) > 6:
                ou["weak"] = True
        if hp:
            ps = bm_win(books, hp["side"])
            if len(ps) >= 2 and max(ps) - min(ps) > 6:
                hp = None
        # 2) ราคาขยับสวนทางไหม (เทียบรอบแรกที่เห็นคู่นี้)
        for k, cur in (("ou", ou["pct"] if ou else None), ("hp", hp["pct"] if hp else None)):
            if cur is None:
                continue
            if k not in sn:
                sn[k] = cur
            elif cur - sn[k] <= -3:
                if k == "ou":
                    ou["weak"] = True
                else:
                    hp = None
        if (ou and not ou["weak"]) or hp:
            cands.append({"t": t, "f": f, "h": h, "a": a, "hc": hc, "ou": ou, "hp": hp, "pr": pr, "e": e,
                          "hcs": hcs, "ous": ous, "flag": flag, "lg": lg,
                          "top": max(ou["pct"] if ou and not ou["weak"] else 0, hp["pct"] if hp else 0)})
    # 3) เช็กด้วยสถิติประตูย้อนหลัง (โมเดลปัวซอง) เฉพาะคู่ที่ผ่านด่านก่อนหน้า และเรียงโอกาสสูงสุดก่อน
    cands.sort(key=lambda c: -c["top"])
    cands = cands[:MAX_MODEL]
    form = {}
    use_model = True
    for c in cands:
        if not use_model:
            break
        try:
            hh, aa = c["h"], c["a"]
            for tm in (hh, aa):
                if tm["id"] not in form:
                    form[tm["id"]] = team_form(tm["id"])
            fh, fa = form[hh["id"]], form[aa["id"]]
            if not fh or not fa:
                continue
            lh, la = (fh[0] + fa[1]) / 2, (fa[0] + fh[1]) / 2
            dist = poisson_dist(lh, la)
            if c["ou"] and not c["ou"]["weak"]:
                ev = sum(p * res_total(gh + ga, c["ou"]["s"], c["ou"]["x"]) for (gh, ga), p in dist.items())
                if ev <= 0:
                    c["ou"]["weak"] = True
            if c["hp"]:
                hpx = c["hp"]
                ev = sum(p * res_hc((gh - ga) if hpx["side"] == "home" else (ga - gh), hpx["h"]) for (gh, ga), p in dist.items())
                if ev <= 0:
                    c["hp"] = None
        except Quota:
            print("โควตาหมดตอนดึงสถิติ ข้ามขั้นนี้")
            use_model = False
        except Exception as ex:
            print("สถิติพลาด:", ex)
    for c in cands:
        ou, hp, t, f = c["ou"], c["hp"], c["t"], c["f"]
        if not ((ou and not ou["weak"]) or hp):
            continue
        h, a, e = c["h"], c["a"], c["e"]
        if not any(x["id"] == f["fixture"]["id"] for x in history):
            base = {"id": f["fixture"]["id"], "ts": int(t.timestamp()), "d": "%02d/%02d" % (t.day, t.month),
                    "hn": h["name"], "an": a["name"], "lg": c["lg"], "res": None}
            if ou and not ou["weak"]:
                history.append(dict(base, k="ou", s=ou["s"], x=ou["x"], lt=ou["line"], pct=ou["pct"]))
            if hp:
                history.append(dict(base, k="hp", side=hp["side"], h=hp["h"], lt=hp["lt"], team=hp["team"],
                                    giver=hp["giver"], pct=hp["pct"]))
        matches.append({
            "v": 2, "id": f["fixture"]["id"], "t": t.strftime("%H:%M"), "d": DAYS[t.weekday()], "ts": int(t.timestamp()),
            "flag": c["flag"], "lg": c["lg"],
            "h": {"n": h["name"], "l": h["logo"]}, "a": {"n": a["name"], "l": a["logo"]},
            "hc": c["hc"], "ou": ou, "hp": hp, "pr": c["pr"], "elo": round(e) if e is not None else None,
            "hcs": c["hcs"], "ous": c["ous"],
        })
    matches.sort(key=lambda m: m["ts"])
    nt = datetime.now(TH)
    data = {"updated": "%s %02d/%02d %s น." % (DAYS[nt.weekday()], nt.day, nt.month, nt.strftime("%H:%M")),
            "date": "%d/%d/%s" % (nt.day, nt.month, str(nt.year + 543)[2:]), "matches": matches,
            "history": sorted(history, key=lambda e: e["ts"])[-150:], "snap": snap}
    with open("data.json", "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    print("เขียน data.json แล้ว %d คู่" % len(matches))
    if os.environ.get("SEND") == "1":
        text, n = build_message(data)
        if n:
            send_telegram(text)


if __name__ == "__main__":
    main()
