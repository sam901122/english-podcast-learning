# Learning material audit: October 5–14, 2026

Dates use Asia/Taipei. Compared the local episode index and detail files against the official BBC RSS feed: https://podcasts.files.bbci.co.uk/w13xtvrv.rss

Seven episodes were published in this window. The four initially missing episodes have now been backfilled, so all seven have learning materials. No episodes appear in the feed for October 10–11 or October 14 at the time of checking. Audio URLs below are the exact RSS enclosure URLs. All four recordings were downloaded and transcribed locally.

| Date | Backfilled episode | Official page | Audio |
| --- | --- | --- | --- |
| 2026-10-05 | Why are so many students protesting in France? | [BBC](http://www.bbc.co.uk/programmes/w3ct98y2) | [MP3](http://open.live.bbc.co.uk/mediaselector/6/redir/version/2.0/mediaset/audio-nondrm-download-rss/proto/http/vpid/p0pf36y4.mp3) |
| 2026-10-07 | Are online gig spoilers ruining live music? | [BBC](http://www.bbc.co.uk/programmes/w3ct992l) | [MP3](http://open.live.bbc.co.uk/mediaselector/6/redir/version/2.0/mediaset/audio-nondrm-download-rss/proto/http/vpid/p0pfdwkv.mp3) |
| 2026-10-08 | Everyone is talking about the "great lock-in" | [BBC](http://www.bbc.co.uk/programmes/w3ct994v) | [MP3](http://open.live.bbc.co.uk/mediaselector/6/redir/version/2.0/mediaset/audio-nondrm-download-rss/proto/http/vpid/p0pfmws8.mp3) |
| 2026-10-12 | The AI influencer who had lots of us fooled | [BBC](http://www.bbc.co.uk/programmes/w3ct98y3) | [MP3](http://open.live.bbc.co.uk/mediaselector/6/redir/version/2.0/mediaset/audio-nondrm-download-rss/proto/http/vpid/p0pg96v8.mp3) |

Previously present materials: October 6, October 9, October 13.

Codex authored the summaries and study content directly, without calling an AI API. Audio transcription ran locally with faster-whisper 1.1.1 and the small.en model. Selected transcript examples were reviewed for known names, transcription punctuation, fillers, and stutters. Temporary audio, transcripts, model files, downloads, and one-off scripts were removed after validation.

The backfill used the existing pipeline functions for ad removal, summaries and the three study sets, dictionary-form preparation, topic duplicate filtering, validation, and saving. Static, directly authored responses replaced the API responses. The existing daily pipeline source was not changed by this backfill.

| Date | Learning material | Practical words / phrases | Advanced words / phrases | Topic words |
| --- | --- | --- | --- | --- |
| October 5 | [French student protests](../site/data/episodes/936c12ec37676961.json) | 10 / 5 | 10 / 5 | 8 |
| October 7 | [Concert spoilers](../site/data/episodes/a68081cb6b071954.json) | 10 / 5 | 10 / 5 | 7 |
| October 8 | [Great lock-in](../site/data/episodes/2477ac429c39e6c4.json) | 10 / 5 | 10 / 5 | 4 |
| October 12 | [AI influencer](../site/data/episodes/3a73b42d28544b1e.json) | 10 / 5 | 10 / 5 | 4 |

Validation passed for all four files: expected schemas and item counts, source-sentence examples, exact highlights, allowed CEFR levels, summary prefix and Chinese/Latin spacing, topic duplicates, feed metadata, and matching date-sorted index entries. The 12 existing vocabulary-preparation tests also passed. Total new material: eight summaries, 103 vocabulary items, and 40 phrases.
