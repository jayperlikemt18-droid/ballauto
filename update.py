#!/usr/bin/env python3
"""ดึงตารางแข่งและราคาจาก The Odds API แล้วเขียน data.json ให้หน้าเว็บอ่าน"""
import json, math, os, re, sys, time, unicodedata, urllib.error, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone

KEY = os.environ.get("ODDS_API_KEY", "").strip()
BASE = "https://api.the-odds-api.com/v4"
BUDGET = int(os.environ.get("ODDS_BUDGET", "16") or 16)  # เครดิตสูงสุดต่อรอบ (แพ็กฟรี 500/เดือน)
TH = timezone(timedelta(hours=7))
DAYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
LEAGUES = {  # sport key ของ The Odds API: (ธง, ชื่อลีก)
    "soccer_epl": ("🏴󠁧󠁢󠁥󠁮󠁧󠁿", "พรีเมียร์ลีก อังกฤษ"), "soccer_germany_bundesliga": ("🇩🇪", "บุนเดสลีกา เยอรมัน"),
    "soccer_italy_serie_a": ("🇮🇹", "เซเรีย อา อิตาลี"), "soccer_france_ligue_one": ("🇫🇷", "ลีกเอิง ฝรั่งเศส"),
    "soccer_spain_la_liga": ("🇪🇸", "ลาลีกา สเปน"), "soccer_uefa_champs_league": ("🏆", "แชมเปียนส์ลีก"),
    "soccer_uefa_europa_league": ("🏆", "ยูโรปาลีก"), "soccer_uefa_europa_conference_league": ("🏆", "คอนเฟอเรนซ์ลีก"),
    "soccer_efl_champ": ("🏴󠁧󠁢󠁥󠁮󠁧󠁿", "แชมเปี้ยนชิป อังกฤษ"), "soccer_netherlands_eredivisie": ("🇳🇱", "เอเรดิวิซี่ เนเธอร์แลนด์"),
    "soccer_portugal_primeira_liga": ("🇵🇹", "พรีเมร่าลีกา โปรตุเกส"), "soccer_turkey_super_league": ("🇹🇷", "ซูเปอร์ลีก ตุรกี"),
    "soccer_belgium_first_div": ("🇧🇪", "โปรลีก เบลเยียม"), "soccer_spl": ("🏴󠁧󠁢󠁳󠁣󠁴󠁿", "พรีเมียร์ชิพ สกอตแลนด์"),
    "soccer_germany_bundesliga2": ("🇩🇪", "บุนเดสลีกา 2"), "soccer_italy_serie_b": ("🇮🇹", "เซเรีย บี"),
    "soccer_spain_segunda_division": ("🇪🇸", "ลาลีกา 2"), "soccer_france_ligue_two": ("🇫🇷", "ลีกเอิง 2"),
    "soccer_brazil_campeonato": ("🇧🇷", "เซเรีย อา บราซิล"), "soccer_usa_mls": ("🇺🇸", "เมเจอร์ลีก ซอคเกอร์"),
    "soccer_japan_j_league": ("🇯🇵", "เจลีก"), "soccer_korea_kleague1": ("🇰🇷", "เคลีก"),
    "soccer_saudi_professional_league": ("🇸🇦", "ซาอุ โปรลีก"), "soccer_fa_cup": ("🏆", "เอฟเอ คัพ"),
    "soccer_uefa_nations_league": ("🌍", "เนชันส์ลีก"), "soccer_uefa_euro_qualification": ("🌍", "ยูโร คัดเลือก"),
    "soccer_fifa_world_cup_qualifiers_europe": ("🌍", "ฟุตบอลโลก คัดเลือก ยุโรป"),
    "soccer_fifa_world_cup_qualifiers_south_america": ("🌎", "ฟุตบอลโลก คัดเลือก อเมริกาใต้"),
    "soccer_conmebol_copa_libertadores": ("🌎", "โกปา ลิเบอร์ตาโดเรส"),
}
ORDER = list(LEAGUES)
MIN_PROB = 0.56
MAX_MATCHES = 400
MAX_MODEL = 10


class Quota(Exception):
    pass


def oget(path, **params):
    params["apiKey"] = KEY
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
            hd = r.headers
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, path, e.read().decode("utf-8", "replace")[:150])
        if e.code in (401, 429):
            raise Quota("HTTP %s" % e.code)
        raise
    try:
        oget.spent += int(hd.get("x-requests-last") or 0)
        oget.rem = hd.get("x-requests-remaining")
    except ValueError:
        pass
    return data


