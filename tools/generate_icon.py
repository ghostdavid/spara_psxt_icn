from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent.parent
SIZES = (16, 24, 32, 48, 64, 128, 256)
BACKGROUND = '#FFFFFF'
CYAN = '#009BB5'
ORANGE = '#E88719'
PATHS = (
    ('#C4D2DB', 6, ((56, 128), (200, 128))),
    (CYAN, 16, ((40, 88), (66, 88), (83, 55), (111, 117),
                (139, 55), (167, 88), (216, 88))),
    (ORANGE, 14, ((40, 174), (76, 174), (91, 160), (105, 188),
                  (121, 151), (137, 190), (152, 163), (168, 174), (216, 174))),
    ('#456477', 7, ((128, 112), (128, 135))),
    ('#456477', 7, ((120, 128), (128, 136), (136, 128))),
)
PORTS = ((40, 88, CYAN), (216, 88, CYAN),
         (40, 174, ORANGE), (216, 174, ORANGE))


def render(size):
    scale = size * 4 / 256
    image = Image.new('RGBA', (size * 4, size * 4))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(tuple(v * scale for v in (8, 8, 248, 248)),
                           radius=48 * scale, fill=BACKGROUND)
    for color, width, points in PATHS:
        coords = [(x * scale, y * scale) for x, y in points]
        draw.line(coords, fill=color, width=max(1, round(width * scale)), joint='curve')
        radius = width * scale / 2
        for x, y in coords:
            draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=color)
    for x, y, color in PORTS:
        draw.ellipse(tuple(v * scale for v in (x-12, y-12, x+12, y+12)), fill=color)
        draw.ellipse(tuple(v * scale for v in (x-4, y-4, x+4, y+4)), fill=BACKGROUND)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main():
    target = ROOT / 'assets'
    target.mkdir(exist_ok=True)
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">',
           '  <title>S-parameter crosstalk and noise</title>',
           f'  <rect x="8" y="8" width="240" height="240" rx="48" fill="{BACKGROUND}"/>']
    for color, width, points in PATHS:
        data = 'M ' + ' L '.join(f'{x} {y}' for x, y in points)
        svg.append(f'  <path d="{data}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>')
    for x, y, color in PORTS:
        svg.append(f'  <circle cx="{x}" cy="{y}" r="12" fill="{color}"/>')
        svg.append(f'  <circle cx="{x}" cy="{y}" r="4" fill="{BACKGROUND}"/>')
    svg.append('</svg>')
    (target / 'app_icon.svg').write_text('\n'.join(svg) + '\n', encoding='utf-8')
    images = [render(size) for size in SIZES]
    images[-1].save(target / 'app_icon.png')
    images[-1].save(target / 'app_icon.ico', sizes=[(s, s) for s in SIZES],
                    append_images=images[:-1])


if __name__ == '__main__':
    main()
