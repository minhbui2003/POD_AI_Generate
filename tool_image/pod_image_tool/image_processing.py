import io
import math

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


class ImageProcessor:
    @staticmethod
    def load_original(image_path):
        """Load original image as RGBA."""
        return Image.open(image_path).convert("RGBA")

    @staticmethod
    def composite_on_white(img):
        """Composite RGBA image on white background for API input."""
        white = Image.new("RGBA", img.size, (255, 255, 255, 255))
        white.paste(img, mask=img.split()[3])
        return white.convert("RGB")

    @classmethod
    def api_input_png_bytes(cls, image_path):
        """Return a flattened white-background PNG for image APIs."""
        image = cls.load_original(image_path)
        flattened = cls.composite_on_white(image)
        buffer = io.BytesIO()
        flattened.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    @staticmethod
    def _edge_sample_points(width, height, samples_per_edge=64):
        if width <= 0 or height <= 0:
            return []

        points = []
        x_step = max(1, width // max(1, samples_per_edge))
        y_step = max(1, height // max(1, samples_per_edge))

        for x in range(0, width, x_step):
            points.append((x, 0))
            points.append((x, height - 1))
        for y in range(0, height, y_step):
            points.append((0, y))
            points.append((width - 1, y))

        return points

    @classmethod
    def _estimate_edge_background(cls, rgb):
        width, height = rgb.size
        pixels = rgb.load()
        points = cls._edge_sample_points(width, height)
        samples = [pixels[x, y] for x, y in points]
        if not samples:
            return (255, 255, 255), 28

        channel_count = len(samples)
        bg = tuple(int(sum(pixel[idx] for pixel in samples) / channel_count) for idx in range(3))
        deviations = [
            math.sqrt(sum((pixel[idx] - bg[idx]) ** 2 for idx in range(3)))
            for pixel in samples
        ]
        avg_deviation = sum(deviations) / len(deviations)
        tolerance = int(max(22, min(76, avg_deviation * 2.5 + 24)))
        return bg, tolerance

    @staticmethod
    def _color_distance(a, b):
        return math.sqrt(sum((a[idx] - b[idx]) ** 2 for idx in range(3)))

    @staticmethod
    def _sentinel_color(bg):
        candidates = [(255, 0, 255), (0, 255, 0), (0, 0, 255), (1, 2, 3)]
        return max(candidates, key=lambda color: ImageProcessor._color_distance(color, bg))

    @classmethod
    def remove_edge_background(cls, img, max_removed_ratio=0.60, feather_radius=1.2):
        """Remove only background connected to image edges using adaptive flood-fill."""
        rgba = img.convert("RGBA")
        rgb = rgba.convert("RGB")
        width, height = rgb.size
        if width <= 0 or height <= 0:
            return rgba, {"removed_ratio": 0, "warning": ""}

        bg, tolerance = cls._estimate_edge_background(rgb)
        sentinel = cls._sentinel_color(bg)
        filled = rgb.copy()
        original_pixels = rgb.load()
        filled_pixels = filled.load()

        border_points = []
        for x in range(width):
            border_points.append((x, 0))
            border_points.append((x, height - 1))
        for y in range(height):
            border_points.append((0, y))
            border_points.append((width - 1, y))

        for point in border_points:
            x, y = point
            if filled_pixels[x, y] == sentinel:
                continue
            if cls._color_distance(original_pixels[x, y], bg) <= tolerance:
                ImageDraw.floodfill(filled, point, sentinel, thresh=tolerance)

        mask_data = []
        removed_count = 0
        for pixel in filled.getdata():
            if pixel == sentinel:
                mask_data.append(0)
                removed_count += 1
            else:
                mask_data.append(255)

        alpha = Image.new("L", (width, height))
        alpha.putdata(mask_data)
        if feather_radius > 0:
            alpha = alpha.filter(ImageFilter.GaussianBlur(feather_radius))

        result = rgba.copy()
        result.putalpha(alpha)

        removed_ratio = removed_count / max(1, width * height)
        warning = ""
        if removed_ratio > max_removed_ratio:
            warning = (
                f"Transparent background removed {removed_ratio:.0%} of the image. "
                "Review manually; the subject may touch the border or include very light areas."
            )

        return result, {
            "background_rgb": bg,
            "tolerance": tolerance,
            "removed_ratio": removed_ratio,
            "warning": warning,
        }

    @staticmethod
    def sharpen(img):
        """Apply print-quality sharpening and color enhancement to RGB channels."""
        r, g, b, a = img.split()
        rgb = Image.merge("RGB", (r, g, b))

        rgb = rgb.filter(ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=2))
        enhancer = ImageEnhance.Color(rgb)
        rgb = enhancer.enhance(1.12)

        r2, g2, b2 = rgb.split()
        return Image.merge("RGBA", (r2, g2, b2, a))

    @staticmethod
    def upscale_for_print(img, min_long_edge):
        """Upscale image to a minimum longest edge for better print quality."""
        if min_long_edge <= 0:
            return img

        width, height = img.size
        longest_edge = max(width, height)
        if longest_edge >= min_long_edge:
            return img

        scale_factor = min_long_edge / longest_edge
        new_width = max(1, int(width * scale_factor))
        new_height = max(1, int(height * scale_factor))
        return img.resize((new_width, new_height), Image.LANCZOS)

    @classmethod
    def full_pipeline(
        cls,
        original_path,
        generated_bytes,
        canvas_w=2400,
        canvas_h=2400,
        target_size=1800,
        print_enhance=False,
        output_background="White",
        return_warnings=False,
    ):
        """Return generated output, optionally removing edge background and upscaling."""
        warnings = []
        generated = Image.open(io.BytesIO(generated_bytes)).convert("RGBA")
        if output_background == "Transparent":
            generated, info = cls.remove_edge_background(generated)
            if info.get("warning"):
                warnings.append(info["warning"])

        if not print_enhance:
            return (generated, warnings) if return_warnings else generated

        min_long_edge = max(canvas_w, canvas_h, target_size)
        generated = cls.upscale_for_print(generated, min_long_edge)
        generated = cls.sharpen(generated)
        return (generated, warnings) if return_warnings else generated
