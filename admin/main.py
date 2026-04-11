import os
import shutil
from fastapi import FastAPI, UploadFile, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List

# Ensure we can import utils regardless of how the script is run
import sys
admin_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(admin_dir)
import utils

class RenameRequest(BaseModel):
    new_filename: str

class CategoryRequest(BaseModel):
    category: str

app = FastAPI()

# Mount assets correctly to match gallery.html paths (assets/images/...)
# We mount the parent 'assets' directory so that /assets/images/... works
app.mount("/assets", StaticFiles(directory=os.path.join(utils.BASE_DIR, "assets")), name="assets")

# This allows previewing the actual gallery from the local server
@app.get("/gallery.html", response_class=HTMLResponse)
async def preview_gallery():
    if not os.path.exists(utils.GALLERY_FILE):
        raise HTTPException(status_code=404, detail="gallery.html not found")
    with open(utils.GALLERY_FILE, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/", response_class=HTMLResponse)
async def admin_page():
    admin_html_path = os.path.join(admin_dir, "admin.html")
    with open(admin_html_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/images")
async def get_images():
    db = utils.load_db()
    images = []
    for filename, category in db.items():
        if category.lower() == "ignore":
            continue
        
        name_part, ext_part = os.path.splitext(filename)
        thumb_name = f"{name_part}{utils.THUMB_SUFFIX}{ext_part}"
        # Path must match what the admin dashboard expects to display previews
        thumb_path = f"assets/images/{thumb_name}" 
        
        # Check existence using absolute path from utils
        abs_thumb_path = os.path.join(utils.SOURCE_DIR, thumb_name)
        
        if os.path.exists(abs_thumb_path):
            images.append({
                "filename": filename,
                "category": category,
                "thumb": thumb_path
            })
    return images

@app.post("/api/upload")
async def upload_image(file: UploadFile, category: str = Form(...)):
    # Sanitize filename: replace spaces and other problematic chars
    safe_filename = file.filename.replace(" ", "_").replace("(", "").replace(")", "")
    
    # Ensure directory exists
    os.makedirs(utils.SOURCE_DIR, exist_ok=True)
    
    # Save original file
    file_path = os.path.join(utils.SOURCE_DIR, safe_filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Generate thumbnail
    utils.create_thumbnail(safe_filename)
    
    # Update DB
    db = utils.load_db()
    db[safe_filename] = category
    utils.save_db(db)
    
    # Update gallery.html
    utils.update_gallery_file()
    
    return {"status": "success", "filename": safe_filename}

@app.put("/api/images/{filename}")
async def rename_image(filename: str, request: RenameRequest):
    db = utils.load_db()
    if filename not in db:
        raise HTTPException(status_code=404, detail="Image not found in database")
    
    # Extract current extension
    _, ext = os.path.splitext(filename)
    
    # Sanitize new filename: replace spaces and other problematic chars
    new_name = request.new_filename.strip().replace(" ", "_").replace("(", "").replace(")", "")
    
    # Ensure it has the extension
    if not new_name.lower().endswith(ext.lower()):
        new_name += ext
        
    if new_name == filename:
        return {"status": "success", "message": "No change"}
        
    if new_name in db:
        raise HTTPException(status_code=400, detail="New filename already exists in database")
    
    # Paths for original
    old_file_path = os.path.join(utils.SOURCE_DIR, filename)
    new_file_path = os.path.join(utils.SOURCE_DIR, new_name)
    
    # Paths for thumbnail
    name_part, _ = os.path.splitext(filename)
    old_thumb_name = f"{name_part}{utils.THUMB_SUFFIX}{ext}"
    old_thumb_path = os.path.join(utils.SOURCE_DIR, old_thumb_name)
    
    new_name_part, _ = os.path.splitext(new_name)
    new_thumb_name = f"{new_name_part}{utils.THUMB_SUFFIX}{ext}"
    new_thumb_path = os.path.join(utils.SOURCE_DIR, new_thumb_name)
    
    # Rename on filesystem
    if os.path.exists(old_file_path):
        os.rename(old_file_path, new_file_path)
    if os.path.exists(old_thumb_path):
        os.rename(old_thumb_path, new_thumb_path)
    
    # Update DB
    category = db[filename]
    del db[filename]
    db[new_name] = category
    utils.save_db(db)
    
    # Update gallery.html
    utils.update_gallery_file()
    
    return {"status": "success", "new_filename": new_name}

@app.patch("/api/images/{filename}/category")
async def update_category(filename: str, request: CategoryRequest):
    db = utils.load_db()
    if filename not in db:
        raise HTTPException(status_code=404, detail="Image not found in database")
    
    # Update category
    db[filename] = request.category.lower()
    utils.save_db(db)
    
    # Update gallery.html
    utils.update_gallery_file()
    
    return {"status": "success", "category": request.category}

@app.delete("/api/images/{filename}")
async def delete_image(filename: str):
    db = utils.load_db()
    if filename not in db:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Delete original and thumbnail
    file_path = os.path.join(utils.SOURCE_DIR, filename)
    name_part, ext_part = os.path.splitext(filename)
    thumb_name = f"{name_part}{utils.THUMB_SUFFIX}{ext_part}"
    thumb_path = os.path.join(utils.SOURCE_DIR, thumb_name)
    
    if os.path.exists(file_path):
        os.remove(file_path)
    if os.path.exists(thumb_path):
        os.remove(thumb_path)
        
    # Update DB
    del db[filename]
    utils.save_db(db)
    
    # Update gallery.html
    utils.update_gallery_file()
    
    return {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    # Listening on localhost only for better local security
    uvicorn.run(app, host="127.0.0.1", port=8000)
