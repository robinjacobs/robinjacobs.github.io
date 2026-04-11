import os
import csv
import argparse
from PIL import Image, ExifTags, ImageOps

# --- CONFIGURATION ---
SOURCE_DIR = "assets/images"
DB_FILE = "photo_database.csv"
THUMB_SUFFIX = "_thumb"
# Hardcoded system/website files to always skip
IGNORE_LIST = ["approx_sf_diag.jpg", "picture.jpg"]

CAMERA_MAP = {
    "ILCE-7C": "Sony Alpha 7C",
    "ILCE-7RM4": "Sony Alpha 7R IV",
}


def get_exif_data(image_path):
    metadata = {
        "model": "Unknown Camera",
        "lens": "Unknown Lens",
        "date": "Unknown Date",
    }
    try:
        with Image.open(image_path) as img:
            exif = img._getexif()
            if not exif:
                return metadata
            readable_exif = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}

            raw_model = readable_exif.get("Model", "Unknown Camera")
            metadata["model"] = CAMERA_MAP.get(raw_model, raw_model)

            if "DateTimeOriginal" in readable_exif:
                # Converts YYYY:MM:DD to YYYY/MM/DD
                metadata["date"] = (
                    readable_exif["DateTimeOriginal"].split(" ")[0].replace(":", "/")
                )

            # Try to find Lens Model in standard tags
            metadata["lens"] = readable_exif.get(
                "LensModel", readable_exif.get(0xA434, "Unknown Lens")
            )
    except Exception:
        pass  # Silently fail for EXIF errors
    return metadata


def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, mode="r", encoding="utf-8") as f:
        # Use Dict comprehension to load filename -> category
        return {rows[0]: rows[1] for rows in csv.reader(f) if len(rows) >= 2}


def save_to_db(filename, category):
    with open(DB_FILE, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([filename, category])


def generate():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--interactive", action="store_true", help="Categorize new images"
    )
    args = parser.parse_args()

    db = load_db()
    categories = ["landscapes", "architecture", "nature", "ignore"]

    # --- THE BUG FIX ---
    # We filter out files that:
    # 1. Are in the hardcoded IGNORE_LIST
    # 2. Contain the THUMB_SUFFIX (e.g. _thumb)
    # 3. Are not .jpg or .jpeg
    files = [
        f
        for f in os.listdir(SOURCE_DIR)
        if f.lower().endswith((".jpg", ".jpeg"))
        and f not in IGNORE_LIST
        and THUMB_SUFFIX not in f.lower()
    ]

    html_output = ""

    for filename in files:
        full_path = os.path.join(SOURCE_DIR, filename)

        # 1. Categorization Logic
        if filename in db:
            category = db[filename]
        elif args.interactive:
            print(f"\n--- NEW PHOTO: {filename} ---")
            for i, cat in enumerate(categories):
                print(f" [{i}] {cat}")
            choice = input("Select category index (default 0): ").strip()

            if choice.isdigit() and int(choice) < len(categories):
                category = categories[int(choice)]
            elif not choice:
                category = categories[0]
            else:
                category = choice  # allows custom typing

            save_to_db(filename, category)
        else:
            category = "landscapes"  # Default fallback

        # 2. Skip logic
        if category.lower() == "ignore":
            continue

        # 3. Thumbnail Generation
        name_part, ext_part = os.path.splitext(filename)
        thumb_name = f"{name_part}{THUMB_SUFFIX}{ext_part}"
        thumb_path = os.path.join(SOURCE_DIR, thumb_name)

        if not os.path.exists(thumb_path):
            try:
                with Image.open(full_path) as img:
                    img = ImageOps.exif_transpose(img)  # Correct orientation
                    img.thumbnail((800, 800))
                    img.save(thumb_path, quality=80, optimize=True)
                    print(f"  > Created thumbnail for {filename}")
            except Exception as e:
                print(f"  > Could not create thumbnail for {filename}: {e}")
                continue

        # 4. Meta & HTML Build
        meta = get_exif_data(full_path)
        # Clean title: removes extension, replaces separators with spaces
        title = name_part.replace("-", " ").replace("_", " ").title()

        html_output += f"""
        <div class="col-12 col-md-6 col-lg-4 gallery-item" data-category="{category}">
            <div class="photo-card" data-bs-toggle="modal" data-bs-target="#imageModal"
                 data-full="{full_path}" data-title="{title}"
                 data-date="{meta["date"]}" data-gear="{meta["model"]} + {meta["lens"]}">
                <img src="{thumb_path}" loading="lazy" alt="{title}">
                <div class="photo-overlay">
                    <div class="overlay-text">
                        <h5 class="mb-0 fw-bold">{title}</h5>
                        <small>{meta["model"]}</small>
                    </div>
                </div>
            </div>
        </div>"""

    print("\n" + "=" * 40)
    print(" GENERATION COMPLETE: COPY TO HTML ")
    print("=" * 40 + "\n")
    if html_output:
        print(html_output)
    else:
        print("No images found (all ignored or empty folder).")


if __name__ == "__main__":
    generate()
