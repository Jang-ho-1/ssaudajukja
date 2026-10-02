# 흰 테두리 지우기 : 초록 바탕 캐릭터 그림에서 몸 둘레 흰 선(스티커 테두리)만 깎아 냄
#   - 바탕(초록)에서 시작해 붙어 있는 흰색 · 흰+초록 섞인 점을 한 겹씩 지우고, 캐릭터의 진한 선을 만나면 멈춤
#   - 1~2px 짜리 얇은 회색 선 뒤에 숨은 흰 조각(머리띠와 머리 사이 등)도 건너가서 지움
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

def 흰선제거(img, 가장자리진하게=True):
    im = np.array(img.convert('RGB')).astype(float)
    bgc = np.median(im[:20, :20].reshape(-1, 3), 0)                  # 왼쪽 위 구석 = 바탕색
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    lum = r * 0.3 + g * 0.59 + b * 0.11
    mx = im.max(-1); mn = im.min(-1)
    bg = np.abs(im - bgc).sum(-1) < 70
    d = np.array([255., 255., 255.]) - bgc                            # 흰색 ↔ 바탕색 사이 섞인 점 찾기
    t = np.clip(((im - bgc) @ d) / (d @ d), 0, 1)
    light = (np.abs(im - (bgc + t[..., None] * d)).sum(-1) < 75) | ((mn > 140) & ((mx - mn) < 70))
    white = (mn > 190) & ((mx - mn) < 45)
    gray = (lum > 100) & ((mx - mn) < 60)
    cur = bg.copy()
    for _ in range(4):
        for _ in range(40):
            grow = dil(cur) & ~cur & light
            if not grow.any(): break
            cur |= grow
        jump = dil(cur, 3) & ~cur & white                             # 얇은 선 건너 흰 조각
        if not jump.any(): break
        cur |= jump
        light = light | white
    for _ in range(3):                                                # 흰색과 진한 선 사이 회색 번짐
        grow = dil(cur) & ~cur & gray
        if not grow.any(): break
        cur |= grow
    out = im.copy()
    edge = dil(cur) & ~cur
    soft = edge & (lum > 60) & ((mx - mn) < 60)
    if 가장자리진하게:
        out[soft] = out[soft] * 0.45                                  # 가장자리 연한 점은 선 색으로 (끄려면 --원래선)
    out[cur] = bgc
    return Image.fromarray(out.astype('uint8'))

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
