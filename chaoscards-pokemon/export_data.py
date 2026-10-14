#!/usr/bin/env python3
"""Collect Chaos Cards Pokémon products and actual product photos, with strict gates."""
import concurrent.futures
from datetime import datetime, timezone
import io, json, os, re, sys, time, random
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import requests
from PIL import Image, ImageOps, UnidentifiedImageError
from playwright.sync_api import sync_playwright

BASE="https://www.chaoscards.co.uk/brand/pokemon"
TOTAL=3020
PAGE_SIZE=24
PAGES=(TOTAL+PAGE_SIZE-1)//PAGE_SIZE
ROOT=Path("dataset")
IMAGES=ROOT/"images"
ROOT.mkdir(exist_ok=True)
IMAGES.mkdir(exist_ok=True)
JS = r"""() => {
 const normalize=s=>String(s||'').replace(/\s+/g,' ').trim();
 const href=a=>{try{let u=new URL(a.href,location.href);return u.origin+u.pathname}catch(e){return ''}};
 const getImg=img=>{
    if(!img) return '';
    for(let s of [img.getAttribute('data-src'),img.getAttribute('data-original'),
       img.getAttribute('data-lazy-src'),img.getAttribute('data-image'),
       img.currentSrc,img.getAttribute('srcset'),img.getAttribute('src')]){
       if(!s) continue;
       s=s.trim().split(',')[0].trim().replace(/\s+\d+[wx]$/,'');
       if(/^(data:|blob:)/.test(s)||/placeholder|loading\.gif|blank\.gif/i.test(s))continue;
       try{return new URL(s,location.href).href}catch(e){}
    }
    return '';
 };
 const anchors=[...document.querySelectorAll('a[href*="/prod/"]')].filter(a=>new URL(a.href,location.href).pathname.startsWith('/prod/'));
 const grouped=new Map();
 for(const a of anchors){let h=href(a);if(!grouped.has(h))grouped.set(h,[]);grouped.get(h).push(a);}
 let out=[];
 for(const [url,links] of grouped){
    let root=null;
    for(const a of links){
       let node=a;
       for(let d=0;d<9&&node;d++,node=node.parentElement){
          let txt=normalize(node.innerText||node.textContent);
          if(!/£\s*[\d,.]+|Price\s*TBC/i.test(txt))continue;
          let uniq=new Set([...node.querySelectorAll('a[href*="/prod/"]')].map(href));
          if(uniq.size>1) break;
          root=node;
          if(node.querySelector('img'))break;
       }
       if(root&&root.querySelector('img'))break;
    }
    if(!root)continue;
    const txt=normalize(root.innerText||root.textContent);
    const names=links.map(a=>normalize(a.title||a.innerText||a.textContent))
      .filter(x=>x.length>5&&!/^(notify|wishlist|quick look|add to)/i.test(x));
    let imCandidates=[...root.querySelectorAll('img')].map(im=>{
       const src=getImg(im);
       return {src, alt:normalize(im.alt),
          score:(im.naturalWidth||im.width||1)*(im.naturalHeight||im.height||1)+(im.closest('a[href*="/prod/"]')?900000:0)};
    }).filter(im=>im.src&&!/feefo|logo|icon|badge|rating|star/i.test(im.src))
      .sort((a,b)=>b.score-a.score);
    let photo=imCandidates[0]||{src:'',alt:''};
    if(photo.alt)names.push(photo.alt);
    let title=names.sort((a,b)=>b.length-a.length)[0]||'';
    title=title.replace(/£\s*[\d,.]+.*$/,'').replace(/\b(Add to basket|Notify me|Quick look)\b.*$/i,'').trim();
    let m=txt.match(/£\s*([\d,]+(?:\.\d{1,2})?)/);
    let price=m?Number(m[1].replaceAll(',','')):null;
    let priceText=price===null&&/Price\s*TBC/i.test(txt)?'Price TBC':'';
    out.push({url,name:title,price,price_text:priceText,image:photo.src});
 }
 const num=(document.body.innerText||'').match(/\b\d[\d,]*\s+to\s+\d[\d,]*\s+of\s+([\d,]+)\s+items\b/i);
 return {products:out,total:num?parseInt(num[1].replaceAll(',','')):null};
}"""

