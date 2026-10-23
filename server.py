import math
import shutil
from pathlib import Path
import urllib.parse
import json
import os,re,json,time,threading,urllib.request,urllib.parse,subprocess,sys,webbrowser
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from datetime import datetime
ROOT=os.path.dirname(os.path.abspath(__file__)); PORT=8847; DATA=os.path.join(ROOT,"data.json")
WATCH={"9984":("ソフトバンクグループ","99840"),"5803":("フジクラ","58030"),"7974":("任天堂","79740"),"5801":("古河電工","58010")}
STATE={"running":False,"ok":None,"step":"待機中","date":None,"error":None,"elapsed":0}

def fitzmod():
    try: import pymupdf; return pymupdf
    except:
        subprocess.check_call([sys.executable,"-m","pip","install","pymupdf","-q"])
        import pymupdf; return pymupdf

def latest_pdf():
    page="https://www.jpx.co.jp/markets/statistics-equities/margin/01.html"
    req=urllib.request.Request(page,headers={"User-Agent":"Mozilla/5.0"})
    h=urllib.request.urlopen(req,timeout=25).read().decode("utf-8","ignore")
    links=[urllib.parse.urljoin(page,x) for x in re.findall(r'href=["\']([^"\']+\.pdf[^"\']*)',h,re.I)]
    links=[x for x in links if "mtall" in x.lower()]
    if not links: raise RuntimeError("JPX PDFリンク未取得")
    def k(u):
        m=re.search(r'(20\d{6})',u); return m.group(1) if m else ""
    u=max(links,key=k); m=re.search(r'(20\d{2})(\d\d)(\d\d)',u)
    return u,(f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else "")

def ni(t): return int(re.sub(r"\D","",t))
def extract(words,target):
    hits=[w for w in words if re.sub(r'[^0-9A-Za-z]','',str(w[4]))==target]
    cand=[]
    for cw in hits:
        cx=(cw[0]+cw[2])/2
        vals=[(float(q[1]),str(q[4])) for q in words if abs(((q[0]+q[2])/2)-cx)<=2.8 and re.fullmatch(r'[\d,]+',str(q[4]))]
        if vals: cand.append((sum(ni(t) for _,t in vals[:4]),vals))
    if not cand:return None
    vals=min(cand,key=lambda z:z[0])[1]
    def at(y):
        z=[(abs(a-y),t) for a,t in vals if abs(a-y)<=5]
        return ni(min(z)[1]) if z else None
    buy,sell=at(75.6),at(241.2)
    if buy is None or sell is None:return None
    return {"buy":buy,"sell":sell,"ratio":round(buy/sell,4) if sell else None}

def valid_data(path):
    try:
        with open(path,encoding="utf-8") as f: data=json.load(f)
        if isinstance(data,dict) and isinstance(data.get("stocks"),dict):
            return len(data["stocks"])
    except (OSError,ValueError,TypeError):
        pass
    return -1

def initialize_data():
    """Never overwrite a preexisting data.json; prefer a sibling's real watchlist."""
    if os.path.exists(DATA):
        if valid_data(DATA)<0:
            raise RuntimeError("data.json が読み取れません。上書きせず停止します。バックアップを確認してください。")
        print("既存の登録データを使用:",DATA,flush=True)
        return
    parent=Path(ROOT).parent
    candidates=[]
    for sibling in parent.iterdir():
        if not sibling.is_dir() or sibling.resolve()==Path(ROOT).resolve():continue
        if not re.search(r"(?:seido.dashboard|V14[_ .-]?\d+)",sibling.name,re.I):continue
        f=sibling/'data.json';count=valid_data(f)
        if count>=0:
            candidates.append((count,f.stat().st_mtime,f))
    if candidates:
        count,_,source=max(candidates)
        shutil.copy2(source,DATA)
        print(f"以前の登録データを引き継ぎ: {source} ({count}銘柄)",flush=True)
    else:
        shutil.copy2(os.path.join(ROOT,'data_seed.json'),DATA)
        print("旧バージョンが見つからないため初期データを使用。旧フォルダは削除しないでください。",flush=True)

def backup_data():
    """Create one pre-change snapshot per day, retaining the latest 14."""
    if not os.path.isfile(DATA):return
    folder=Path(ROOT)/'backups';folder.mkdir(exist_ok=True)
    stamp=datetime.now().strftime('%Y%m%d')
    dest=folder/f'data_before_change_{stamp}.json'
    if not dest.exists():shutil.copy2(DATA,dest)
    backups=sorted(folder.glob('data_before_change_*.json'))
    for old in backups[:-14]:old.unlink()

def load():
    with open(DATA,encoding="utf-8") as f:return json.load(f)
def save(d):
    backup_data()
    tmp=DATA+".tmp"
    with open(tmp,"w",encoding="utf-8") as f:json.dump(d,f,ensure_ascii=False,indent=2)
    os.replace(tmp,DATA)

def update():
    t=time.time(); STATE.update(running=True,ok=None,step="JPXページ",error=None,elapsed=0)
    try:
        pm=fitzmod(); u,date=latest_pdf(); STATE.update(step="PDFダウンロード",date=date)
        req=urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}); raw=urllib.request.urlopen(req,timeout=25).read()
        doc=pm.open(stream=raw,filetype="pdf")
        d0=load()
        dynamic_watch={str(c):(st.get("name") or str(c),str(c)+"0") for c,st in d0.get("stocks",{}).items() if re.fullmatch(r"(?:\d{4}|\d{3}[A-Z])",str(c))}
        rem=set(dynamic_watch); out={}
        for i,p in enumerate(doc):
            STATE["step"]=f"PDF解析 {i+1}/{len(doc)}"
            words=p.get_text("words",sort=False)
            for c in list(rem):
                r=extract(words,dynamic_watch[c][1])
                if r: out[c]=r; rem.remove(c)
            if not rem:break
        doc.close()
        missing=sorted(rem)
        d=load()
        for c,r in out.items():
            st=d["stocks"][c]; h=[x for x in st["history"] if x["date"]!=date]
            h.append({"date":date,**r}); h.sort(key=lambda x:x["date"]); st["history"]=h[-400:]
        save(d); STATE.update(running=False,ok=True,step=("完了" if not missing else "完了 / 未取得 "+",".join(missing)),elapsed=round(time.time()-t,1))
    except Exception as e:
        STATE.update(running=False,ok=False,step="エラー",error=f"{type(e).__name__}: {e}",elapsed=round(time.time()-t,1))



