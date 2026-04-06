"""
生成应用图标 - 蓝色圆形背景 + 白色 "T" 字
生成 PNG 和 ICO 格式
"""
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.resolve()
ASSETS_DIR = PROJECT_ROOT / "assets"


def create_icon(size: int) -> Image.Image:
    """创建指定尺寸的图标"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 蓝色圆形背景 (0, 120, 212)
    margin = 0
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=(0, 120, 212, 255)
    )

    # 白色 "T" 文字 - 更大的字体，更粗
    font_size = int(size * 0.7)  # 增大到 70%
    try:
        # 尝试使用 Arial Bold 粗体
        font = ImageFont.truetype("arialbd.ttf", font_size)
    except:
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", font_size)
        except:
            try:
                # 尝试使用 Arial
                font = ImageFont.truetype("arial.ttf", font_size)
            except:
                try:
                    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", font_size)
                except:
                    font = ImageFont.load_default()

    # 计算文字位置使其居中
    text = "T"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (size - text_width) // 2
    y = (size - text_height) // 2 - bbox[1]  # 修正y坐标

    draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)

    return img


def create_icon_image():
    """创建并保存图标"""
    # 创建 assets 目录
    ASSETS_DIR.mkdir(exist_ok=True)

    # 生成多个尺寸的 PNG
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = []

    for size in sizes:
        img = create_icon(size)
        images.append(img)
        print(f"Created {size}x{size} icon")

    # 保存 256x256 PNG (作为源文件)
    icon_256 = create_icon(256)
    png_path = ASSETS_DIR / "icon.png"
    icon_256.save(png_path)
    print(f"Saved: {png_path}")

    # 创建 ICO 文件 (包含多个尺寸)
    ico_path = ASSETS_DIR / "icon.ico"

    # ICO 需要 16x16, 32x32, 48x48, 256x256
    ico_sizes = [16, 32, 48, 256]
    ico_images = [create_icon(s) for s in ico_sizes]

    # 保存 ICO (使用 PIL 的 ICO 格式)
    ico_images[0].save(
        ico_path,
        format='ICO',
        sizes=[(s, s) for s in ico_sizes],
        append_images=ico_images[1:]
    )
    print(f"Saved: {ico_path}")

    print(f"\n图标已生成到: {ASSETS_DIR}")
    print(f"  - icon.png (256x256)")
    print(f"  - icon.ico (多尺寸)")


if __name__ == "__main__":
    create_icon_image()