def collect():
    all_rows=[]
    with sync_playwright() as p:
      browser=p.chromium.launch(headless=True,args=['--disable-dev-shm-usage','--no-sandbox'])
      context=browser.new_context(viewport={"width":1300,"height":950}, user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),locale='en-GB')
      page=context.new_page()
      for pg in range(1,PAGES+1):
        url=BASE if pg==1 else BASE+f"/sort/release-date-newest-first/page/{pg}"
        last=None
        for attempt in range(4):
          try:
            page.goto(url,wait_until='domcontentloaded',timeout=60000)
            page.locator('a[href*="/prod/"]').first.wait_for(timeout=25000)
            page.wait_for_timeout(700)
            ans=page.evaluate(JS)
            if pg==1 and ans['total']!=TOTAL:
                raise RuntimeError(f"Website reported {ans['total']} items, expected {TOTAL}")
            rows=ans['products']
            expected=PAGE_SIZE if pg<PAGES else TOTAL-PAGE_SIZE*(PAGES-1)
            if len(rows)!=expected:
                raise RuntimeError(f"Page {pg} returned {len(rows)} rather than {expected} distinct products")
            if any(not x['name'] or not (x['price'] is not None or x['price_text']) for x in rows):
                raise RuntimeError(f"Missing product names or prices on page {pg}")
            all_rows.extend(rows)
            last=None
            break
          except Exception as exc:
            last=exc
            print(f"Page={pg} attempt={attempt+1} ERROR {type(exc).__name__}: {exc}",flush=True)
            page.wait_for_timeout(2500+attempt*2500)
        if last:raise RuntimeError(f"UNVERIFIED: page {pg}: {last}")
        print(f"COLLECTED page={pg:03d}/{PAGES} rows={len(all_rows)}",flush=True)
        if pg<PAGES:time.sleep(.28+random.random()*.37)
      context.close()
      browser.close()
    ids=[v['url'] for v in all_rows]
    if len(all_rows)!=TOTAL or len(set(ids))!=TOTAL:
        raise RuntimeError(f"Rows {len(all_rows)}, unique {len(set(ids))}; expected {TOTAL}")
    return all_rows

SESSION=requests.Session()
SESSION.headers.update({'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36','Referer':'https://www.chaoscards.co.uk/'})
def fetch_image(arg):
    idx,item=arg
    image_url=item['image']
    h=(urlsplit(image_url).hostname or '').lower()
    if not h.endswith('chaoscards.co.uk'):
        raise RuntimeError(f"Image {idx} host invalid/missing: {image_url}")
    dest=IMAGES/f'{idx:04d}.jpg'
    for attempt in range(4):
      try:
        r=SESSION.get(image_url,timeout=(15,40))
        r.raise_for_status()
        if not r.headers.get('Content-Type','').startswith('image/'):
            raise RuntimeError(f"Not an image: HTTP {r.status_code}: {r.headers.get('Content-Type')}")
        if len(r.content)<300:raise RuntimeError("Image too small")
        with Image.open(io.BytesIO(r.content)) as im:
            im=ImageOps.exif_transpose(im).convert('RGB')
            im.thumbnail((180,180),Image.Resampling.LANCZOS)
            im.save(dest,'JPEG',quality=77,optimize=True)
        if dest.stat().st_size<300:raise RuntimeError("Thumbnail invalid")
        return idx,str(dest)
      except Exception as exc:
        if attempt==3:return idx, "ERROR "+str(exc)
        time.sleep(1.5*(attempt+1))
    return idx,"ERROR retry exhausted"

def main():
    rows=collect()
    print("COLLECTION VERIFIED 3020 distinct product names/prices",flush=True)
    for i,x in enumerate(rows,1):
        x['picture']=f'images/{i:04d}.jpg'
    with concurrent.futures.ThreadPoolExecutor(max_workers=9) as pool:
      futs=[pool.submit(fetch_image,(i,x)) for i,x in enumerate(rows,1)]
      failures=[]
      for n,f in enumerate(concurrent.futures.as_completed(futs),1):
        i,v=f.result()
        if v.startswith("ERROR"):failures.append((i,v))
        if n%100==0:print(f"IMAGES completed={n}/{TOTAL} failures={len(failures)}",flush=True)
    if failures:
      (ROOT/'image_failures.json').write_text(json.dumps(failures,indent=2))
      raise RuntimeError(f"UNVERIFIED: {len(failures)} images failed: {failures[:5]}")
    data={'source':BASE,'retrieved_utc':datetime.now(timezone.utc).isoformat(),'count':len(rows),
          'products':[{k:x[k] for k in ('name','price','price_text','picture')} for x in rows]}
    (ROOT/'manifest.json').write_text(json.dumps(data,ensure_ascii=False,indent=1),encoding='utf-8')
    print(f"COMPLETE rows={len(rows)} images={len(list(IMAGES.glob('*.jpg')))}",flush=True)
if __name__=="__main__":
    main()
