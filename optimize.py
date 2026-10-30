#!/usr/bin/env python3
"""Generate responsive WebP and JPEG derivatives, and rewire index.html to them.

    python3 optimize.py            build derivatives and patch the HTML
    python3 optimize.py --check    report sizes only, change nothing

Originals stay where they are and remain the masters. Derivatives land in
img/r/. Widths are capped at the source width so nothing is ever upscaled.

Two mechanisms, because the page uses two. Real <img> tags become <picture>
with a WebP source and a JPEG fallback. The four CSS background bands cannot
use <picture>, so they get a class whose rule declares a plain url() first and
an image-set() second: browsers that understand image-set take the WebP, the
rest keep the JPEG.
"""
import os, re, sys
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'img', 'r')
HTML = os.path.join(HERE, 'index.html')
BP = 980                      # the page's one breakpoint

# path -> how it is displayed. `sizes` is what the browser needs to pick.
IMGS = {
    'img/hero-wide.jpg':          dict(w=[960, 1440, 1920], sizes='100vw', eager=True),
    'img/portrait-farmstand.jpg': dict(w=[400, 760, 1000],
                                       sizes=f'(max-width:{BP}px) 92vw, 379px'),
    'img/band-farm.jpg':          dict(w=[600, 1160],
                                       sizes=f'(max-width:{BP}px) 100vw, 576px'),
    'img/pass-whites.jpg':        dict(w=[340, 680],
                                       sizes=f'(max-width:{BP}px) 92vw, 328px'),
    'img/card-crudo.jpg':         dict(w=[340, 680],
                                       sizes=f'(max-width:{BP}px) 92vw, 328px'),
    'img/book-wine-mondays.jpg':  dict(w=[340, 680],
                                       sizes=f'(max-width:{BP}px) 92vw, 328px'),
    'img/band-dessert.jpg':       dict(w=[480, 960],
                                       sizes=f'(max-width:{BP}px) 50vw, 25vw'),
    'img/band-firepit.jpg':       dict(w=[480, 960],
                                       sizes=f'(max-width:{BP}px) 50vw, 25vw'),
    'img/band-notebook.jpg':      dict(w=[480, 960],
                                       sizes=f'(max-width:{BP}px) 50vw, 25vw'),
    'img/band-lobster.jpg':       dict(w=[480, 960],
                                       sizes=f'(max-width:{BP}px) 50vw, 25vw'),
    'img/brand/logo-lockup.png':  dict(w=[248, 496], sizes='clamp(186px,21vw,248px)'),
    'img/brand/chicken-solid.png': dict(w=[140, 280], sizes='clamp(104px,11vw,138px)'),
}

# full bleed CSS backgrounds: path -> css class
BGS = {
    'img/band-bread.jpg':   'bg-bread',
    'img/band-cm.jpg':      'bg-cm',
    'img/band-harvest.jpg': 'bg-harvest',
    'img/fire-fish.jpg':    'bg-fire',
}
BG_W = [1280, 1920]

Q_WEBP, Q_JPEG, Q_WEBP_ALPHA = 78, 80, 90


def stem(path):
    return os.path.splitext(os.path.basename(path))[0]


def derive(path, widths):
    """Write WebP and same-format fallbacks. Returns [(w, webp, fallback)]."""
    src = os.path.join(HERE, path)
    png = path.lower().endswith('.png')
    made = []
    with Image.open(src) as im:
        im.load()
        sw, sh = im.size
        alpha = png and im.mode in ('RGBA', 'LA', 'P')
        base = im.convert('RGBA' if alpha else 'RGB')
        targets = sorted({min(w, sw) for w in widths})
        for w in targets:
            h = round(sh * w / sw)
            r = base.resize((w, h), Image.LANCZOS)
            wp = f'img/r/{stem(path)}-{w}.webp'
            r.save(os.path.join(HERE, wp), 'WEBP',
                   quality=Q_WEBP_ALPHA if alpha else Q_WEBP, method=6)
            if png:
                fb = f'img/r/{stem(path)}-{w}.png'
                r.save(os.path.join(HERE, fb), 'PNG', optimize=True)
            else:
                fb = f'img/r/{stem(path)}-{w}.jpg'
                r.save(os.path.join(HERE, fb), 'JPEG', quality=Q_JPEG,
                       optimize=True, progressive=True)
            made.append((w, wp, fb))
    return made, (sw, sh)


