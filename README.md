# World in Words

Daily English-learning notes generated from BBC World Service's **What in the World** podcast.

## How it works

On weekdays, GitHub Actions reads the official BBC RSS feed, processes the newest unseen episode,
transcribes its audio with OpenAI, generates Traditional Chinese learning notes, and deploys the
static site to GitHub Pages. Audio and full transcripts are not committed to the repository.
When Spotify's public show page has an exact title match for the newest episode, the published notes
also include a direct Spotify episode link. A failed or mismatched Spotify lookup does not stop the update.

Each episode contains basic, intermediate, and advanced study sets. Every set has 10 vocabulary words
and up to 5 genuinely useful phrases, sorted by CEFR level; the site opens on the advanced set. Learning
entries use canonical forms while preserving one exact transcript sentence and the model-selected highlight.
All generated Chinese is normalized to Taiwan Traditional Chinese before publishing.

## Setup

1. In the GitHub repository, open **Settings → Secrets and variables → Actions**.
2. Create a repository secret named `OPENAI_API_KEY`.
3. Open **Settings → Pages** and select **GitHub Actions** as the deployment source.
4. Run **Actions → Update daily podcast → Run workflow** once.

The default feed is `https://podcasts.files.bbci.co.uk/w13xtvrv.rss`. The update runs at 08:00
Asia/Taipei, Monday through Friday. Both can be changed in the workflow or with the
`PODCAST_FEED_URL` environment variable.

The workflow transcribes the complete episode. Manual runs reprocess the latest episode; scheduled
runs only process newly published episodes. Pushing code does not trigger podcast processing.

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