oget.spent = 0
oget.rem = None


def to_fixture(ev, key, title):
    return {"fixture": {"id": ev["id"], "date": ev["commence_time"].replace("Z", "+00:00"), "status": {"short": "NS"}},
            "league": {"id": key, "name": title, "season": None},
            "teams": {"home": {"id": None, "name": ev["home_team"], "logo": ""},
                      "away": {"id": None, "name": ev["away_team"], "logo": ""}}}


def to_odds(ev):
    """แปลงราคา The Odds API ให้อยู่ในรูปเดิมที่ analyse() ใช้ (bet 1=ชนะ, 4=ต่อรอง, 5=สูง/ต่ำ)"""
    hn, an = ev["home_team"], ev["away_team"]
    books = []
    for b in ev.get("bookmakers", []):
        bets = []
        for mk in b.get("markets", []):
            vals = []
            for o in mk.get("outcomes", []):
                nm = o.get("name")
                side = "Home" if nm == hn else "Away" if nm == an else nm
                try:
                    price = str(float(o["price"]))
                    if mk["key"] == "h2h" and side in ("Home", "Draw", "Away"):
                        vals.append({"value": side, "odd": price})
                    elif mk["key"] == "spreads" and side in ("Home", "Away"):
                        vals.append({"value": "%s %g" % (side, float(o["point"])), "odd": price})
                    elif mk["key"] == "totals" and side in ("Over", "Under"):
                        vals.append({"value": "%s %g" % (side, float(o["point"])), "odd": price})
                except (KeyError, TypeError, ValueError):
                    continue
            bid = {"h2h": 1, "spreads": 4, "totals": 5}.get(mk["key"])
            if bid and vals:
                bets.append({"id": bid, "name": mk["key"], "values": vals})
        books.append({"name": b.get("title"), "bets": bets})
    return {"fixture": {"id": ev["id"]}, "bookmakers": books}


def fetch_all(now, end, old):
    """ดึงลีกที่กำลังเปิดฤดูกาล เรียงตามความสำคัญ จนเครดิตถึงเพดาน"""
    sports = oget("/sports")  # ไม่เสียเครดิต
    soc = [s for s in sports if str(s.get("key", "")).startswith("soccer") and s.get("active")
           and not s.get("has_outrights") and "winner" not in s["key"]]
    for s in soc:  # ถ้วย/ทีมชาติที่ไม่รู้จัก ให้ถือเป็นรายการสำคัญ
        if s["key"] not in LEAGUES and any(w in s["key"] for w in ("nations", "qualif", "world_cup", "euro", "champions", "libertadores")):
            LEAGUES[s["key"]] = ("🌍", s["title"])
            ORDER.append(s["key"])
    soc.sort(key=lambda s: ORDER.index(s["key"]) if s["key"] in ORDER else 99)
    print("ลีกที่เปิดอยู่", len(soc), "| ใช้เครดิตไปแล้ว", oget.spent)
    iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")
    out, odds_map = [], {}
    for s in soc:
        if oget.spent + 3 > BUDGET:
            print("ถึงเพดานเครดิตต่อรอบ หยุดที่", s["title"])
            break
        try:
            evs = oget("/sports/%s/odds" % s["key"], regions="eu", markets="h2h,spreads,totals", oddsFormat="decimal",
                       dateFormat="iso", commenceTimeFrom=iso(now), commenceTimeTo=iso(end))
        except Quota:
            raise
        except Exception as e:
            print("ลีกพลาด:", s["title"], e)
            continue
        print(s["title"], len(evs), "คู่ | เครดิตรวม", oget.spent, "เหลือ", oget.rem)
        for ev in evs:
            t = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00")).astimezone(TH)
            if not (now <= t.astimezone(timezone.utc) <= end):
                continue
            f = to_fixture(ev, s["key"], s["title"])
            out.append((t, f))
            odds_map[ev["id"]] = to_odds(ev)
    return out, odds_map


