import os
import json

def generate_posts_json():
    """
    Scans the '_posts' directory for markdown files and generates a posts.json
    file containing a list of the filenames, sorted by date.
    """
    posts_dir = '_posts'
    posts_list = []
    if os.path.exists(posts_dir):
        # Sort files by name, which should correspond to the date
        for filename in sorted(os.listdir(posts_dir), reverse=True):
            if filename.endswith('.md'):
                posts_list.append(filename)

    with open('posts.json', 'w') as f:
        json.dump(posts_list, f, indent=4)
    print("posts.json generated successfully.")

if __name__ == '__main__':
    generate_posts_json()
