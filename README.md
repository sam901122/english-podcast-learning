# World in Words

Daily English-learning notes generated from BBC World Service's **What in the World** podcast.

## How it works

On weekdays, GitHub Actions reads the official BBC RSS feed, processes the newest unseen episode,
transcribes its audio with OpenAI, generates Traditional Chinese learning notes, and deploys the
static site to GitHub Pages. Audio and full transcripts are not committed to the repository.

## Setup

1. In the GitHub repository, open **Settings → Secrets and variables → Actions**.
2. Create a repository secret named `OPENAI_API_KEY`.
3. Open **Settings → Pages** and select **GitHub Actions** as the deployment source.
4. Run **Actions → Update daily podcast → Run workflow** once.

The default feed is `https://podcasts.files.bbci.co.uk/w13xtvrv.rss`. The update runs at 22:30
Asia/Taipei, Monday through Friday. Both can be changed in the workflow or with the
`PODCAST_FEED_URL` environment variable.

During initial testing, the workflow sets `TRANSCRIPTION_MAX_SECONDS=20`, so only the first 20
seconds are sent for transcription. Remove that environment variable to process full episodes.

## Local feed check

```powershell
python -m pip install -r requirements.txt
python scripts/update_podcast.py --dry-run
```

To run the complete process locally, set `OPENAI_API_KEY` in the environment and omit `--dry-run`.

## Attribution

This is an independent educational project and is not affiliated with the BBC. Podcast content
belongs to the BBC. The site links listeners to the official BBC episode pages and does not host
podcast audio or publish full transcripts.
