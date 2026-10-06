# -*- coding: utf-8 -*-
"""
Higgsfield 자동 뽑기
  UI그림_번호표.csv + UI그림_프롬프트_전체.txt 를 읽어서
  번호마다 : 프롬프트 넣기 → 첨부 그림 올리기 → 생성 → 결과 받기 → 저장폴더\파일이름 저장 → 쉬기 → 다음 번호

  python hf_auto.py setup          처음 한 번 : 입력칸 · 첨부 단추 · 생성 단추 위치 알려 주기
  python hf_auto.py run --test     시험 1개
  python hf_auto.py run            밤새 돌리기 (--from 10 --to 50 --stage 1단계 --count 30 --gap 180)
"""
import argparse, csv, ctypes, datetime, io, json, os, random, re, sys, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SETTINGS = HERE / 'hf_settings.json'
LOG = HERE / 'hf_log.csv'
STOP = HERE / 'STOP.txt'                                     # 이 파일을 만들면 지금 번호를 끝내고 멈춤

DEFAULT = {
    "작업폴더": r"C:\Users\User\클로드\side\art\UI\UI 그림 작업",
    "번호표": "UI그림_번호표.csv",
    "프롬프트": "UI그림_프롬프트_전체.txt",
    "생성주소": "",
    "간격초": 180,              # 한 장 끝나고 다음 생성까지 쉬는 시간
    "간격흔들기초": 30,          # 간격을 ± 이만큼 무작위로 (사람처럼)
    "최대대기초": 900,           # 생성이 이보다 오래 걸리면 실패로 넘어감
    "최소가로": 1500,            # 이보다 작은 그림은 «_작은그림» 폴더로
    "올린뒤대기초": 8,           # 첨부 그림 한 장 올린 뒤 기다리는 시간
    "매번새로고침": True,         # 번호마다 생성 화면을 새로 열어 지난 첨부를 비움
    "연속실패멈춤": 3,
    "크롬포트": 9222,
    "선택자": {}
}


def say(*a):
    print(datetime.datetime.now().strftime('%H:%M:%S'), *a, flush=True)


def load_settings():
    s = dict(DEFAULT)
    if SETTINGS.exists():
        s.update(json.loads(SETTINGS.read_text(encoding='utf-8')))
    return s


def save_settings(s):
    SETTINGS.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding='utf-8')


def log(n, result, memo=''):
    new = not LOG.exists()
    with open(LOG, 'a', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        if new:
            w.writerow(['시각', '번호', '결과', '메모'])
        w.writerow([datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), n, result, memo])


def keep_awake(on=True):                                     # 자는 동안 컴퓨터가 잠들지 않게 (윈도)
    if os.name == 'nt':
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | (0x00000001 if on else 0))


# ── 번호표 · 프롬프트 읽기 (UI 그림 도우미와 같은 방식) ──
def read_rows(s):
    p = Path(s['작업폴더']) / s['번호표']
    with open(p, encoding='utf-8-sig', newline='') as f:
        rows = [{k.strip(): (v or '').strip() for k, v in r.items() if k} for r in csv.DictReader(f)]
    return [r for r in rows if r.get('번호', '').isdigit() and int(r['번호'])]


def read_prompts(s):
    text = (Path(s['작업폴더']) / s['프롬프트']).read_text(encoding='utf-8-sig')
    P, n, on, buf = {}, None, False, []

    def end():
        nonlocal n, on, buf
        if n is not None:
            P[n] = '\n'.join(buf).strip()
        n, on, buf = None, False, []
    for line in text.splitlines():
        m = re.match(r'^\[(\d+)번\]', line)
        if re.match(r'^={5,}', line):
            end(); continue
        if m:
            end(); n = int(m.group(1)); continue
        if n is not None and not on and re.match(r'^-{5,}', line):
            on = True; continue
        if on:
            buf.append(line)
    end()
    return P


def base(p):
    return re.split(r'[\\/]', p)[-1]