def latest_margin_for_code(code):
    pm=fitzmod()
    u,date=latest_pdf()
    req=urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"})
    raw=urllib.request.urlopen(req,timeout=25).read()
    doc=pm.open(stream=raw,filetype="pdf")
    target=str(code)+"0"
    found=None
    for p in doc:
        found=extract(p.get_text("words",sort=False),target)
        if found: break
    doc.close()
    return date,found


def fetch_text(url,timeout=12):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Accept-Language":"ja,en;q=0.7"})
    return urllib.request.urlopen(req,timeout=timeout).read().decode("utf-8","ignore")

def strip_tags(x):
    import html as _html
    x=re.sub(r"<script\b[^>]*>.*?</script>"," ",x,flags=re.I|re.S)
    x=re.sub(r"<style\b[^>]*>.*?</style>"," ",x,flags=re.I|re.S)
    x=re.sub(r"<[^>]+>"," ",x)
    return re.sub(r"\s+"," ",_html.unescape(x)).strip()

def yahoo_valuation_history(code):
    """Only read values in a labeled Yahoo stock time-series row; no global number search."""
    from html.parser import HTMLParser
    class Rows(HTMLParser):
        def __init__(self):super().__init__();self.rows=[];self.row=None;self.cell=None
        def handle_starttag(self,t,a):
            if t=='tr':self.row=[]
            if self.row is not None and t in ('td','th'):self.cell=[]
        def handle_data(self,d):
            if self.cell is not None:self.cell.append(d)
        def handle_endtag(self,t):
            if t in ('td','th') and self.cell is not None and self.row is not None:self.row.append(''.join(self.cell).strip());self.cell=None
            if t=='tr' and self.row is not None:self.rows.append(self.row);self.row=None
    raw=fetch_text(f'https://finance.yahoo.co.jp/quote/{code}.T/history',12)
    parser=Rows();parser.feed(raw)
    for i,row in enumerate(parser.rows):
        labels=' '.join(row)
        if ('PER' in labels and 'PBR' in labels) and ('日付' in labels or '年月日' in labels):
            pi=next((j for j,v in enumerate(row) if 'PER' in v),None)
            bi=next((j for j,v in enumerate(row) if 'PBR' in v),None)
            if pi is None or bi is None:continue
            for rr in parser.rows[i+1:i+8]:
                if len(rr)<=max(pi,bi) or not re.search(r'20\d\d[/年.-]',rr[0]):continue
                found={}
                for k,idx in [('per',pi),('pbr',bi)]:
                    mm=re.search(r'(?<!\d)(\d{1,4}(?:\.\d{1,2})?)(?!\d)',rr[idx].replace(',',''))
                    if mm and 0<float(mm.group(1))<1000:found[k]=mm.group(1)+'倍'
                if found:return found
    return {}

def parse_analyst_consensus(plain,source):
    """Extract only explicitly labeled analyst consensus; never site stock diagnosis."""
    patterns = [
        r'目標株価の平均\s*([0-9]{1,3}(?:,[0-9]{3})*|[0-9]{3,6})\s*円',
        r'アナリストの平均目標株価は\s*([0-9]{1,3}(?:,[0-9]{3})*|[0-9]{3,6})\s*円',
        r'目標株価\s*\(コ\)\s*株価かい離率\s*([0-9]{1,3}(?:,[0-9]{3})*|[0-9]{3,6})\s*円',
        r'目標株価\s*\(コンセンサス\)\s*([0-9]{1,3}(?:,[0-9]{3})*|[0-9]{3,6})\s*円',
    ]
    for pat in patterns:
        m=re.search(pat,plain,re.S)
        if m:
            price=int(m.group(1).replace(',',''))
            if 50<=price<=1000000:
                return {'target':f'{price:,}円','target_source':source,
                        'target_kind':'アナリスト平均（コンセンサス）'}
    return None

def analyst_consensus_target(code):
    """Use explicitly labeled consensus from IFIS; no blocking bypass or estimates."""
    if not re.fullmatch(r'(?:\d{4}|\d{3}[A-Z])',str(code)):return {}
    errors=[]
    sources=[
      (f"https://ko5yqxb8d4.execute-api.ap-northeast-1.amazonaws.com/reportTarget?bcode={code}",'株予報Pro・目標株価'),
      (f"https://kabuyoho.jp/reportTarget?bcode={code}",'株予報Pro・目標株価'),
      (f"https://ko5yqxb8d4.execute-api.ap-northeast-1.amazonaws.com/reportAnalyst?bcode={code}",'株予報Pro・コンセンサス'),
      (f"https://kabuyoho.jp/reportAnalyst?bcode={code}",'株予報Pro・コンセンサス'),
    ]
    for url,source in sources:
        try:
            plain=strip_tags(fetch_text(url,6))
            parsed=parse_analyst_consensus(plain,source)
            if parsed:
                parsed['target_url']=url
                return parsed
            errors.append(source+': 平均目標株価を抽出できません')
        except Exception as e:
            errors.append(source+': '+str(e)[:85])
    return {'target_error':' / '.join(errors)}