def calibrate(history):
    """ดูผลย้อนหลัง: ชนิด/ลีกไหนแย่ชัดเจน ตัดทิ้ง (ต้องมีผลอย่างน้อย 30 / 10 คู่)"""
    def rate(a):
        w = sum(1 for e in a if e["res"] > 0)
        l = sum(1 for e in a if e["res"] < 0)
        return (w / (w + l), w + l) if w + l else (None, 0)
    done = [e for e in history if e.get("res") is not None and e.get("sp")]  # นับเฉพาะผลจากระบบใหม่
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
    pend = [e for e in history if e.get("res") is None and e.get("sp") and now - 3 * 86400 < e["ts"] < now - 3 * 3600]
    done = {}
    cnt = {}
    for e in pend:
        cnt[e["sp"]] = cnt.get(e["sp"], 0) + 1
    for sp in sorted(cnt, key=lambda k: -cnt[k])[:3]:  # คิดเครดิตลีกละ 2
        for g in oget("/sports/%s/scores" % sp, daysFrom=3):
            if g.get("completed") and g.get("scores"):
                sc = {x["name"]: x["score"] for x in g["scores"]}
                try:
                    done[g["id"]] = (int(sc[g["home_team"]]), int(sc[g["away_team"]]))
                except (KeyError, TypeError, ValueError):
                    pass
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


def totals_ladder(books):
    """สูง/ต่ำทุกบรรทัดที่เจ้ามือเปิด: [(เส้น, โอกาสสูง)] เฉลี่ยทุกเจ้ามือ ตัดค่าน้ำแล้ว"""
    acc = {}
    for b in books:
        for bet in b.get("bets", []):
            if bet.get("id") != 5:
                continue
            ov, un = {}, {}
            for v in bet.get("values", []):
                try:
                    kind, x = v["value"].split()
                    x, o = float(x), float(v["odd"])
                except (ValueError, KeyError):
                    continue
                (ov if kind == "Over" else un)[x] = o
            for x in ov:
                if x in un:
                    acc.setdefault(x, []).append((1 / ov[x]) / ((1 / ov[x]) + (1 / un[x])))
    return sorted((x, sum(v) / len(v)) for x, v in acc.items())


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
            ou = {"lab": "สูง " + thai_line(x), "line": thai_line(x), "pct": round(po * 100), "weak": po < 0.55, "s": "over", "x": x}
        else:
            ou = {"lab": "ต่ำ " + thai_line(x), "line": thai_line(x), "pct": round((1 - po) * 100), "weak": (1 - po) < 0.55, "s": "under", "x": x}
    lt_ = totals_ladder(res)  # บรรทัดจริงของตลาด = บรรทัดที่เจ้ามือตั้งให้ใกล้ 50/50 ที่สุด
    if lt_:
        x, po = min(lt_, key=lambda t: abs(t[1] - 0.5))
        side = "over" if po >= 0.5 else "under"
        p = po if side == "over" else 1 - po
        ou = {"lab": ("สูง " if side == "over" else "ต่ำ ") + thai_line(x), "line": thai_line(x),
              "pct": round(p * 100), "weak": p < 0.55, "s": side, "x": x}
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

def _norm(n):
    return "".join(c for c in unicodedata.normalize("NFD", n.lower()) if unicodedata.category(c) != "Mn")


_SUF = re.compile(r"^(.+?)\s+(?:W|Women|U-?\d\d|II|B)$", re.I)


def _base(n):
    m = _SUF.match(n)
    return m.group(1) if m else n


def _gt(text):
    url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(
        {"client": "gtx", "sl": "auto", "tl": "th", "dt": "t", "q": text})
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=15) as r:
        d = json.loads(r.read().decode("utf-8"))
    return "".join(seg[0] for seg in d[0] if seg and seg[0]).strip()


def _gemini_models(key):
    """ถามรายชื่อโมเดลที่คีย์นี้ใช้ได้จริง (ชื่อรุ่นเปลี่ยนบ่อย) ไม่เดาชื่อเอง"""
    pref = [m for m in [os.environ.get("GEMINI_MODEL", "").strip()] if m]
    try:
        req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                                     headers={"x-goog-api-key": key})
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8"))
        ms = []
        for m in d.get("models", []):
            nm = str(m.get("name", "")).replace("models/", "")
            if "flash" in nm and "generateContent" in (m.get("supportedGenerationMethods") or []) \
                    and not any(w in nm for w in ("image", "tts", "live", "audio", "embedding", "robotics", "computer", "native")):
                ms.append(nm)
        ms.sort(key=lambda x: ("lite" not in x, x))  # รุ่นเล็กเร็วก่อน
        print("โมเดล Gemini ที่ใช้ได้:", ms[:6])
        pref += ms[:4]
    except Exception as e:
        print("ดูรายชื่อโมเดล Gemini ไม่ได้:", e)
    pref += ["gemini-flash-latest", "gemini-flash-lite-latest"]
    out = []
    for m in pref:
        if m not in out:
            out.append(m)
    return out


