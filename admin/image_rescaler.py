import os
from PIL import Image

# Configuration
SOURCE_DIR = "assets/images"
MAX_SIZE = (800, 800)  # Max width/height. Keeps aspect ratio.
THUMB_SUFFIX = "_thumb"
QUALITY = 80  # JPEG quality (0-100). 80 is a good balance.


def create_thumbnails():
    # check if directory exists
    if not os.path.exists(SOURCE_DIR):
        print(f"Error: Directory '{SOURCE_DIR}' not found.")
        return

    # Loop through all files in the directory
    for filename in os.listdir(SOURCE_DIR):
        # Check if it is an image and NOT already a thumbnail
        if (
            filename.lower().endswith((".jpg", ".jpeg", ".png"))
            and THUMB_SUFFIX not in filename
        ):
            full_path = os.path.join(SOURCE_DIR, filename)

            try:
                with Image.open(full_path) as img:
                    # Create the new filename
                    # e.g., "photo.JPG" -> "photo_thumb.JPG"
                    name, ext = os.path.splitext(filename)
                    new_filename = f"{name}{THUMB_SUFFIX}{ext}"
                    new_full_path = os.path.join(SOURCE_DIR, new_filename)

                    # Check if thumbnail already exists to avoid re-processing
                    if os.path.exists(new_full_path):
                        print(f"Skipping: {new_filename} (already exists)")
                        continue

                    # fix orientation if image has EXIF data (common with phone photos)
                    from PIL import ImageOps

                    img = ImageOps.exif_transpose(img)

                    # Create thumbnail (modifies image in place, preserves aspect ratio)
                    img.thumbnail(MAX_SIZE)

                    # Save the new file
                    img.save(new_full_path, quality=QUALITY, optimize=True)

                    print(f"Created: {new_filename}")

            except Exception as e:
                print(f"Error processing {filename}: {e}")


if __name__ == "__main__":
    print("--- Starting Thumbnail Generator ---")
    create_thumbnails()
    print("--- Done! ---")