def target_of(r):
    return Path(r['저장폴더']) / base(r['파일이름'])


# ── 크롬 연결 ──
def connect(pw, s):
    try:
        br = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{s['크롬포트']}")
    except Exception:
        sys.exit('크롬에 연결 못 했어요 · 먼저 «2_크롬열기.bat» 로 크롬을 여세요 (다른 크롬 창은 상관없음)')
    ctx = br.contexts[0]
    page = next((p for p in ctx.pages if 'higgsfield' in p.url), None) or ctx.new_page()
    page.bring_to_front()
    return br, ctx, page


# ── 위치 알려 주기 (setup) ──
PICK_JS = r"""
() => {
  if (window.__hfPickOn) return; window.__hfPickOn = true; window.__hfPick = null; window.__hfWant = null;
  const box = document.createElement('div'), ban = document.createElement('div');
  box.style.cssText = 'position:fixed;z-index:2147483646;pointer-events:none;border:3px solid #ffd27a;border-radius:6px;background:#ffd27a22;display:none';
  ban.id = '__hfBanner';
  ban.style.cssText = 'position:fixed;z-index:2147483647;top:12px;left:50%;transform:translateX(-50%);background:#211c2b;color:#ffd27a;border:2px solid #ffd27a;border-radius:10px;padding:12px 20px;font:bold 18px "Malgun Gothic",sans-serif;pointer-events:none';
  document.documentElement.append(box, ban);
  window.__hfSetBanner = t => { ban.textContent = t; ban.style.display = t ? '' : 'none'; };
  const climb = (el, kind) => kind === 'prompt'
      ? (el.closest('textarea,[contenteditable="true"],[contenteditable=""],[role="textbox"],input[type="text"],input:not([type])') || el)
      : (el.closest('button,[role="button"],label,a') || el);
  const uniq = q => { try { return document.querySelectorAll(q).length === 1; } catch (e) { return false; } };
  const path = el => { const out = []; for (let e = el; e && e.nodeType === 1 && e !== document.body; e = e.parentElement) {
      if (e.id && !/\d{3,}/.test(e.id) && uniq('#' + CSS.escape(e.id))) { out.unshift('#' + CSS.escape(e.id)); break; }
      let i = 1; for (let x = e.previousElementSibling; x; x = x.previousElementSibling) if (x.tagName === e.tagName) i++;
      out.unshift(e.tagName.toLowerCase() + ':nth-of-type(' + i + ')'); }
    return (out[0] && out[0][0] === '#' ? '' : 'body > ') + out.join(' > '); };
  const sels = el => { const S = [], t = el.tagName.toLowerCase();
    if (el.id && !/\d{3,}/.test(el.id)) S.push('#' + CSS.escape(el.id));
    for (const a of ['data-testid', 'data-test', 'aria-label', 'placeholder', 'name', 'title'])
      if (el.getAttribute(a)) S.push(t + '[' + a + '="' + el.getAttribute(a).replace(/"/g, '\\"') + '"]');
    const S2 = S.filter(uniq); const tx = (el.innerText || '').trim().split('\n')[0];
    if (tx && tx.length <= 30 && t !== 'textarea') S2.push(t + ':has-text("' + tx.replace(/"/g, '\\"') + '")');
    S2.push(path(el)); return S2; };
  const fileNear = el => { for (let e = el, k = 0; e && k < 6; e = e.parentElement, k++) { const f = e.querySelector('input[type=file]'); if (f) return path(f); }
    const all = document.querySelectorAll('input[type=file]'); return all.length === 1 ? path(all[0]) : null; };
  document.addEventListener('pointermove', e => { if (!window.__hfWant) { box.style.display = 'none'; return; }
    const r = climb(document.elementFromPoint(e.clientX, e.clientY) || e.target, window.__hfWant).getBoundingClientRect();
    Object.assign(box.style, { display: '', left: r.left - 3 + 'px', top: r.top - 3 + 'px', width: r.width + 6 + 'px', height: r.height + 6 + 'px' }); }, true);
  // 꺼진 (disabled) 단추는 click 이 안 오므로 pointerdown 에서 누른 자리의 요소를 잡음
  let swallow = 0;
  const block = e => { if (window.__hfWant || Date.now() < swallow) { e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation(); } };
  for (const ev of ['mousedown', 'pointerup', 'mouseup', 'click']) document.addEventListener(ev, block, true);
  document.addEventListener('pointerdown', e => { if (!window.__hfWant) return; block(e);
    const kind = window.__hfWant, el = climb(document.elementFromPoint(e.clientX, e.clientY) || e.target, kind);
    window.__hfPick = { sels: sels(el), file: kind === 'attach' ? fileNear(el) : null, text: (el.innerText || '').trim().slice(0, 30) };
    window.__hfWant = null; swallow = Date.now() + 800; box.style.display = 'none'; }, true);
}
"""