def _gemini_call(model, key, prompt, think0):
    cfg = {"responseMimeType": "application/json", "temperature": 0.1}
    if think0:
        cfg["thinkingConfig"] = {"thinkingBudget": 0}  # ปิดโหมดคิดนาน ให้ตอบเร็ว
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg}).encode()
    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model, data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode("utf-8"))
    return json.loads(d["candidates"][0]["content"]["parts"][0]["text"])


def _gemini(names):
    """ให้ Gemini แปล/ทับศัพท์ชื่อทีมและลีกเป็นไทย ทีละ 40 ชื่อ คืน dict {ชื่อ: ไทย}"""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key or not names:
        return {}
    models = _gemini_models(key)
    res = {}
    t0 = time.time()
    for i in range(0, len(names), 40):
        if time.time() - t0 > 150:
            print("Gemini ใช้เวลานานเกินไป หยุดก่อน")
            break
        chunk = names[i:i + 40]
        prompt = ("แปลหรือทับศัพท์ชื่อทีมฟุตบอลและชื่อลีกต่อไปนี้เป็นภาษาไทย แบบที่สื่อกีฬาไทยเขียนทั่วไป "
                  "ชื่อทีมชาติให้ใช้ชื่อประเทศ ไม่ต้องใส่ FC หรือ SC ถ้าไม่จำเป็น "
                  "ตอบเป็น JSON object เท่านั้น key คือชื่อเดิมตามที่ให้ value คือชื่อไทย\n" + json.dumps(chunk, ensure_ascii=False))
        done = False
        for model in list(models):
            for think0 in (True, False):
                try:
                    out = _gemini_call(model, key, prompt, think0)
                    if isinstance(out, dict):
                        res.update({k: v for k, v in out.items() if isinstance(v, str) and re.search("[\u0e00-\u0e7f]", v)})
                        models.remove(model)
                        models.insert(0, model)  # โมเดลที่ใช้ได้ ใช้ต่อในชุดถัดไป
                        print("Gemini แปลได้ด้วย", model)
                        done = True
                        break
                except urllib.error.HTTPError as e:
                    print("Gemini", model, "ไม่ได้:", e)
                    if e.code != 400:
                        break  # 400 อาจเป็นเพราะรุ่นนี้ไม่รับ thinkingBudget ลองอีกครั้งแบบไม่ใส่
                except Exception as e:
                    print("Gemini", model, "ไม่ได้:", e)
                    break
            if done:
                break
    return res


def auto_names(names, cache, limit=150):
    """ชื่อทีม/ลีกที่ยังไม่มีไทยในรายการ ให้แปลอัตโนมัติ แล้วจำไว้ใน data.json (ชื่อที่ตั้งเองมีสิทธิ์ก่อนเสมอ)"""
    todo = []
    for n in names:
        b = _base(n)
        key = _norm(b)
        if key and key not in NAMES and key not in cache and (key, b) not in todo:
            todo.append((key, b))
    todo = todo[:limit]
    if not todo:
        return
    got = _gemini([b for _, b in todo])
    for key, b in todo:
        if b in got:
            cache[key] = got[b].strip()
    print("แปลชื่อด้วย Gemini", sum(1 for k, _ in todo if k in cache), "จาก", len(todo))
    todo = [(k, b) for k, b in todo if k not in cache]  # ที่ Gemini แปลไม่ได้ ใช้ตัวสำรองต่อ
    for key, b in todo[:80]:
        try:
            t = _gt(b)
            if t and re.search("[\u0e00-\u0e7f]", t):
                cache[key] = t
        except Exception as e:
            print("แปลชื่อไม่ได้:", b, e)
            if "429" in str(e):
                time.sleep(10)
                continue
            break
        time.sleep(1.5)
    print("ตัวสำรองแปลเพิ่ม; ยังไม่มีไทย", sum(1 for k, _ in todo if k not in cache), "ชื่อ")



def tn(n):
    k = "".join(c for c in unicodedata.normalize("NFD", n.lower()) if unicodedata.category(c) != "Mn")
    return NAMES.get(k) or NAMES.get(n.lower()) or n


