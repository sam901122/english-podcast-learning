# World in Words

Daily English-learning notes generated from BBC World Service's **What in the World** podcast.

## How it works

On weekdays, GitHub Actions reads the official BBC RSS feed, processes the newest unseen episode,
uses Gemini to transcribe its audio and generate Traditional Chinese learning notes, then deploys the
static site to GitHub Pages. Audio and full transcripts are not committed to the repository.

## Setup

1. In the GitHub repository, open **Settings → Secrets and variables → Actions**.
2. Create a repository secret named `GEMINI_API_KEY`.
3. Open **Settings → Pages** and select **GitHub Actions** as the deployment source.
4. Run **Actions → Update daily podcast → Run workflow** once.

The default feed is `https://podcasts.files.bbci.co.uk/w13xtvrv.rss`. The update runs at 08:00
Asia/Taipei, Tuesday through Saturday. Both can be changed in the workflow or with the
`PODCAST_FEED_URL` environment variable.

The workflow transcribes the complete episode. Manual runs reprocess the latest episode; scheduled
runs only process newly published episodes. Pushing code does not trigger podcast processing.

## Local feed check

```powershell
python -m pip install -r requirements.txt
python scripts/update_podcast.py --dry-run
```

To run the complete process locally, put `GEMINI_API_KEY=...` in a local `.env` file and omit
`--dry-run`. To deliberately rebuild a particular RSS item, pass its zero-based position, for example
`--episode-offset 0` for the newest episode.

## Attribution

This is an independent educational project and is not affiliated with the BBC. Podcast content
belongs to the BBC. The site links listeners to the official BBC episode pages and does not host
podcast audio or publish full transcripts.