STEPS = [
    ('프롬프트', 'prompt', '① 프롬프트 입력칸을 누르세요'),
    ('첨부', 'attach', '② 사진 첨부 단추 (+ · 업로드) 를 누르세요'),
    ('생성', 'button', '③ 생성 (Generate) 단추를 누르세요 · 실제로 생성되지는 않아요'),
]


def setup(pw, s):
    br, ctx, page = connect(pw, s)
    print('\n크롬 창에서 Higgsfield 에 로그인하고, 쓸 생성 화면 (예 : Nano Banana Pro) 을 여세요.')
    print('모델 · 해상도 · 비율 · 한 번에 1장 까지 원하는 대로 맞춘 뒤 여기서 Enter.')
    input('> ')
    page = next((p for p in ctx.pages if 'higgsfield' in p.url and not p.is_closed()), page)
    page.bring_to_front()
    s['생성주소'] = page.url
    s['선택자'] = {}
    for key, kind, text in STEPS:
        page.evaluate(PICK_JS)
        page.evaluate('([k, t]) => { window.__hfPick = null; window.__hfWant = k; window.__hfSetBanner(t); }', [kind, text])
        say(text + '  (크롬 창에서)')
        while True:
            time.sleep(0.3)
            try:
                got = page.evaluate('() => window.__hfPick')
            except Exception:
                page.evaluate(PICK_JS); continue
            if got:
                break
        s['선택자'][key] = got
        say('  → 기억함 :', got['sels'][0] + (('  · 파일칸 ' + got['file']) if got.get('file') else ''))
    page.evaluate('() => window.__hfSetBanner("위치 기억 끝 · 이 창은 그대로 두세요")')
    save_settings(s)
    print('\n끝. 생성 화면 :', s['생성주소'])
    print('이제 «4_시험1개.bat» 로 하나만 뽑아 보세요.')


# ── 돌리기 ──
def find(page, cands, need_visible=True):
    for c in cands:
        try:
            loc = page.locator(c)
            if loc.count() < 1:
                continue
            loc = loc.first
            if need_visible and not loc.is_visible():
                continue
            return loc
        except Exception:
            continue
    return None


def wait_find(page, cands, sec=30, need_visible=True):
    end = time.time() + sec
    while time.time() < end:
        loc = find(page, cands, need_visible)
        if loc:
            return loc
        time.sleep(0.5)
    return None


def put_prompt(page, s, text):
    loc = wait_find(page, s['선택자']['프롬프트']['sels'], 40)
    if not loc:
        raise RuntimeError('프롬프트 입력칸을 못 찾음')
    loc.click()
    page.keyboard.press('Control+A')
    page.keyboard.press('Backspace')
    page.keyboard.insert_text(text)
    time.sleep(0.5)
    got = loc.evaluate('e => e.value !== undefined ? e.value : e.innerText') or ''
    if text[:20].strip() not in got:
        raise RuntimeError('프롬프트가 안 들어감')