def _swap(m, t):
    return t.replace(m["h"]["n"], tn(m["h"]["n"])).replace(m["a"]["n"], tn(m["a"]["n"]))


def best_pick(m):
    a = b = None
    ou, hp = m.get("ou"), m.get("hp")
    if ou and not ou["weak"] and ou["pct"] >= 55:
        g = m["hc"].split(" ต่อ ")[0] if m.get("hc") and " ต่อ " in m["hc"] else m["h"]["n"]
        a = (ou["pct"], "%s %s" % (tn(g), ou["lab"]), "ou")
    if hp:
        b = (hp["pct"], _swap(m, hp["lab"]), "hp")
    if a and b:
        return a if a[0] >= b[0] + 3 else b
    r = a or b
    return r if r and r[0] >= (55 if r[2] == "ou" else 60) else None


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
    picks.sort(key=lambda x: (0 if x[1].get("rk", 99) < 99 else 1, -x[0]))
    out = ["⚽️บอลวันที่ %s⚽️" % data["date"], ""]
    st = {"date": data["date"], "steps": [], "star": []}
    for n, icon in ((3, "⚡"), (5, "🔥"), (7, "💣")):
        if len(picks) < n:
            continue
        out.append("%s สเต็ป %d" % (icon, n))
        lines = []
        for _, m, txt, _k in sorted(select(picks, n), key=lambda x: x[1]["ts"]):
            out.append("⏰%s %s" % (m["t"].replace(":", "."), txt))
            lines.append({"t": m["t"].replace(":", "."), "x": txt, "id": m["id"], "k": _k})
        st["steps"].append({"n": n, "icon": icon, "lines": lines})
        out.append("————————————")
    if picks:
        out.append("⭐ ตัวเน้นสุด")
        for medal, (_, m, txt, _k) in zip("🥇🥈🥉", select(picks, 3)):
            out.append("%s %s" % (medal, txt))
            st["star"].append({"medal": medal, "x": txt, "id": m["id"], "k": _k})
        out.append("")
    build_message.struct = st
    return "\n".join(out).rstrip(), len(picks)


def summary_message(sent, history):
    """สรุปผลของข้อความที่แจกไป หน้าตาเหมือนเดิม แต่ใส่ ✅❌➖ ต่อท้ายแต่ละคู่ (⏳ = ยังไม่มีผล)"""
    res = {(e["id"], e.get("k")): e.get("res") for e in history}
    pend = [0]

    def mk(l):
        r = res.get((l["id"], l["k"]))
        if r is None:
            pend[0] += 1
            return "⏳"
        return "✅" if r > 0 else ("❌" if r < 0 else "➖")
    out = ["⚽️สรุปผลบอลวันที่ %s⚽️" % sent["date"], ""]
    for st in sent.get("steps", []):
        marks = [mk(l) for l in st["lines"]]
        verdict = "❌" if "❌" in marks else ("⏳" if "⏳" in marks else "✅")
        out.append("%s สเต็ป %d %s" % (st["icon"], st["n"], verdict))
        for l, m in zip(st["lines"], marks):
            out.append("%s ⏰%s %s" % (m, l["t"], l["x"]))
        out.append("————————————")
    if sent.get("star"):
        out.append("⭐ ตัวเน้นสุด")
        for x in sent["star"]:
            out.append("%s %s %s" % (x["medal"], mk(x), x["x"]))
    return "\n".join(out).rstrip(), pend[0]


def result_message(newly, history):
    out = ["📊 ผลที่เพิ่งออก", ""]
    for e in sorted(newly, key=lambda x: x["ts"]):
        if e.get("k") == "ou":
            pick = ("สูง " if e["s"] == "over" else "ต่ำ ") + str(e["lt"])
        else:
            pick = "%s %s%s" % (tn(e["team"]), "-" if e.get("giver") else "+", e["lt"])
        r = e["res"]
        ic = "✅" if r > 0 else ("❌" if r < 0 else "➖")
        out.append("%s %s (%s พบ %s) %s-%s" % (ic, pick, tn(e["hn"]), tn(e["an"]), e.get("gh"), e.get("ga")))
    done = [e for e in history if e.get("res") is not None]
    w = sum(1 for e in done if e["res"] > 0)
    l = sum(1 for e in done if e["res"] < 0)
    if w + l:
        out += ["", "สะสม เข้า %d ตาย %d (%d%%)" % (w, l, round(w * 100 / (w + l)))]
    return "\n".join(out)


