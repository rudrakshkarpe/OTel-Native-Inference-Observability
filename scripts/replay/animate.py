"""Animate authentic Dash0 captures with magnified excerpts and editorial highlights.

Adapted from logfire-inference-lab/scripts/build_walkthrough.py.
Copyright (c) 2026 Rudraksh Karpe, MIT license (see repository LICENSE).
"""

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path("docs/assets/dash0")
SIZE = (1280, 800)
BG = "#0b1018"
TEXT = "#f2f6ff"
MUTED = "#9aabc1"
CYAN = "#54dfd2"
AMBER = "#ffc269"
RED = "#ff797c"


def font(size):
    # Pillow's bundled font keeps generation portable across CI and local machines.
    return ImageFont.load_default(size=size)


@dataclass
class Detail:
    crop: tuple[int, int, int, int]
    target: tuple[int, int, int, int]
    label: str
    highlights: tuple[tuple[tuple[int, int, int, int], str], ...] = ()


@dataclass
class Scene:
    filename: str
    step: str
    title: str
    finding: str
    explanation: str
    color: str
    details: tuple[Detail, ...]


def mapped(rect, source, target):
    sx = (target[2] - target[0]) / (source[2] - source[0])
    sy = (target[3] - target[1]) / (source[3] - source[1])
    return (
        target[0] + (rect[0] - source[0]) * sx,
        target[1] + (rect[1] - source[1]) * sy,
        target[0] + (rect[2] - source[0]) * sx,
        target[1] + (rect[3] - source[1]) * sy,
    )


def render(scene, index, progress, scenes, footer=None):
    screenshot = Image.open(ASSETS / f"{scene.filename}.png").convert("RGB")
    frame = Image.new("RGB", SIZE, BG)
    preview = screenshot.copy()
    preview.thumbnail((1208, 438), Image.Resampling.LANCZOS)
    px, py = (SIZE[0] - preview.width) // 2, 151
    preview_box = (px, py, px + preview.width, py + preview.height)
    frame.paste(preview, (px, py))
    # Dim context as the unmodified detail crops expand out of their original positions.
    shade = Image.new("RGB", SIZE, BG)
    frame = Image.blend(frame, shade, 0.88 * progress)
    eased = 1 - (1 - progress) ** 3
    for detail in scene.details:
        start = mapped(detail.crop, (0, 0, *screenshot.size), preview_box)
        target = tuple(round(a + (b - a) * eased) for a, b in zip(start, detail.target))
        excerpt = screenshot.crop(detail.crop).resize(
            (target[2] - target[0], target[3] - target[1]), Image.Resampling.LANCZOS
        )
        frame.paste(excerpt, target[:2])
        if progress == 1:
            draw = ImageDraw.Draw(frame)
            draw.rectangle(target, outline="#42526b", width=1)
            draw.text(
                (target[0], target[1] - 26), detail.label, font=font(16), fill=MUTED
            )
            for rect, color in detail.highlights:
                bounds = tuple(round(v) for v in mapped(rect, detail.crop, target))
                draw.rounded_rectangle(bounds, radius=5, outline=color, width=3)

    draw = ImageDraw.Draw(frame)
    draw.rectangle((0, 0, 1280, 137), fill=BG)
    draw.text((36, 18), "OTEL INFERENCE LAB  /  DASH0", font=font(16), fill=MUTED)
    draw.text((36, 51), scene.title, font=font(34), fill=TEXT)
    # A small four-step rail makes the loop's progression clear without a loading animation.
    for i, item in enumerate(scenes):
        spacing = 1220 / len(scenes)
        x = round(36 + i * spacing)
        color = scene.color if i == index else "#253145"
        draw.rounded_rectangle((x, 110, x + spacing - 17, 114), radius=2, fill=color)
        draw.text((x, 122), f"0{i + 1}  {item.step}", font=font(14), fill=MUTED)

    draw.rectangle((0, 609, 1280, 800), fill=BG)
    draw.rounded_rectangle((36, 630, 42, 731), radius=3, fill=scene.color)
    draw.text((61, 638), scene.finding, font=font(32), fill=scene.color)
    draw.text((61, 689), scene.explanation, font=font(23), fill=TEXT)
    draw.text(
        (36, 763),
        footer
        or "ACTUAL DASH0 CAPTURES  /  MAGNIFIED EXCERPTS  /  CONTROLLED WORKLOAD",
        font=font(14),
        fill=MUTED,
    )
    return frame


def build(scenes, destination, preview, footer=None):
    frames, durations, focused = [], [], []
    for i, scene in enumerate(scenes):
        frames.append(render(scene, i, 0, scenes, footer))
        durations.append(160)
        for step in range(1, 7):
            frames.append(render(scene, i, step / 6, scenes, footer))
            durations.append(60)
        focused.append(frames[-1])
        durations[-1] += 2000
        next_index = (i + 1) % len(scenes)
        next_frame = render(scenes[next_index], next_index, 0, scenes, footer)
        transition = Image.new("RGB", SIZE, BG)
        frames.extend(
            [
                Image.blend(focused[-1], transition, 0.65),
                Image.blend(next_frame, transition, 0.65),
                next_frame,
            ]
        )
        durations.extend([60, 60, 60])

    # Share one palette to avoid color flicker between zoom and hold frames.
    swatches = Image.new("RGB", (640, 400 * len(focused)))
    for i, frame in enumerate(focused):
        swatches.paste(frame.resize((640, 400)), (0, i * 400))
    palette = swatches.quantize(colors=192)
    encoded = [
        frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames
    ]
    encoded[0].save(
        destination,
        save_all=True,
        append_images=encoded[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=1,
    )
    preview.mkdir(parents=True, exist_ok=True)
    for i, (scene, frame) in enumerate(zip(scenes, focused)):
        frame.save(preview / f"{i + 1:02d}-{scene.step.lower()}.png")
    print(
        f"{destination}: {sum(durations) / 1000:.1f}s, {destination.stat().st_size / 1e6:.2f} MB"
    )
