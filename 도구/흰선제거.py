# 흰 테두리 지우기 : 초록 바탕(또는 투명 바탕) 캐릭터 그림에서 몸 둘레 흰 선(스티커 테두리)만 깎아 냄
#   - 바탕(초록)에서 시작해 붙어 있는 흰색 · 흰+초록 섞인 점을 한 겹씩 지우고, 캐릭터의 진한 선을 만나면 멈춤
#   - 선을 건너뛰지 않고, 테두리 두께의 2.5배보다 깊이는 안 들어감 → 테두리에 붙은 흰 털 · 흰 옷도 남음
#   - 안쪽 흰색(눈 흰자 · 셔츠 · 흰 옷)은 진한 선으로 둘러싸여 있으면 그대로 남음
# 쓰는 법 :
#   python 흰선제거.py 그림.png                 → 그림_흰선없음.png
#   python 흰선제거.py 폴더                     → 폴더 안 png/webp/jpg 전부, 폴더_흰선없음 에 같은 이름으로
#   python 흰선제거.py 폴더 새폴더               → 결과를 새폴더 에 (없으면 만듦, 원본은 그대로)
#   python 흰선제거.py 폴더 --덮어쓰기           → 원본 자리에 바로 저장 (먼저 백업할 것)
#   --원래선 : 바깥 가장자리 1px 회색 번짐을 진하게 바꾸지 않고 그대로 둠
# 필요 : pip install pillow numpy
import sys, os
import numpy as np
from PIL import Image

def dil(m, n=1):
    for _ in range(n):
        d = m.copy()
        d[1:] |= m[:-1]; d[:-1] |= m[1:]; d[:, 1:] |= m[:, :-1]; d[:, :-1] |= m[:, 1:]
        d[1:, 1:] |= m[:-1, :-1]; d[:-1, :-1] |= m[1:, 1:]; d[1:, :-1] |= m[:-1, 1:]; d[:-1, 1:] |= m[1:, :-1]
        m = d
    return m
def 선두께(bg, light):                                               # 바탕에서 안쪽으로 흰 점이 이어지는 길이의 중간값 = 흰 테두리 두께
    runs = []
    for M, L in [(bg, light), (bg.T, light.T), (bg[:, ::-1], light[:, ::-1]), (bg.T[:, ::-1], light.T[:, ::-1])]:
        H, W = M.shape
        for y in range(0, H, 3):
            row, lr = M[y], L[y]
            for x in np.nonzero(row[:-1] & ~row[1:])[0]:
                n = 0
                while x + 1 + n < W and lr[x + 1 + n] and n < 80: n += 1
                if n: runs.append(n)
    return float(np.median(runs)) if runs else 4.0
def 흰선제거(img, 가장자리진하게=True):
    rgba = np.array(img.convert('RGBA')).astype(float)
    im, al = rgba[..., :3], rgba[..., 3]
    투명 = al[:20, :20].mean() < 16
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    lum = r * 0.3 + g * 0.59 + b * 0.11
    mx = im.max(-1); mn = im.min(-1)
    if 투명:
        bg = al < 16
        light = ((mn > 215) & ((mx - mn) < 35)) | ((al < 160) & (mn > 120))
    else:
        bgc = np.median(im[:20, :20].reshape(-1, 3), 0)
        bg = np.abs(im - bgc).sum(-1) < 70
        d = np.array([255., 255., 255.]) - bgc
        t = np.clip(((im - bgc) @ d) / (d @ d), 0, 1)
        light = ((np.abs(im - (bgc + t[..., None] * d)).sum(-1) < 45) & (t > 0.1)) | ((mn > 215) & ((mx - mn) < 35))
    gray = (lum > 100) & ((mx - mn) < 60)
    한도 = max(6, int(round(선두께(bg, light) * 2.5)))                 # 테두리 두께의 2.5배까지만 안쪽으로 (흰 털 · 흰 옷 보호)
    cur = bg.copy()
    for _ in range(한도):
        grow = dil(cur) & ~cur & light
        if not grow.any(): break
        cur |= grow
    grow = dil(cur) & ~cur & gray
    cur |= grow
    out = rgba.copy()
    edge = dil(cur) & ~cur
    soft = edge & (lum > 60) & ((mx - mn) < 60)
    if 가장자리진하게: out[soft, :3] *= 0.45
    if 투명:
        out[cur] = 0                                                  # 지운 자리는 투명하게
        return Image.fromarray(out.astype('uint8'), 'RGBA')
    out[cur, :3] = bgc
    return Image.fromarray(out[..., :3].astype('uint8'))

EXT = ('.png', '.webp', '.jpg', '.jpeg')

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    over = '--덮어쓰기' in sys.argv
    dark = '--원래선' not in sys.argv
    if not args:
        print(__doc__ or '쓰는 법 : python 흰선제거.py 그림또는폴더 [--덮어쓰기]'); return
    src = args[0]
    if os.path.isdir(src):
        dst = src if over else (args[1] if len(args) > 1 else src.rstrip('\\/') + '_흰선없음')
        os.makedirs(dst, exist_ok=True)
        files = [f for f in sorted(os.listdir(src)) if f.lower().endswith(EXT)]
        for i, f in enumerate(files, 1):
            o = 흰선제거(Image.open(os.path.join(src, f)), dark)
            o.save(os.path.join(dst, os.path.splitext(f)[0] + '.png'))
            print(f'{i}/{len(files)}  {f}')
        print('끝 →', dst)
    else:
        base, _ = os.path.splitext(src)
        out = base + '.png' if over else base + '_흰선없음.png'
        흰선제거(Image.open(src), dark).save(out)
        print('끝 →', out)

if __name__ == '__main__':
    main()
