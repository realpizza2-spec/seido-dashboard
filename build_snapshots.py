#!/usr/bin/env python3
"""Generate read-only API snapshots for GitHub Pages from the existing server logic."""
import os,sys,json,traceback,urllib.parse
from pathlib import Path
os.chdir(Path(__file__).resolve().parent)
sys.path.insert(0,str(Path.cwd()))
import server
site=Path("site/api");site.mkdir(parents=True,exist_ok=True)
server.initialize_data()
def dump(key,data):
    (site/(key+".json")).write_text(json.dumps(data,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
def call(path):
    """Use the actual V14.48 HTTP handler without running a web server."""
    class Fake(server.H):
        def __init__(self):self.path=path;self.result=None
        def js(self,x,status=200):self.result=x
    h=Fake()
    try:
        h.do_GET()
        return h.result if h.result is not None else {"ok":False,"error":"データなし"}
    except Exception as e:
        return {"ok":False,"error":str(e)}
# JPX update only on scheduled run; preserve prior histories if JPX temporarily unavailable.
if os.getenv("SKIP_JPX")!="1":
    server.update()
    print("JPX:",server.STATE)
dump("data",server.load())
dump("status",server.STATE)
for endpoint in ("markets","growth-history","growth-diagnostics","diagnostics"):
    dump(endpoint,call("/api/"+endpoint))
stocks=list(server.load().get("stocks",{}))
print("stocks:",len(stocks),flush=True)
for i,code in enumerate(stocks,1):
    print(f"{i}/{len(stocks)} {code}",flush=True)
    for endpoint in ("price","stock-info","weekly","preview-history","preview-margin","intraday","candles"):
        params={"code":code}
        if endpoint=="candles":
            for rng in ("1m","3m","6m","1y"):
                p=urllib.parse.urlencode({"code":code,"range":rng})
                dump(f"candles_{code}_{rng}",call("/api/candles?"+p))
        else:
            dump(f"{endpoint}_{code}",call("/api/"+endpoint+"?"+urllib.parse.urlencode(params)))
for symbol in ("^N225","^TOPX","^SOX","^FANG","^N225","^TOPX","^N225","^TOPX"):
    for endpoint in ("intraday","index-history"):
        dump(f"{endpoint}_{urllib.parse.quote(symbol,safe='')}",call("/api/"+endpoint+"?"+urllib.parse.urlencode({"symbol":symbol})))
print("snapshot complete",flush=True)
