# Instagram Post Scraper

Scrapes posts from any public Instagram account, uploads images to ImgBB, and saves everything to a CSV.

## What it does

For each post it collects:
- Image (uploaded to ImgBB, link saved)
- Likes count
- Comment count
- All comments (username + text)
- Caption
- Post date and URL

## Setup (one time)

```bash
cd ~/projects/insta-scraper
source venv/bin/activate
```

You must be logged into Instagram in Chrome. The script reads your browser cookies — it does not store or share your credentials.

## Usage

```bash
source ~/projects/insta-scraper/venv/bin/activate
python3 ~/projects/insta-scraper/scrape.py <username> --count <number>
```

### Examples

Scrape last 5 posts from an account:
```bash
python3 ~/projects/insta-scraper/scrape.py mememandir --count 5
```

Scrape last 10 posts:
```bash
python3 ~/projects/insta-scraper/scrape.py mememandir --count 10
```

Different account:
```bash
python3 ~/projects/insta-scraper/scrape.py therock --count 3
```

## Output

Each run creates a timestamped CSV in:
```
~/projects/insta-scraper/output/<username>_YYYYMMDD_HHMMSS.csv
```

### CSV columns

| Column | Description |
|---|---|
| Post URL | Link to the Instagram post |
| Post Date | When it was posted |
| Caption | Post caption text |
| ImgBB Link | Uploaded image URL (multiple links for carousels) |
| Likes | Number of likes |
| Comment Count | Total number of comments |
| All Comments | All comments formatted as `@user: text \| @user: text` |

## How it works

1. Uses **gallery-dl** to download post images + metadata via your Chrome cookies
2. Uploads each image to **ImgBB** (free image hosting)
3. Fetches comments via Instagram's GraphQL API (using your Chrome cookies)
4. Writes everything to a CSV file

## Notes

- Only works with public accounts (or private accounts you follow)
- You must be logged into Instagram in Chrome
- Has a 1 second delay between posts to avoid rate limiting
- Carousel posts get all images uploaded, links comma-separated in one cell
