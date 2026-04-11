import os
import csv
from PIL import Image, ExifTags, ImageOps

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_DIR = os.path.join(BASE_DIR, "assets/images")
DB_FILE = os.path.join(BASE_DIR, "photo_database.csv")
GALLERY_FILE = os.path.join(BASE_DIR, "gallery.html")
THUMB_SUFFIX = "_thumb"
MAX_SIZE = (800, 800)
QUALITY = 80

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
                metadata["date"] = (
                    readable_exif["DateTimeOriginal"].split(" ")[0].replace(":", "/")
                )

            metadata["lens"] = readable_exif.get(
                "LensModel", readable_exif.get(0xA434, "Unknown Lens")
            )
    except Exception:
        pass
    return metadata

def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, mode="r", encoding="utf-8") as f:
        return {rows[0]: rows[1] for rows in csv.reader(f) if len(rows) >= 2}

def save_db(db):
    with open(DB_FILE, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for filename, category in db.items():
            writer.writerow([filename, category])

def create_thumbnail(filename):
    full_path = os.path.join(SOURCE_DIR, filename)
    name_part, ext_part = os.path.splitext(filename)
    thumb_name = f"{name_part}{THUMB_SUFFIX}{ext_part}"
    thumb_path = os.path.join(SOURCE_DIR, thumb_name)

    try:
        with Image.open(full_path) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail(MAX_SIZE)
            img.save(thumb_path, quality=QUALITY, optimize=True)
            return thumb_name
    except Exception as e:
        print(f"Error creating thumbnail for {filename}: {e}")
        return None

def generate_gallery_html():
    db = load_db()
    # Filter files: must be in DB and not a thumbnail
    files = [
        f for f in os.listdir(SOURCE_DIR)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
        and THUMB_SUFFIX not in f.lower()
        and f in db
        and db[f].lower() != "ignore"
    ]

    # Sort files to maintain some order, maybe by date from EXIF or filename
    files.sort(reverse=True)

    html_blocks = []
    for filename in files:
        category = db[filename]
        # Use relative paths for the web
        rel_full_path = f"assets/images/{filename}"
        name_part, ext_part = os.path.splitext(filename)
        thumb_name = f"{name_part}{THUMB_SUFFIX}{ext_part}"
        rel_thumb_path = f"assets/images/{thumb_name}"
        
        abs_full_path = os.path.join(SOURCE_DIR, filename)
        abs_thumb_path = os.path.join(SOURCE_DIR, thumb_name)

        if not os.path.exists(abs_thumb_path):
            create_thumbnail(filename)

        meta = get_exif_data(abs_full_path)
        title = name_part.replace("-", " ").replace("_", " ").title()

        block = f"""
            <div class="col-12 col-md-6 col-lg-4 gallery-item" data-category="{category}">
                <div class="photo-card" data-bs-toggle="modal" data-bs-target="#imageModal"
                     data-full="{rel_full_path}" data-title="{title}"
                     data-date="{meta["date"]}" data-gear="{meta["model"]} + {meta["lens"]}">
                    <img src="{rel_thumb_path}" loading="lazy" alt="{title}">
                    <div class="photo-overlay">
                        <div class="overlay-text">
                            <h5 class="mb-0 fw-bold">{title}</h5>
                            <small>{meta["model"]}</small>
                        </div>
                    </div>
                </div>
            </div>"""
        html_blocks.append(block)

    return "\n".join(html_blocks)

def update_gallery_file():
    new_content = generate_gallery_html()

    with open(GALLERY_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    start_marker = "<!-- GALLERY_START -->"
    end_marker = "<!-- GALLERY_END -->"

    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)

    if start_idx == -1 or end_idx == -1:
        print("Error: Gallery markers not found in gallery.html")
        return False

    updated_content = (
        content[:start_idx + len(start_marker)]
        + "\n"
        + new_content
        + "\n            "
        + content[end_idx:]
    )

    with open(GALLERY_FILE, "w", encoding="utf-8") as f:
        f.write(updated_content)
    return True
