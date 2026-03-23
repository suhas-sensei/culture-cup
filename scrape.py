#!/usr/bin/env python3
"""
Instagram Post Scraper
Downloads posts, uploads to ImgBB, fetches engagement data + comments, writes CSV.

Usage: python scrape.py <username> [--count N]
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import browser_cookie3
import requests

IMGBB_API_KEY = "8581c981fd6ff5630d156361ce64f25d"
SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR / "output"


def get_instagram_session():
    cj = browser_cookie3.chrome(domain_name=".instagram.com")
    csrf = None
    for c in cj:
        if c.name == "csrftoken":
            csrf = c.value
    session = requests.Session()
    session.cookies = cj
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "X-IG-App-ID": "936619743392459",
        "X-CSRFToken": csrf or "",
        "Referer": "https://www.instagram.com/",
        "Accept": "application/json",
    })
    return session


def download_posts(username, count):
    """Use gallery-dl to download posts + metadata."""
    dl_dir = OUTPUT_DIR / username / "images"
    dl_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "gallery_dl",
        "--cookies-from-browser", "chrome",
        "--range", f"1-{count}",
        "--write-metadata",
        "-d", str(dl_dir),
        f"https://www.instagram.com/{username}/",
    ]
    print(f"Downloading {count} posts from @{username}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 and not any(
        f.suffix in (".jpg", ".png", ".webp") for f in dl_dir.rglob("*")
    ):
        print(f"gallery-dl error: {result.stderr}")
        sys.exit(1)

    # Collect downloaded files with their metadata
    posts = []
    meta_dir = dl_dir / "instagram" / username
    if not meta_dir.exists():
        print("No posts downloaded.")
        sys.exit(1)

    # Metadata files are named like "12345.jpg.json"
    json_files = sorted(meta_dir.glob("*.json"))
    for jf in json_files:
        with open(jf) as f:
            meta = json.load(f)

        # Image file is the json filename minus ".json" suffix (e.g. "12345.jpg.json" -> "12345.jpg")
        img_file = jf.with_name(jf.stem)
        if not img_file.exists():
            continue

        posts.append({"meta": meta, "image_path": img_file})

    # Deduplicate by post_id (carousel posts have multiple images)
    seen = {}
    for p in posts:
        pid = p["meta"].get("post_id", "")
        if pid not in seen:
            seen[pid] = p
        else:
            # Keep track of extra images for carousels
            if "extra_images" not in seen[pid]:
                seen[pid]["extra_images"] = []
            seen[pid]["extra_images"].append(p["image_path"])

    return list(seen.values())


def upload_to_imgbb(image_path):
    """Upload image to ImgBB and return the URL."""
    with open(image_path, "rb") as f:
        r = requests.post(
            "https://api.imgbb.com/1/upload",
            params={"key": IMGBB_API_KEY},
            files={"image": f},
        )
    if r.status_code == 200:
        return r.json()["data"]["url"]
    print(f"  ImgBB upload failed for {image_path.name}: {r.text[:200]}")
    return ""


def fetch_comments(session, shortcode):
    """Fetch all comments for a post via GraphQL."""
    all_comments = []
    comment_count = 0
    cursor = ""
    has_next = True

    while has_next:
        variables = json.dumps({
            "shortcode": shortcode,
            "first": 50,
            "after": cursor,
        })
        try:
            r = session.get(
                "https://www.instagram.com/graphql/query/",
                params={
                    "query_hash": "bc3296d1ce80a24b1b6e40b1e72903f5",
                    "variables": variables,
                },
            )
            if r.status_code != 200:
                break
            data = r.json()
            edge_data = data["data"]["shortcode_media"]["edge_media_to_parent_comment"]
            comment_count = edge_data["count"]
            for edge in edge_data["edges"]:
                node = edge["node"]
                all_comments.append({
                    "username": node["owner"]["username"],
                    "text": node["text"],
                    "likes": node.get("edge_liked_by", {}).get("count", 0),
                })
            page_info = edge_data["page_info"]
            has_next = page_info["has_next_page"]
            cursor = page_info.get("end_cursor", "")
            if has_next:
                time.sleep(1)  # Rate limit
        except Exception as e:
            print(f"  Comment fetch error: {e}")
            break

    return comment_count, all_comments


def fetch_reshares(session, media_id):
    """Try to fetch reshare count."""
    try:
        variables = json.dumps({
            "media_id": media_id,
        })
        r = session.get(
            "https://www.instagram.com/graphql/query/",
            params={
                "query_hash": "c8e441e60e080b94a9e34f0b2b97c547",
                "variables": variables,
            },
        )
        if r.status_code == 200:
            data = r.json()
            media = data.get("data", {}).get("shortcode_media", {})
            return media.get("edge_media_preview_comment", {}).get("count", "N/A")
    except Exception:
        pass
    return "N/A"


def write_csv(username, rows):
    """Write results to CSV."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = OUTPUT_DIR / f"{username}_{timestamp}.csv"

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Post URL",
            "Post Date",
            "Caption",
            "ImgBB Link",
            "Likes",
            "Comment Count",
            "All Comments",
        ])
        for row in rows:
            # Format comments as "username: text | username: text | ..."
            comments_str = " | ".join(
                f"@{c['username']}: {c['text']}" for c in row["comments"]
            )
            writer.writerow([
                row["post_url"],
                row["post_date"],
                row["caption"],
                row["imgbb_url"],
                row["likes"],
                row["comment_count"],
                comments_str,
            ])

    return csv_path


def main():
    parser = argparse.ArgumentParser(description="Scrape Instagram posts to CSV")
    parser.add_argument("username", help="Instagram username to scrape")
    parser.add_argument("--count", type=int, default=5, help="Number of posts (default: 5)")
    args = parser.parse_args()

    # 1. Download posts
    posts = download_posts(args.username, args.count)
    print(f"Downloaded {len(posts)} posts.")

    # 2. Setup Instagram session for API calls
    session = get_instagram_session()

    rows = []
    for i, post in enumerate(posts):
        meta = post["meta"]
        shortcode = meta.get("post_shortcode") or meta.get("shortcode", "")
        post_url = meta.get("post_url", f"https://www.instagram.com/p/{shortcode}/")
        print(f"\n[{i+1}/{len(posts)}] {post_url}")

        # 3. Upload to ImgBB
        print(f"  Uploading to ImgBB...")
        imgbb_url = upload_to_imgbb(post["image_path"])
        if imgbb_url:
            print(f"  ImgBB: {imgbb_url}")

        # Upload extra carousel images too
        extra_urls = []
        for extra_img in post.get("extra_images", []):
            url = upload_to_imgbb(extra_img)
            if url:
                extra_urls.append(url)
        all_imgbb = " , ".join([imgbb_url] + extra_urls) if extra_urls else imgbb_url

        # 4. Fetch comments
        print(f"  Fetching comments...")
        comment_count, comments = fetch_comments(session, shortcode)
        print(f"  Comments: {comment_count}, Likes: {meta.get('likes', 'N/A')}")

        rows.append({
            "post_url": post_url,
            "post_date": meta.get("post_date", ""),
            "caption": meta.get("description", ""),
            "imgbb_url": all_imgbb,
            "likes": meta.get("likes", "N/A"),
            "comment_count": comment_count,
            "comments": comments,
        })

        time.sleep(1)  # Rate limit between posts

    # 5. Write CSV
    csv_path = write_csv(args.username, rows)
    print(f"\nCSV saved to: {csv_path}")


if __name__ == "__main__":
    main()