def send_telegram(text):
    tok, chat = os.environ.get("TELEGRAM_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT", "").strip()
    if not tok or not chat:
        print("ไม่ได้ตั้งเทเลแกรม ข้ามการส่ง")
        return False
    body = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    try:
        urllib.request.urlopen("https://api.telegram.org/bot%s/sendMessage" % tok, data=body, timeout=30)
        print("ส่งเทเลแกรมแล้ว")
        return True
    except Exception as e:
        print("ส่งเทเลแกรมไม่สำเร็จ:", e)
        return False


def fetch_logos(matches, cache, limit=40):
    """หาโลโก้ทีมจาก TheSportsDB (ฟรี) ตามชื่อทีม เก็บแคชใน data.json ไม่ค้นซ้ำ"""
    todo = []
    for m in sorted(matches, key=lambda x: (x.get("nopick", False), x.get("rk", 99))):
        for x in (m["h"]["n"], m["a"]["n"]):
            if x not in cache and x not in todo:
                todo.append(x)
    for nm in todo[:limit]:
        url = "https://www.thesportsdb.com/api/v1/json/123/searchteams.php?t=" + urllib.parse.quote(nm)
        logo = ""
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
                d = json.loads(r.read().decode("utf-8"))
            for t in d.get("teams") or []:
                if t.get("strSport") == "Soccer" and t.get("strBadge"):
                    logo = t["strBadge"] + "/small"
                    break
        except Exception as e:
            print("โลโก้ไม่ได้:", nm, e)
            if "429" in str(e):
                break
            continue
        cache[nm] = logo
        time.sleep(2.2)  # ฟรี 30 ครั้งต่อนาที
    for m in matches:
        for k in ("h", "a"):
            if not m[k].get("l") and cache.get(m[k]["n"]):
                m[k]["l"] = cache[m[k]["n"]]


def main():
    try:
        run()
    except Quota as e:
        print("เครดิต/สิทธิ์ The Odds API มีปัญหา ไม่เขียนทับข้อมูลเดิม:", e)


