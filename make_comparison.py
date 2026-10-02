"""Make a faithful right-eye comparison figure from saved PNGs."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from reproduce_quality import DEFAULT_ROOT, WORKLOADS, original_psnr


def main():
    folder = DEFAULT_ROOT / WORKLOADS["driving_15_300"]
    name = "0039.png"  # Median per-frame stereo PSNR difference in frames.csv.
    paths = [
        ("Ground truth", folder / "right" / name),
        ("HEVC, 5 Mbps / eye", folder / "5_right" / name),
        ("PIRATE archived 8+1", folder / "8+1_cuda" / name),
        ("PIRATE current CUDA", folder / "cuda_right" / name),
    ]
    images = [Image.open(path).convert("RGB") for _, path in paths]
    psnr = original_psnr(folder / "test_numba.py")
    width, height = images[0].size
    pad, caption = 12, 40
    canvas = Image.new("RGB", (2 * width + 3 * pad, 2 * (height + caption) + 3 * pad), "white")
    draw = ImageDraw.Draw(canvas)
    font_path = Path(r"C:\Windows\Fonts\arial.ttf")
    font = ImageFont.truetype(str(font_path), 23) if font_path.is_file() else ImageFont.load_default()
    gt = np.asarray(images[0])
    for index, ((label, _), image) in enumerate(zip(paths, images)):
        row, col = divmod(index, 2)
        x, y = pad + col * (width + pad), pad + row * (height + caption + pad)
        canvas.paste(image, (x, y + caption))
        value = "" if index == 0 else f"  |  PSNR {float(psnr(np.asarray(image), gt)):.3f} dB"
        draw.text((x, y + 7), label + value, fill="black", font=font)
    out = Path("results/quality_audit/comparison_driving_15_300_frame0039.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    print(str(out.resolve()).encode("unicode_escape").decode("ascii"))


if __name__ == "__main__":
    main()