def srcset(items, idx):
    return ', '.join(f'{it[idx]} {it[0]}w' for it in items)


def attrs_of(tag):
    """Keep whatever the original tag said about class, alt and aria."""
    keep = {}
    for k in ('class', 'alt', 'aria-hidden'):
        m = re.search(rf'{k}="([^"]*)"', tag)
        if m:
            keep[k] = m.group(1)
    return keep


def main(check=False):
    os.makedirs(OUT, exist_ok=True)
    html = open(HTML, encoding='utf-8').read()
    if '<picture>' in html and not check:
        sys.exit('index.html already uses <picture>. Revert it before re-running.')

    before = after = 0
    for path in list(IMGS) + list(BGS):
        before += os.path.getsize(os.path.join(HERE, path))

    # ---------------------------------------------------------- <img> tags
    for path, cfg in IMGS.items():
        items, (sw, sh) = derive(path, cfg['w'])
        after += min(os.path.getsize(os.path.join(HERE, it[1])) for it in items)
        if check:
            continue
        m = re.search(r'<img[^>]*src="' + re.escape(path) + r'"[^>]*>', html)
        if not m:
            sys.exit(f'could not find the <img> tag for {path}')
        old = m.group(0)
        a = attrs_of(old)
        biggest = items[-1]
        bits = [f'src="{biggest[2]}"',
                f'srcset="{srcset(items, 2)}"',
                f'sizes="{cfg["sizes"]}"',
                f'width="{sw}"', f'height="{sh}"',
                f'alt="{a.get("alt", "")}"', 'decoding="async"']
        if a.get('class'):
            bits.insert(0, f'class="{a["class"]}"')
        if a.get('aria-hidden'):
            bits.append('aria-hidden="true"')
        bits.append('loading="eager" fetchpriority="high"' if cfg.get('eager')
                    else 'loading="lazy"')
        new = ('<picture>'
               f'<source type="image/webp" srcset="{srcset(items, 1)}" '
               f'sizes="{cfg["sizes"]}">'
               f'<img {" ".join(bits)}>'
               '</picture>')
        html = html.replace(old, new, 1)

    # ------------------------------------------------- CSS background bands
    rules = ['picture{display:contents}picture>source{display:none}']
    for path, cls in BGS.items():
        items, _ = derive(path, BG_W)
        after += min(os.path.getsize(os.path.join(HERE, it[1])) for it in items)
        small, large = items[0], items[-1]
        for sel, it in ((f'.{cls}', small), (f'@media (min-width:{BP+1}px){{.{cls}', large)):
            rule = (f"background-image:url('{it[2]}');"
                    f"background-image:image-set(url('{it[1]}') type('image/webp'),"
                    f"url('{it[2]}') type('image/jpeg'))")
            rules.append(f'{sel}{{{rule}}}' + ('}' if sel.startswith('@') else ''))
        if check:
            continue
        pat = r'style="background-image:url\(\'' + re.escape(path) + r"'\)\""
        m = re.search(pat, html)
        if not m:
            sys.exit(f'could not find the background style for {path}')
        # move the image out of the inline style and onto a class
        start = html.rfind('<div', 0, m.start())
        tag = html[start:m.end() + 1]
        newtag = re.sub(pat, '', tag)
        newtag = re.sub(r'class="([^"]*)"', rf'class="\1 {cls}"', newtag, count=1)
        newtag = re.sub(r'\s+>', '>', newtag.replace('  ', ' '))
        html = html[:start] + newtag + html[m.end() + 1:]

    if not check:
        html = html.replace('</style>', '\n' + '\n'.join(rules) + '\n</style>', 1)
        open(HTML, 'w', encoding='utf-8').write(html)

    print(f'  originals delivered: {before/1048576:.2f} MB')
    print(f'  smallest variants:   {after/1048576:.2f} MB')
    n = len([f for f in os.listdir(OUT)]) if os.path.isdir(OUT) else 0
    print(f'  {n} derivative files in img/r/')


if __name__ == '__main__':
    main(check='--check' in sys.argv)