def japanese_stock_info(code):
    out={"name":str(code),"per":"—","pbr":"—","yield":"—","target":"—","earnings":"—","aggregate":"—","rights_final":"—","ex_date":"—","pbr_source":"unavailable"}
    try:
        vals=yahoo_valuation_history(code)
        for k,v in vals.items():out[k]=v;out[k+'_source']='yahoo_history_table'
    except Exception as e:out['history_metric_error']=str(e)
    # Parse Yahoo's OWN company quote "参考指標" only. Never search sidebars or
    # unrelated recommendations for valuation numbers.
    try:
        raw=fetch_text(f"https://finance.yahoo.co.jp/quote/{code}.T")
        title=re.search(r"<title>(.*?)</title>",raw,re.I|re.S)
        if title:
            name=re.split(r"【|\(|（| - |：|:",strip_tags(title.group(1)))[0].strip()
            name=re.sub(r"\s*\d{4}(?:\.T)?\s*$","",name).strip()
            if name and 'Yahoo' not in name:out['name']=name
        # Use the quote section between "参考指標" and "信用取引情報".
        # Do not use any number if the page layout cannot be recognized.
        heading=re.search(r"(?:<h[1-6][^>]*>\s*参考指標\s*</h[1-6]>|参考指標)",raw,re.I)
        if heading:
            section=raw[heading.end():heading.end()+25000]
            stop=re.search(r"信用取引情報|<h[12][^>]*>.*?(?:ニュース|業績)",section,re.I|re.S)
            if stop:section=section[:stop.start()]
            t=strip_tags(section)
            # Actual quote labels on Yahoo: 株価収益率 (PER), 純資産倍率 (PBR).
            pats={
              'per':[r'(?:株価収益率|PER)(?:\s*[（(][^）)]{0,25}[）)])?\s*(?:用語\s*)?(?:---\s*)?([0-9][0-9,]*(?:\.[0-9]+)?)\s*倍'],
              'pbr':[r'(?:純資産倍率|PBR)(?:\s*[（(][^）)]{0,25}[）)])?\s*(?:用語\s*)?(?:---\s*)?([0-9][0-9,]*(?:\.[0-9]+)?)\s*倍'],
              'yield':[r'(?:配当利回り|予想配当利回り)(?:\s*[（(][^）)]{0,25}[）)])?\s*(?:用語\s*)?([0-9][0-9,]*(?:\.[0-9]+)?)\s*[%％]']
            }
            for key,patterns in pats.items():
                for pat in patterns:
                    m=re.search(pat,t,re.I)
                    if m:
                        v=float(m.group(1).replace(',',''))
                        if (0.01<v<1000 if key!='yield' else 0<=v<100):
                            out[key]=f'{v:g}'+('%' if key=='yield' else '倍')
                            out[key+'_source']='yahoo_reference'
                            break
            # Overall credit ratio is distinct from JPX daily margin ratio.
            m=re.search(r'信用倍率\s*(?:用語)?\s*([0-9]+(?:\.[0-9]+)?)\s*倍',strip_tags(raw[heading.end():heading.end()+50000]))
            if m:out['aggregate']=m.group(1)+'倍'
    except Exception as e:out['metric_error']=str(e)
    try:
        raw=fetch_text(f"https://kabutan.jp/stock/?code={code}")
        txt=strip_tags(raw)
        if out['name']==str(code):
            mt=re.search(r"\b"+re.escape(code)+r"\b\s+(.{1,40}?)(?:\s+\d|株価|基本情報)",txt)
            if mt:out['name']=mt.group(1).strip()
        # Kabutan's stock header contains a compact, issue-specific valuation row.
        # Require the three labels together, rather than matching arbitrary "1倍" elsewhere.
        if out['per']=='—' or out['pbr']=='—' or out['yield']=='—':
            for block in re.findall(r'<(?:table|div|section)\b[^>]*>.*?</(?:table|div|section)>',raw,re.I|re.S):
                plain=strip_tags(block)
                if not ('PER' in plain and 'PBR' in plain and ('利回り' in plain or '配当' in plain)):
                    continue
                # Kabutan labels precede their respective values, with small gaps.
                for key,pat,unit in (
                    ('per',r'PER\s*(?:\([^)]*\))?\s*([0-9]+(?:\.[0-9]+)?)\s*倍','倍'),
                    ('pbr',r'PBR\s*(?:\([^)]*\))?\s*([0-9]+(?:\.[0-9]+)?)\s*倍','倍'),
                    ('yield',r'(?:配当)?利回り\s*([0-9]+(?:\.[0-9]+)?)\s*[%％]','%')):
                    if out[key]=='—':
                        mm=re.search(pat,plain,re.I)
                        if mm:out[key]=mm.group(1)+unit
                if out['pbr']!='—':out['pbr_source']='kabutan_header'
                if all(out[k]!='—' for k in ('per','pbr','yield')):break
        # On Kabutan, valuation values may be in table cells BEFORE their headings.
        # Limit extraction to the first table with all three headings and a compact length.
        if any(out[k]=='—' for k in ('per','pbr','yield')):
            for table in re.findall(r'<table\b[^>]*>.*?</table>',raw,re.I|re.S):
                plain=strip_tags(table)
                if not (20<len(plain)<2500 and 'PER' in plain and 'PBR' in plain and '利回り' in plain):continue
                cells=[strip_tags(x).strip() for x in re.findall(r'<t[dh]\b[^>]*>(.*?)</t[dh]>',table,re.I|re.S)]
                for k,label,unit in [('per','PER','倍'),('pbr','PBR','倍'),('yield','利回り','%')]:
                    if out[k]!='—':continue
                    for i,c in enumerate(cells):
                        if not re.search(label,c,re.I):continue
                        for v in cells[max(0,i-1):min(len(cells),i+3)]:
                            m=re.fullmatch(r'\s*([0-9]+(?:\.[0-9]+)?)\s*(?:倍|[%％])?\s*',v)
                            if m:
                                num=float(m.group(1))
                                if 0<num<(100 if k=='yield' else 1000):
                                    out[k]=f'{num:g}'+unit;out[k+'_source']='kabutan_valuation_table'
                                    break
                        if out[k]!='—':break
                break
        # Never take PER/PBR from Kabutan's unscoped page: "1倍" was a false match.
        # Match only an explicitly announced FUTURE earnings date.
        for pattern in [
            r"決算発表予定日\s*[:：]?\s*(20\d{2})[/-](\d{1,2})[/-](\d{1,2})(?:\s+(\d{1,2}:\d{2}))?",
            r"次回決算発表(?:予定日)?\s*[:：]?\s*(20\d{2})[/-](\d{1,2})[/-](\d{1,2})(?:\s+(\d{1,2}:\d{2}))?",
        ]:
            mm=re.search(pattern,txt)
            if mm:
                from datetime import date
                day=date(int(mm.group(1)),int(mm.group(2)),int(mm.group(3)))
                if day>=date.today():
                    out["earnings"]=f"{day.year}/{day.month}/{day.day}"+((" "+mm.group(4)) if mm.group(4) else "")
                    break
    except: pass
    # Keep source-provided PER, including for 9984. Never force a placeholder.
    out["per_note"]=""
    if out["earnings"]=="—":
        try:
            raw=fetch_text(f"https://s.kabutan.jp/stocks/{code}/")
            txt=strip_tags(raw)
            mm=re.search(r"決算発表予定日\s*[:：]?\s*(20\d{2})[/-](\d{1,2})[/-](\d{1,2})",txt)
            if mm:
                from datetime import date
                day=date(int(mm.group(1)),int(mm.group(2)),int(mm.group(3)))
                if day>=date.today():out["earnings"]=f"{day.year}/{day.month}/{day.day}"
        except Exception:pass
    # Structured quote data: parse only key/value JSON, not arbitrary page text.
    # Some Yahoo pages embed a quoteSummary-style object; only accept issue-specific fields.
    try:
        raw=fetch_text(f"https://finance.yahoo.co.jp/quote/{code}.T",10)
        import html as _ht
        raw=_ht.unescape(raw)
        fields={"per":("trailingPE","forwardPE"),"pbr":("priceToBook",),"yield":("dividendYield",)}
        for field,keys in fields.items():
            if out[field]!='—':continue
            for key in keys:
                mm=re.search(r'["\\]'+re.escape(key)+r'["\\]\s*:\s*(?:\{\s*["\\]raw["\\]\s*:\s*)?([0-9]+(?:\.[0-9]+)?)',raw)
                if not mm:continue
                val=float(mm.group(1))
                if field=='yield' and val<1:val*=100
                if (0<val<1000 if field!='yield' else 0<=val<100):
                    out[field]=f"{val:.2f}"+("%" if field=='yield' else "倍")
                    out[field+'_source']='yahoo_structured_'+key
                    break
    except Exception as e:out['structured_error']=str(e)
    for k in ('per','pbr','yield'):
        out.setdefault(k+'_source','unavailable' if out[k]=='—' else 'quote_page')
    out.update(analyst_consensus_target(code))
    return out