def attach(page, s, files):
    sel = s['선택자']['첨부']
    for i, f in enumerate(files):
        done = False
        btn = find(page, sel['sels'])
        if btn:
            try:
                with page.expect_file_chooser(timeout=6000) as fc:
                    btn.click()
                ch = fc.value
                if ch.is_multiple() and i == 0 and len(files) > 1:
                    ch.set_files([str(x) for x in files]); time.sleep(s['올린뒤대기초'] * len(files)); return
                ch.set_files(str(f)); done = True
            except Exception:
                page.keyboard.press('Escape')
        if not done:                                         # 단추로 안 열리면 숨은 파일칸에 직접
            inp = find(page, ([sel['file']] if sel.get('file') else []) + ['input[type=file][accept*="image"]', 'input[type=file]'], need_visible=False)
            if not inp:
                raise RuntimeError('첨부를 못 함 (파일칸 없음)')
            inp.set_input_files(str(f))
        time.sleep(s['올린뒤대기초'])


IMGS_JS = """() => [...document.images].map(i => ({ src: i.currentSrc || i.src, w: i.naturalWidth }))
  .filter(x => x.src && !x.src.startsWith('data:') && !x.src.startsWith('blob:'))"""


def click_generate(page, s):
    loc = wait_find(page, s['선택자']['생성']['sels'], 30)
    if not loc:
        raise RuntimeError('생성 단추를 못 찾음')
    end = time.time() + 120                                  # 올리는 중이면 단추가 꺼져 있음
    while time.time() < end:
        if loc.evaluate('e => !(e.disabled || e.getAttribute("aria-disabled") === "true")'):
            break
        time.sleep(1)
    loc.click()


def variants(u):
    out = [u]
    m = re.match(r'^(https?://[^/]+)/cdn-cgi/image/[^/]+/(.*)$', u)      # 크기 줄인 주소 → 원본
    if m:
        out.insert(0, m.group(2) if m.group(2).startswith('http') else m.group(1) + '/' + m.group(2))
    if '?' in u:
        out.append(u.split('?')[0])
    return list(dict.fromkeys(out))


def fetch(ctx, url):
    try:
        r = ctx.request.get(url, timeout=60000)
        if r.ok:
            return r.body()
    except Exception:
        pass
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=60) as r:
            return r.read()
    except Exception:
        return None


def wait_result(page, ctx, s, before, net):
    """새로 나타난 큰 그림이 12초 동안 그대로면 끝난 것 · 가장 큰 원본을 돌려줌"""
    from PIL import Image
    end, last, stable = time.time() + s['최대대기초'], None, 0
    while time.time() < end:
        time.sleep(4)
        new = sorted({x['src'] for x in page.evaluate(IMGS_JS) if x['src'] not in before and x['w'] >= 400})
        if new and new == last:
            stable += 4
            if stable >= 12:
                break
        else:
            stable = 0
        last = new
    else:
        raise RuntimeError('시간 안에 결과가 안 나옴')
    best = None
    for u in list(dict.fromkeys(last + [x for x in net if x not in before]))[:16]:
        for v in variants(u):
            data = fetch(ctx, v)
            if not data:
                continue
            try:
                im = Image.open(io.BytesIO(data)); im.load()
            except Exception:
                continue
            if not best or im.width > best[0].width:
                best = (im, v)
            break
    if not best:
        raise RuntimeError('결과 그림을 못 받음')
    return best


def save_png(im, r, s):
    tgt = target_of(r)
    small = im.width < s['최소가로']
    if small:
        tgt = tgt.parent / '_작은그림' / tgt.name
    tgt.parent.mkdir(parents=True, exist_ok=True)
    if tgt.exists():
        bk = tgt.parent / '_이전'; bk.mkdir(exist_ok=True)
        tgt.replace(bk / (tgt.stem + '_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.png'))
    im.save(tgt, 'PNG')
    return tgt, small