def run():
    if not KEY:
        sys.exit("ไม่มี ODDS_API_KEY")
    history = []
    old = []
    old_snap = {}
    old_tn = {}
    old_logos = {}
    old_sent, old_prev, old_ssent = None, None, None
    try:
        with open("data.json", encoding="utf-8") as fh:
            _d = json.load(fh)
            history = _d.get("history", [])
            old = _d.get("matches", [])
            old_snap = _d.get("snap", {})
            old_tn = _d.get("tn", {})
            old_logos = _d.get("logos", {})
            old_sent, old_prev, old_ssent = _d.get("sent"), _d.get("prev"), _d.get("summary_sent")
            if os.environ.get("GITHUB_EVENT_NAME") == "schedule" and time.time() - _d.get("ts", 0) < 10 * 3600:
                print("ข้อมูลยังใหม่ (อัปเดตแล้วเมื่อไม่กี่ชั่วโมงก่อน) ข้ามรอบสำรอง")
                return
    except Exception:
        pass
    before = {(e["id"], e.get("k")) for e in history if e.get("res") is not None}
    try:
        settle(history)
    except Exception as e:
        print("เช็กผลไม่ได้:", e)
    history = [e for e in history if e.get("res") is not None or (e.get("sp") and e["ts"] > datetime.now(timezone.utc).timestamp() - 4 * 86400)]
    newly = [e for e in history if e.get("res") is not None and (e["id"], e.get("k")) not in before]
    now = datetime.now(timezone.utc)
    # "บอลวันที่ X" = เตะตั้งแต่ 06:00 วัน X ถึง 06:00 ของวันถัดไป (เวลาไทย) คู่ที่เลยเที่ยงคืนยังนับเป็นของวัน X
    fd = (now.astimezone(TH) - timedelta(hours=6)).date()
    end = (datetime(fd.year, fd.month, fd.day, 6, tzinfo=TH) + timedelta(days=1)).astimezone(timezone.utc)
    out, odds_map = fetch_all(now, end, old)
    out = list({x[1]["fixture"]["id"]: x for x in out}.values())
    out = [x for x in out if x[1]["fixture"]["id"] in odds_map or x[1]["fixture"]["id"] in {m.get("id") for m in old}]
    out.sort(key=lambda x: x[0])
    out = out[:MAX_MATCHES]
    elo_map = load_elo()
    matches = []
    # ล็อกคู่เด็ดเดิมที่ยังไม่เตะ ไม่เปลี่ยนคู่ที่แจกไปแล้ว
    locked = {m["id"]: m for m in old
              if m.get("id") and m.get("v") == 4 and not m.get("nopick") and m["ts"] > now.timestamp() and (m.get("hp") or (m.get("ou") and not m["ou"].get("weak")))}
    # คู่ที่จะคิดใหม่ (ไม่ได้ล็อก) ให้ลบรายการที่ยังไม่มีผลของคู่นั้นในประวัติ จะได้ไม่ค้างตัวเลือกเก่า
    redo = {x[1]["fixture"]["id"] for x in out} - set(locked)
    history = [e for e in history if not (e.get("res") is None and e["id"] in redo)]
    snap = {k: v for k, v in old_snap.items() if v.get("ts", 0) > now.timestamp() - 86400}
    bad_kind, bad_lg = calibrate(history)
    cands = []
    others = []
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
        if pr:  # ทีมเต็งจาก % ชนะ (ต้องชนะ 60%+ และ Elo เห็นตรงกัน) แล้วใช้บรรทัดต่อรองจริงของตลาด
            fav = "home" if pr["h"] >= pr["a"] else "away"
            if max(pr["h"], pr["a"]) < 60:
                fav = None
            if fav and e is not None and ((e >= 50) != (fav == "home") or max(e, 100 - e) < 55):
                fav = None
            if fav:
                cand = []
                for line, ph in ah_ladder(books):
                    ht = line if fav == "home" else -line   # แต้มต่อของทีมเต็ง (ลบ = ต่อ)
                    pc = ph if fav == "home" else 1 - ph    # โอกาสผ่านราคาของทีมเต็งที่บรรทัดนี้
                    if -6 <= ht <= 6:
                        cand.append((abs(pc - 0.5), ht, pc))
                if cand:
                    _, ht, pc = min(cand)
                    team = h["name"] if fav == "home" else a["name"]
                    sgn = "-" if ht < 0 else "+"
                    lt = thai_line(abs(ht)) if ht != 0 else "0"
                    hp = {"lab": "%s %s%s" % (team, sgn if ht != 0 else "", lt), "pct": pr["h"] if fav == "home" else pr["a"],
                          "cp": round(pc * 100), "team": team, "giver": ht < 0, "lt": lt, "side": fav, "h": ht}
        if ou and ou["pct"] < 55:
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
        cc = {"t": t, "f": f, "h": h, "a": a, "hc": hc, "ou": ou, "hp": hp, "pr": pr, "e": e,
              "hcs": hcs, "ous": ous, "flag": flag, "lg": lg,
              "top": max(ou["pct"] if ou and not ou["weak"] else 0, hp["pct"] if hp else 0)}
        if (ou and not ou["weak"]) or hp:
            cands.append(cc)
        else:
            others.append(cc)
    # 3) เช็กด้วยสถิติประตูย้อนหลัง (โมเดลปัวซอง) เฉพาะคู่ที่ผ่านด่านก่อนหน้า และเรียงโอกาสสูงสุดก่อน
    cands.sort(key=lambda c: -c["top"])
    cands = cands[:MAX_MODEL]
    form = {}
    use_model = False  # แหล่งนี้ไม่มีสถิติย้อนหลัง
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
            others.append(c)
            continue
        h, a, e = c["h"], c["a"], c["e"]
        if not any(x["id"] == f["fixture"]["id"] for x in history):
            base = {"id": f["fixture"]["id"], "ts": int(t.timestamp()), "d": "%02d/%02d" % (t.day, t.month),
                    "hn": h["name"], "an": a["name"], "lg": c["lg"], "sp": f["league"]["id"], "res": None}
            if ou and not ou["weak"]:
                history.append(dict(base, k="ou", s=ou["s"], x=ou["x"], lt=ou["line"], pct=ou["pct"]))
            if hp:
                history.append(dict(base, k="hp", side=hp["side"], h=hp["h"], lt=hp["lt"], team=hp["team"],
                                    giver=hp["giver"], pct=hp["pct"]))
        matches.append({
            "v": 4, "id": f["fixture"]["id"], "t": t.strftime("%H:%M"), "d": DAYS[t.weekday()], "ts": int(t.timestamp()),
            "flag": c["flag"], "lg": c["lg"], "rk": ORDER.index(f["league"]["id"]) if f["league"]["id"] in LEAGUES else 99,
            "h": {"n": h["name"], "l": h["logo"]}, "a": {"n": a["name"], "l": a["logo"]},
            "hc": c["hc"], "ou": ou, "hp": hp, "pr": c["pr"], "elo": round(e) if e is not None else None,
            "hcs": c["hcs"], "ous": c["ous"],
        })
    nodds = [f for t, f in out if f["fixture"]["id"] not in odds_map and f["league"]["id"] in LEAGUES]
    for f in nodds:
        print("ไม่มีราคา:", f["league"]["name"], f["teams"]["home"]["name"], "-", f["teams"]["away"]["name"])
    for c in others:
        if c["f"]["league"]["id"] in LEAGUES:
            print("ไม่ผ่านเกณฑ์:", c["lg"], c["h"]["name"], "-", c["a"]["name"],
                  "| สูง/ต่ำ", (c["ou"] or {}).get("pct"), "| ชนะ", c["pr"])
    for c in others:  # คู่ที่ไม่ผ่านเกณฑ์ ใส่ไว้ดูในแท็บ "ทุกคู่" เท่านั้น ไม่เข้าสเต็ป
        t, f, h, a, e = c["t"], c["f"], c["h"], c["a"], c["e"]
        if c["ou"]:
            c["ou"]["weak"] = True
        matches.append({
            "v": 4, "id": f["fixture"]["id"], "t": t.strftime("%H:%M"), "d": DAYS[t.weekday()], "ts": int(t.timestamp()),
            "flag": c["flag"], "lg": c["lg"], "rk": ORDER.index(f["league"]["id"]) if f["league"]["id"] in LEAGUES else 99,
            "h": {"n": h["name"], "l": h["logo"]}, "a": {"n": a["name"], "l": a["logo"]},
            "hc": c["hc"], "ou": c["ou"], "hp": None, "pr": c["pr"], "elo": round(e) if e is not None else None,
            "hcs": c["hcs"], "ous": c["ous"], "nopick": True,
        })
    matches.sort(key=lambda m: m["ts"])
    names = []
    for m in matches:
        for x in (m["h"]["n"], m["a"]["n"], m["lg"]):
            if x not in names:
                names.append(x)
    try:
        auto_names(names, old_tn)
    except Exception as e:
        print("แปลชื่อพลาด:", e)
    for k, v in old_tn.items():
        NAMES.setdefault(k, v)
    try:
        fetch_logos(matches, old_logos)
    except Exception as e:
        print("โลโก้พลาด:", e)
    nt = datetime.now(TH)
    data = {"ts": int(time.time()), "updated": "%s %02d/%02d %s น." % (DAYS[nt.weekday()], nt.day, nt.month, nt.strftime("%H:%M")),
            "date": "%d/%d/%s" % (fd.day, fd.month, str(fd.year + 543)[2:]), "matches": matches,
            "history": sorted(history, key=lambda e: e["ts"])[-150:], "snap": snap, "tn": old_tn, "logos": old_logos}
    text, n = build_message(data)
    sent_now = build_message.struct if n else (old_sent if old_sent and old_sent.get("date") == data["date"] else None)
    prev = old_prev
    if old_sent and old_sent.get("date") != data["date"]:
        prev = old_sent  # วันบอลเปลี่ยนแล้ว ชุดที่แจกเมื่อวานกลายเป็นชุดที่ต้องสรุปผล
    summ, pend = (summary_message(prev, data["history"]) if prev else (None, 0))
    data["sent"], data["prev"] = sent_now, prev
    data["summary"] = {"date": prev["date"], "text": summ, "pending": pend} if summ else None
    data["summary_sent"] = old_ssent
    do_send = os.environ.get("SEND") == "1" or os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    if do_send and summ and pend == 0 and old_ssent != prev["date"]:
        if send_telegram(summ):
            data["summary_sent"] = prev["date"]
    with open("data.json", "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    print("เขียน data.json แล้ว %d คู่" % len(matches))
    if os.environ.get("SEND") == "1" or os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        if newly:
            send_telegram(result_message(newly, data["history"]))
        if n:
            send_telegram(text)


if __name__ == "__main__":
    main()