def margin_pdf_links():
    page="https://www.jpx.co.jp/markets/statistics-equities/margin/01.html"
    raw=fetch_text(page,20)
    hrefs=re.findall(r'href=["\x27]([^"\x27]+\.pdf[^"\x27]*)',raw,re.I)
    links=[urllib.parse.urljoin(page,x) for x in hrefs if "mtall" in x.lower()]
    uniq={}
    for u in links:
        mm=re.search(r'(20\d{6})',u)
        if mm: uniq[mm.group(1)]=u
    return [(d,uniq[d]) for d in sorted(uniq,reverse=True)]

_MARGIN_HISTORY_CACHE={}
def recent_margin_history(code,limit=65):
    now=time.time(); cached=_MARGIN_HISTORY_CACHE.get(str(code))
    if cached and now-cached[0]<1800:return cached[1]
    pm=fitzmod(); target=str(code)+"0"; rows=[]
    for ds,u in margin_pdf_links()[:max(limit,1)]:
        try:
            raw=urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=20).read()
            doc=pm.open(stream=raw,filetype="pdf"); found=None
            for p in doc:
                found=extract(p.get_text("words",sort=False),target)
                if found:break
            doc.close()
            if found:rows.append({"date":f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}",**found})
        except:pass
    rows.sort(key=lambda x:x["date"]); rows=rows[-limit:]
    _MARGIN_HISTORY_CACHE[str(code)]=(now,rows)
    return rows

def yahoo_quote(symbol):
    # Current/last traded price and previous close come from the SAME chart response.
    # Do not use the last daily candle as "current price": during the session it can be stale/incomplete.
    q=urllib.parse.quote(symbol,safe="")
    req=urllib.request.Request(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?interval=1m&range=1d&includePrePost=false",
        headers={"User-Agent":"Mozilla/5.0"}
    )
    with urllib.request.urlopen(req,timeout=10) as rr:
        jj=json.loads(rr.read().decode("utf-8"))
    r=jj["chart"]["result"][0]
    meta=r.get("meta",{}) or {}
    price=meta.get("regularMarketPrice")
    prev=meta.get("chartPreviousClose")
    if prev is None:
        prev=meta.get("previousClose")
    # Fallback only for current price: latest intraday trade in the same response.
    if price is None:
        closes=r.get("indicators",{}).get("quote",[{}])[0].get("close",[]) or []
        valid=[float(x) for x in closes if x is not None]
        if valid: price=valid[-1]
    if price is None or prev is None:
        raise ValueError("current price / previous close unavailable")
    price=float(price); prev=float(prev)
    change=price-prev
    pct=(change/prev*100.0) if prev else None
    return {"price":price,"prev":prev,"change":change,"pct":pct}

def growth250_kabutan_pc():
    raw=fetch_text('https://kabutan.jp/stock/?code=0012',12)
    txt=strip_tags(raw)
    pos=txt.find('東証グロース市場250')
    if pos<0:raise ValueError('index title not found')
    area=txt[pos:pos+1500]
    mm=re.search(r'([0-9]{3,4}\.[0-9]{1,2})\s*\(([+-]?[0-9]+(?:\.[0-9]+)?)%\)',area)
    if not mm:
        mm=re.search(r'([0-9]{3,4}\.[0-9]{1,2})\s*([+-][0-9]+\.[0-9]+)\s*\(([+-]?[0-9]+(?:\.[0-9]+)?)%\)',area)
        if not mm:raise ValueError('growth index quote pattern unavailable')
        price=float(mm.group(1));change=float(mm.group(2));prev=price-change
    else:
        price=float(mm.group(1));pct=float(mm.group(2));prev=price/(1+pct/100)
        change=price-prev
    if not (100<price<3000 and prev>0):raise ValueError('growth index range invalid')
    return {'price':price,'prev':prev,'change':change,'pct':change/prev*100}

def growth250_quote():
    # Kabutan's index page publishes the Growth Market 250 current value and day change.
    u="https://s.kabutan.jp/stocks/0012/historical_prices/daily/"
    req=urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"})
    html=urllib.request.urlopen(req,timeout=10).read().decode("utf-8","ignore")
    txt=re.sub(r"<[^>]+>"," ",html)
    txt=re.sub(r"\s+"," ",txt)
    # Look around the index title, then take value / day change / day-change %.
    pos=txt.find("東証グロース市場250指数")
    area=txt[pos:pos+1800] if pos>=0 else txt[:2500]
    nums=re.findall(r'(?<![\d/])([0-9]{3,4}\.[0-9]{1,2})',area)
    pcts=re.findall(r'([+-]\s*[0-9]+\.[0-9]+)\s*%',area)
    changes=re.findall(r'([+-]\s*[0-9]+\.[0-9]{1,2})(?!\s*%)',area)
    if not nums or not pcts:
        raise RuntimeError("Growth250 parse failed")
    price=float(nums[0].replace(",",""))
    pct=float(pcts[0].replace(" ",""))
    # derive previous close robustly from price and percent
    prev=price/(1+pct/100.0) if pct!=-100 else None
    change=price-prev if prev else None
    return {"price":price,"prev":prev,"change":change,"pct":pct}



def yahoo_daily_history(symbol, range_="6mo"):
    q=urllib.parse.quote(symbol,safe="")
    req=urllib.request.Request(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?interval=1d&range={range_}",
        headers={"User-Agent":"Mozilla/5.0"}
    )
    with urllib.request.urlopen(req,timeout=10) as rr:
        jj=json.loads(rr.read().decode("utf-8"))
    r=jj["chart"]["result"][0]
    ts=r.get("timestamp",[]) or []
    closes=r.get("indicators",{}).get("quote",[{}])[0].get("close",[]) or []
    pts=[]
    for t,c in zip(ts,closes):
        if c is not None:
            d=datetime.fromtimestamp(int(t)).strftime("%Y-%m-%d")
            pts.append({"date":d,"close":float(c)})
    return pts

def topix_jp_daily_history():
    raw=fetch_text('https://finance.yahoo.co.jp/quote/998405.T/history',12)
    txt=strip_tags(raw)
    rows=re.findall(r'(20\d{2}/\d{1,2}/\d{1,2})\s+([0-9,]+\.[0-9]+)\s+([0-9,]+\.[0-9]+)\s+([0-9,]+\.[0-9]+)\s+([0-9,]+\.[0-9]+)',txt)
    if len(rows)<2:raise ValueError('Yahoo Japan TOPIX daily table not found')
    pts=sorted({d:float(close.replace(',','')) for d,_,_,_,close in rows}.items())
    return [{'date':d.replace('/','-'),'close':v} for d,v in pts]

def yahoo_intraday(symbol):
    q=urllib.parse.quote(symbol,safe="")
    req=urllib.request.Request(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?interval=5m&range=1d&includePrePost=false",
        headers={"User-Agent":"Mozilla/5.0"}
    )
    with urllib.request.urlopen(req,timeout=10) as rr:
        jj=json.loads(rr.read().decode("utf-8"))
    r=jj["chart"]["result"][0]
    meta=r.get("meta",{})
    ts=r.get("timestamp",[]) or []
    closes=r.get("indicators",{}).get("quote",[{}])[0].get("close",[]) or []
    pts=[]
    for t,c in zip(ts,closes):
        if c is not None: pts.append([int(t),float(c)])
    prev=meta.get("regularMarketPreviousClose") or meta.get("chartPreviousClose")
    price=meta.get("regularMarketPrice")
    return {"points":pts,"prev":float(prev) if prev is not None else None,
            "price":float(price) if price is not None else (pts[-1][1] if pts else None)}

def official_jpx_indices():
    """Parse official JPX major-index rows, not unrelated figures elsewhere on the page."""
    from html.parser import HTMLParser
    class Rows(HTMLParser):
        def __init__(self): super().__init__();self.inrow=False;self.incell=False;self.cell='';self.cells=[];self.rows=[]
        def handle_starttag(self,tag,attrs):
            if tag=='tr':self.inrow=True;self.cells=[]
            if self.inrow and tag in ('td','th'):self.incell=True;self.cell=''
        def handle_data(self,data):
            if self.incell:self.cell+=data
        def handle_endtag(self,tag):
            if tag in ('td','th') and self.incell:self.cells.append(self.cell.strip());self.incell=False
            if tag=='tr' and self.inrow:self.rows.append(self.cells);self.inrow=False
    url='https://www.jpx.co.jp/english/markets/indices/realvalues/index.html'
    raw=fetch_text(url,12)
    parser=Rows();parser.feed(raw)
    results={}
    for row in parser.rows:
        if len(row)<3:continue
        name=re.sub(r'\s+',' ',row[0]).strip().lower()
        key='topix' if name=='topix' else ('growth' if ('growth' in name and '250' in name) else None)
        if not key:continue
        try:
            price=float(re.search(r'[0-9][0-9,]*(?:\.[0-9]+)?',row[1]).group().replace(',',''))
            # JPX change cell can contain both absolute and percentage values.
            change=float(re.search(r'[+-]?\d[\d,]*(?:\.\d+)?',row[2]).group().replace(',',''))
            prev=price-change
            if not (100<price<10000 and prev>0):continue
            results[key]={'price':price,'prev':prev,'change':change,'pct':change/prev*100,'source':'JPX official'}
        except (ValueError,AttributeError,IndexError):continue
    return results

def official_jpx_home_quotes():
    """Read only labeled index quotes on JPX Japanese home page, never ETF proxies."""
    from html.parser import HTMLParser
    class Text(HTMLParser):
        def __init__(self): super().__init__();self.parts=[]
        def handle_data(self,data):
            if data.strip():self.parts.append(data.strip())
    raw=fetch_text('https://www.jpx.co.jp/',12)
    parser=Text();parser.feed(raw)
    txt=' '.join(parser.parts)
    result={}
    for key,labels in [('growth',['東証グロース市場250指数','東証グロース市場250']),('topix',['TOPIX'])]:
        for label in labels:
            # Explicit label followed by its current quote and signed day change.
            pat=re.escape(label)+r'\\s+([0-9][0-9,]*\\.[0-9]+)\\s+([+\\-−]\\s*[0-9][0-9,]*\\.[0-9]+)'
            m=re.search(pat,txt,re.I)
            if not m:continue
            price=float(m.group(1).replace(',',''))
            change=float(m.group(2).replace(',','').replace(' ','').replace('−','-'))
            prev=price-change
            if prev>0 and (100<price<3000 if key=='growth' else 100<price<10000):
                result[key]={'price':price,'prev':prev,'change':change,
                             'pct':change/prev*100,'source':'JPX公式トップページ'}
                break
    return result

def topix_yahoo_jp_quote():
    raw=fetch_text('https://finance.yahoo.co.jp/quote/998405.T',12)
    txt=strip_tags(raw)
    # Restrict extraction to the heading, before the page's other market data.
    p=txt.find('TOPIX')
    area=txt[p:p+800] if p>=0 else ''
    m=re.search(r'998405(?:\.T)?.{0,150}?([0-9],[0-9]{3}\.[0-9]{1,2})\s*前日比\s*([+-]\s*[0-9,]+(?:\.[0-9]+)?)\s*\(',area)
    if not m:raise ValueError('TOPIX Yahoo Japan quote layout unavailable')
    price=float(m.group(1).replace(',',''));change=float(m.group(2).replace(',','').replace(' ',''))
    prev=price-change
    return {'price':price,'prev':prev,'change':change,'pct':100*change/prev,'source':'Yahoo Japan TOPIX 998405.T'}

def growth250_traders():
    """Read the labeled cash index, not the futures quote."""
    raw=fetch_text('https://www.traders.co.jp/market_jp/index',12)
    txt=strip_tags(raw)
    label='東証グロース市場250指数'
    pos=txt.find(label)
    if pos<0:raise ValueError('指数名がページに見つかりません')
    area=txt[pos+len(label):pos+len(label)+240]
    # Expected order on the published index table: current, change, percent.
    m=re.search(r'([0-9]{3,4}\.[0-9]{1,2})\s+([+\-−]\s*[0-9]+(?:\.[0-9]+)?)\s+([+\-−]\s*[0-9]+(?:\.[0-9]+)?)\s*%',area)
    if not m:raise ValueError('指数名はあるが数値形式が一致しません: '+area[:110])
    price=float(m.group(1));change=float(m.group(2).replace('−','-').replace(' ',''))
    pct=float(m.group(3).replace('−','-').replace(' ',''));prev=price-change
    if not (100<price<3000 and prev>0 and abs(100*change/prev-pct)<0.25):raise ValueError('値と前日比の整合性エラー')
    return {'price':price,'prev':prev,'change':change,'pct':100*change/prev,'source':'Traders Web 東証グロース市場250指数'}

def growth250_daily_history():
    """Cash-index historical closes, never an ETF/futures proxy."""
    url='https://nikkeiyosoku.com/mothers/data/stock_us/stock_us/theme_ranking/'
    raw=fetch_text(url,12)
    # Parse row cells to avoid accidentally pairing a date with unrelated numbers.
    rows=re.findall(r'<tr\b[^>]*>(.*?)</tr\s*>',raw,re.I|re.S)
    records={}
    for row in rows:
        cells=re.findall(r'<t[dh]\b[^>]*>(.*?)</t[dh]\s*>',row,re.I|re.S)
        values=[re.sub(r'\s+',' ',strip_tags(cell)).strip() for cell in cells]
        for i,cell in enumerate(values[:-1]):
            match=re.fullmatch(r'(20\d{2})[/-](\d{1,2})[/-](\d{1,2})',cell)
            if not match:continue
            price=re.fullmatch(r'([0-9]{2,4}(?:,[0-9]{3})*\.[0-9]{1,2})',values[i+1].replace(' ',''))
            if not price:continue
            day=f'{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}'
            val=float(price.group(1).replace(',',''))
            if 100<val<3000 and day<=datetime.now().strftime('%Y-%m-%d'):
                records[day]=val
    points=sorted(records.items())[-30:]
    if len(points)<2:raise ValueError('投資の森の日次表を解析できません（行数 '+str(len(rows))+'）')
    return {'points':[[i,price] for i,(_,price) in enumerate(points)],
            'prev':points[-2][1],'dates':[d for d,_ in points],
            'source':'投資の森 東証グロース市場250指数 日足','kind':'daily'}

def growth250_diagnostics():
    providers=[('Traders Web 現物指数',growth250_traders),('JPX公式トップ',lambda: official_jpx_home_quotes().get('growth') or (_ for _ in ()).throw(ValueError('ページ内で指数を特定できません'))),('JPX英語指数',lambda: official_jpx_indices().get('growth') or (_ for _ in ()).throw(ValueError('指数を特定できません'))),('株探 PC',growth250_kabutan_pc),('株探 モバイル',growth250_quote),('Yahoo 指数',lambda: yahoo_quote('^TSEGM250'))]
    report=[];found=None
    for name,fn in providers:
        try:
            data=fn()
            if not data or not (100<float(data['price'])<3000):raise ValueError('値が空、または範囲外')
            report.append({'name':name,'ok':True,'price':data['price'],'source':data.get('source',name)})
            if found is None:found={'ok':True,**data,'source':data.get('source',name)}
        except Exception as e:report.append({'name':name,'ok':False,'error':str(e)[:240]})
    return {'ok':bool(found),'quote':found,'providers':report,'checked_at':datetime.now().isoformat(timespec='seconds')}

def market_quotes():
    items={}
    for key,symbols in [('nikkei',['^N225']),('topix',['998405.T','^TOPX']),('sox',['^SOX']),('fang',['^NYFANG'])]:
        errors=[]
        for sym in symbols:
            try:
                items[key]={'ok':True,**yahoo_quote(sym),'source':'Yahoo chart '+sym}
                break
            except Exception as e:errors.append(f'{sym}: {e}')
        if key not in items:items[key]={'ok':False,'error':'; '.join(errors)}
    if not items['topix']['ok']:
        try:items['topix']={'ok':True,**topix_yahoo_jp_quote()}
        except Exception as e:items['topix']['error']+='; Yahoo JP: '+str(e)
    try:
        for sym in ('^TSEGM250',):
            try:
                items['growth']={'ok':True,**yahoo_quote(sym),'source':'Yahoo chart '+sym}
                break
            except Exception:pass
        if 'growth' not in items:
            try:items['growth']={'ok':True,**growth250_kabutan_pc(),'source':'Kabutan PC growth 250'}
            except Exception:items['growth']={'ok':True,**growth250_quote(),'source':'Kabutan mobile growth 250'}
    except Exception as e:items['growth']={'ok':False,'error':str(e)}
    if not items['growth']['ok']:
        try:items['growth']={'ok':True,**growth250_traders()}
        except Exception as e:items['growth']['error']+='; Traders Web: '+str(e)
    if not items['topix']['ok'] or not items['growth']['ok']:
        try:
            home=official_jpx_home_quotes()
            for key in ('topix','growth'):
                if not items[key]['ok'] and key in home:items[key]={'ok':True,**home[key]}
        except Exception as e:
            for key in ('topix','growth'):
                if not items[key]['ok']:items[key]['error']+='; JPX home: '+str(e)
    if not items['topix']['ok'] or not items['growth']['ok']:
        try:
            official=official_jpx_indices()
            for key in ('topix','growth'):
                if not items[key]['ok'] and key in official:
                    items[key]={'ok':True,**official[key]}
        except Exception as e:
            for key in ('topix','growth'):
                if not items[key]['ok']:items[key]['error']+='; JPX: '+str(e)
    return items

class H(SimpleHTTPRequestHandler):
    def log_message(self,*a):pass
    def js(self,x,status=200):
        b=json.dumps(x,ensure_ascii=False).encode();self.send_response(status);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Cache-Control","no-store");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def do_POST(self):
        path=urllib.parse.urlparse(self.path).path
        if path=="/api/update":
            if not STATE["running"]:threading.Thread(target=update,daemon=True).start()
            return self.js(STATE)
        if path=="/api/watch/remove":
            try:
                n=int(self.headers.get("Content-Length","0") or 0)
                body=json.loads(self.rfile.read(n).decode("utf-8") or "{}")
                code=str(body.get("code","")).strip().upper()
                if not re.fullmatch(r"(?:\d{4}|\d{3}[A-Z])",code): raise ValueError("bad code")
                d=load()
                if code in d.get("stocks",{}):
                    del d["stocks"][code]
                    save(d)
                return self.js({"ok":True,"code":code})
            except Exception as e:
                return self.js({"ok":False,"error":str(e)},400)
        if path=="/api/watch/add":
            try:
                n=int(self.headers.get("Content-Length","0") or 0)
                body=json.loads(self.rfile.read(n).decode("utf-8") or "{}")
                code=str(body.get("code","")).strip().upper()
                name=str(body.get("name","")).strip() or code
                if not re.fullmatch(r"(?:\d{4}|\d{3}[A-Z])",code):
                    raise ValueError("銘柄コードは4桁の数字、または285Aのような英数字です")
                # Confirm the Tokyo quote exists.
                yahoo_quote(code+".T")
                date,margin=latest_margin_for_code(code)
                d=load()
                stocks=d.setdefault("stocks",{})
                if code not in stocks and len(stocks)>=100:
                    raise ValueError("登録銘柄は最大100件です")
                st=stocks.setdefault(code,{"name":name,"history":[]})
                st["name"]=name
                st.setdefault("history",[])
                if margin:
                    st["history"]=[x for x in st["history"] if x.get("date")!=date]
                    st["history"].append({"date":date,**margin})
                    st["history"].sort(key=lambda x:x.get("date",""))
                    st["history"]=st["history"][-400:]
                save(d)
                return self.js({"ok":True,"code":code,"name":name,"margin":bool(margin),"date":date})
            except Exception as e:
                return self.js({"ok":False,"error":str(e)},400)
        self.js({"error":"not found"},404)
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/backup-download":
            try:
                raw=Path(DATA).read_bytes()
                json.loads(raw.decode('utf-8'))
                self.send_response(200)
                self.send_header('Content-Type','application/json; charset=utf-8')
                self.send_header('Content-Disposition','attachment; filename="seido_data_backup.json"')
                self.send_header('Cache-Control','no-store')
                self.send_header('Content-Length',str(len(raw)))
                self.end_headers();self.wfile.write(raw)
            except Exception as e:self.js({'ok':False,'error':str(e)},500)
            return

        if u.path == "/api/growth-history":
            try:
                result=growth250_daily_history()
                return self.js({'ok':True,**result})
            except Exception as e:
                return self.js({'ok':False,'error':str(e),'source':'投資の森 日足','checked_at':datetime.now().isoformat(timespec='seconds')})

        if u.path == "/api/index-history":
            try:
                q=urllib.parse.parse_qs(u.query); symbol=q.get('symbol',[''])[0]
                if symbol not in ('998405.T','^TOPX'):raise ValueError('unsupported index')
                try:points=yahoo_daily_history(symbol,'1mo')
                except Exception:
                    if symbol!='998405.T':raise
                    points=topix_jp_daily_history()
                if len(points)<2 and symbol=='998405.T':points=topix_jp_daily_history()
                if len(points)<2:raise ValueError('insufficient history')
                return self.js({'ok':True,'points':[[i,p['close']] for i,p in enumerate(points)],'prev':points[-2]['close'],'kind':'daily'})
            except Exception as e:return self.js({'ok':False,'error':str(e)})

        if u.path == "/api/candles":
            try:
                qs=urllib.parse.parse_qs(u.query)
                code=qs.get("code",[""])[0].strip().upper()
                period=qs.get("range",["3mo"])[0]
                if not re.fullmatch(r"(?:\d{4}|\d{3}[A-Z])",code):raise ValueError("unsupported stock code")
                if period not in ("1mo","3mo","6mo","1y"):raise ValueError("unsupported range")
                symbol=urllib.parse.quote(code+".T",safe="")
                url=f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range={period}"
                req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
                with urllib.request.urlopen(req,timeout=12) as response:
                    payload=json.loads(response.read().decode("utf-8"))
                result=payload["chart"]["result"][0]
                timestamps=result.get("timestamp") or []
                quote=result["indicators"]["quote"][0]
                rows=[]
                for i,t in enumerate(timestamps):
                    try:
                        o,h,l,c=(float(quote[k][i]) for k in ("open","high","low","close"))
                        if not all(map(math.isfinite,(o,h,l,c))) or min(o,h,l,c)<=0:continue
                        rows.append({"date":datetime.fromtimestamp(int(t)).strftime("%Y-%m-%d"),
                                     "open":o,"high":h,"low":l,"close":c,
                                     "volume":(int(quote["volume"][i]) if quote.get("volume") and i<len(quote["volume"]) and quote["volume"][i] is not None else None)})
                    except (ValueError,TypeError,IndexError,KeyError):continue
                if not rows:raise ValueError("OHLC data unavailable")
                return self.js({"ok":True,"code":code,"source":"Yahoo Finance daily OHLC","candles":rows})
            except Exception as e:return self.js({"ok":False,"error":str(e)})
        if u.path == "/api/weekly":
            try:
                qs=urllib.parse.parse_qs(u.query)
                code=(qs.get("code",[""])[0]).strip().upper()
                if not re.fullmatch(r"(?:\d{4}|\d{3}[A-Z])",code): raise ValueError("bad code")
                return self.js({"ok":True,"code":code,"history":yahoo_daily_history(code+".T")})
            except Exception as e:
                return self.js({"ok":False,"error":str(e)})

        if u.path == "/api/intraday":
            try:
                qs=urllib.parse.parse_qs(u.query)
                symbol=(qs.get("symbol",[""])[0]).strip()
                code=(qs.get("code",[""])[0]).strip().upper()
                if code:
                    if not re.fullmatch(r"(?:\d{4}|\d{3}[A-Z])",code): raise ValueError("bad code")
                    symbol=code+".T"
                if not symbol: raise ValueError("symbol required")
                return self.js({"ok":True,"symbol":symbol,**yahoo_intraday(symbol)})
            except Exception as e:
                return self.js({"ok":False,"error":str(e)})

        if u.path == "/api/diagnostics":
            qs=urllib.parse.parse_qs(u.query); code=qs.get('code',['7203'])[0]
            if not re.fullmatch(r'(?:\d{4}|\d{3}[A-Z])',code):code='7203'
            info=japanese_stock_info(code)
            markets=market_quotes()
            return self.js({'ok':True,'code':code,'stock_info':info,
                            'indices':{k:{'ok':v.get('ok'),'source':v.get('source'),'error':v.get('error'),'price':v.get('price')} for k,v in markets.items()}})
        if u.path == "/api/stock-info":
            try:
                q=urllib.parse.parse_qs(u.query); code=str(q.get("code",[""])[0]).strip().upper()
                if not re.fullmatch(r"(?:\d{4}|\d{3}[A-Z])",code): raise ValueError("bad code")
                return self.js({"ok":True,"code":code,**japanese_stock_info(code)})
            except Exception as e:return self.js({"ok":False,"error":str(e)},400)
        if u.path == "/api/preview-history":
            try:
                q=urllib.parse.parse_qs(u.query); code=str(q.get("code",[""])[0]).strip().upper()
                if not re.fullmatch(r"(?:\d{4}|\d{3}[A-Z])",code): raise ValueError("bad code")
                return self.js({"ok":True,"code":code,"history":recent_margin_history(code,65)})
            except Exception as e:return self.js({"ok":False,"error":str(e)},400)
        if u.path == "/api/preview-margin":
            try:
                q=urllib.parse.parse_qs(u.query)
                code=str(q.get("code",[""])[0]).strip().upper()
                if not re.fullmatch(r"(?:\d{4}|\d{3}[A-Z])",code): raise ValueError("bad code")
                date,margin=latest_margin_for_code(code)
                if not margin: raise ValueError("JPX制度信用データを取得できませんでした")
                return self.js({"ok":True,"code":code,"date":date,**margin})
            except Exception as e:
                return self.js({"ok":False,"error":str(e)},400)
        if u.path == "/api/search":
            try:
                qs=urllib.parse.parse_qs(u.query)
                term=(qs.get("q",[""])[0]).strip().upper() if re.fullmatch(r"[0-9a-zA-Z]{4}",(qs.get("q",[""])[0]).strip()) else (qs.get("q",[""])[0]).strip()
                if not term: raise ValueError("empty query")
                if re.fullmatch(r"\d{3}[A-Z]",term):
                    yahoo_quote(term+".T")
                    known={"285A":"キオクシアホールディングス"}
                    return self.js({"ok":True,"code":term,"name":known.get(term,term)})
                # For a 4-digit JP code, resolve the company name too.
                if re.fullmatch(r"(?:\d{4}|\d{3}[A-Z])",term):
                    url="https://query1.finance.yahoo.com/v1/finance/search?q="+urllib.parse.quote(term)+"&quotesCount=10&newsCount=0"
                    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
                    jj=json.loads(urllib.request.urlopen(req,timeout=10).read().decode("utf-8"))
                    for q in jj.get("quotes",[]):
                        sym=q.get("symbol","")
                        if sym==term+".T":
                            info=japanese_stock_info(term)
                            return self.js({"ok":True,"code":term,"name":info.get("name") or q.get("shortname") or q.get("longname") or term})
                    return self.js({"ok":True,"code":term,"name":term})
                url="https://query1.finance.yahoo.com/v1/finance/search?q="+urllib.parse.quote(term)+"&quotesCount=10&newsCount=0"
                req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
                jj=json.loads(urllib.request.urlopen(req,timeout=10).read().decode("utf-8"))
                for q in jj.get("quotes",[]):
                    sym=q.get("symbol","")
                    if sym.endswith(".T") and re.fullmatch(r"(?:\d{4}|\d{3}[A-Z])\.T",sym):
                        info=japanese_stock_info(sym[:-2])
                        return self.js({"ok":True,"code":sym[:-2],"name":info.get("name") or q.get("shortname") or q.get("longname") or sym[:-2]})
                return self.js({"ok":False,"error":"該当する日本株が見つかりません"})
            except Exception as e:
                return self.js({"ok":False,"error":str(e)})

        if u.path == "/api/diagnostics":
            code=urllib.parse.parse_qs(u.query).get('code',['4062'])[0]
            if not re.fullmatch(r'(?:\d{4}|\d{3}[A-Z])',code):return self.js({'ok':False,'error':'4-digit code required'},400)
            return self.js({'ok':True,'code':code,'metrics':japanese_stock_info(code),'markets':market_quotes()})
        if u.path == "/api/growth-diagnostics":
            return self.js(growth250_diagnostics())
        if u.path == "/api/markets":
            return self.js({"ok":True,"items":market_quotes(),"time":datetime.now().isoformat(timespec="seconds")})

        if u.path == "/api/price":
            try:
                from urllib.parse import parse_qs
                qs=parse_qs(u.query)
                code=(qs.get("code",["9984"])[0]).strip()
                if not re.fullmatch(r"(?:\d{4}|\d{3}[A-Z])",code): raise ValueError("unsupported code")
                q=yahoo_quote(code+".T")
                return self.js({"ok":True,"code":code,**q})
            except Exception as e:
                return self.js({"ok":False,"error":str(e)})
        p=urllib.parse.urlparse(self.path).path
        if p=="/api/status":
            return self.js(STATE)
        if p=="/api/data":
            return self.js(load())
        return super().do_GET()
if __name__=="__main__":
    initialize_data()
    os.chdir(ROOT); print("V14.48 MOBILE PORTRAIT  http://127.0.0.1:8847/dashboard.html (LAN access enabled)",flush=True)
    threading.Timer(1,lambda:webbrowser.open("http://127.0.0.1:8847/dashboard.html?v=1448")).start()
    ThreadingHTTPServer(("0.0.0.0",PORT),H).serve_forever()