def run(pw, s, a):
    if not s.get('생성주소') or not s.get('선택자'):
        sys.exit('먼저 «3_위치정하기.bat» 를 해 주세요')
    rows, P = read_rows(s), read_prompts(s)
    todo = [r for r in rows
            if (a.start is None or int(r['번호']) >= a.start) and (a.end is None or int(r['번호']) <= a.end)
            and (not a.stage or a.stage in r.get('단계', '')) and not target_of(r).exists()]
    if a.count:
        todo = todo[:a.count]
    gap = a.gap if a.gap is not None else s['간격초']
    say(f'할 번호 {len(todo)}개 · 간격 약 {gap}초 · 멈추려면 Ctrl+C 또는 이 폴더에 STOP.txt 만들기')
    if not todo:
        return
    br, ctx, page = connect(pw, s)
    net = []
    page.on('response', lambda resp: resp.request.resource_type == 'image' and resp.ok and net.append(resp.url))
    keep_awake(True)
    fails = ok = 0
    try:
        for k, r in enumerate(todo):
            if STOP.exists():
                say('STOP.txt 가 있어 멈춤'); break
            n = int(r['번호'])
            say(f'── {n}번 ({k + 1}/{len(todo)}) · {base(r["파일이름"])}')
            try:
                prompt = P.get(n)
                if not prompt:
                    raise RuntimeError('프롬프트를 못 찾음')
                files = [Path(r[c]) for c in ('첨부1', '첨부2') if r.get(c) and r[c] != '-']
                miss = [str(f) for f in files if not f.exists()]
                if miss:
                    raise RuntimeError('첨부 그림 없음 : ' + ', '.join(miss))
                if s['매번새로고침'] or k == 0:
                    page.goto(s['생성주소'], wait_until='domcontentloaded'); time.sleep(5)
                put_prompt(page, s, prompt)
                if files:
                    attach(page, s, files)
                before = {x['src'] for x in page.evaluate(IMGS_JS)} | set(net)
                net.clear()
                click_generate(page, s)
                say('  생성 누름 · 기다리는 중…')
                im, url = wait_result(page, ctx, s, before, net)
                tgt, small = save_png(im, r, s)
                say(f'  저장 {im.width}x{im.height} → {tgt}' + ('  (작은 그림 · 확인 필요)' if small else ''))
                log(n, '작음' if small else '저장', f'{im.width}x{im.height} {url}')
                ok += 1; fails = 0
            except KeyboardInterrupt:
                raise
            except Exception as e:
                fails += 1
                say(f'  실패 : {e}')
                log(n, '실패', str(e))
                try:
                    page.screenshot(path=str(HERE / f'실패_{n}.png'))
                except Exception:
                    pass
                if fails >= s['연속실패멈춤']:
                    say(f'연속 {fails}번 실패라 멈춤 · 로그인 · 화면 · 크레딧 확인 · 실패_번호.png 를 보세요'); break
            if k < len(todo) - 1 and not a.test:
                w = max(30, gap + random.uniform(-s['간격흔들기초'], s['간격흔들기초']))
                say(f'  {int(w)}초 쉬기'); time.sleep(w)
    except KeyboardInterrupt:
        say('Ctrl+C 로 멈춤')
    finally:
        keep_awake(False)
    say(f'끝 · 저장 {ok}개 · 기록은 hf_log.csv')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['setup', 'run'])
    ap.add_argument('--test', action='store_true', help='1개만')
    ap.add_argument('--from', dest='start', type=int)
    ap.add_argument('--to', dest='end', type=int)
    ap.add_argument('--stage', help='단계 칸에 이 글자가 있는 번호만 (예 : 1단계)')
    ap.add_argument('--count', type=int, help='최대 몇 개')
    ap.add_argument('--gap', type=int, help='쉬는 초 (기본 180)')
    a = ap.parse_args()
    if a.test:
        a.count = 1
    s = load_settings()
    if not SETTINGS.exists():
        save_settings(s)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        setup(pw, s) if a.cmd == 'setup' else run(pw, s, a)


if __name__ == '__main__':
    main()
