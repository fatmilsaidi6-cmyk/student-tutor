# Privacy & Safety

Study Buddy is designed to be **private by default** and is intended for use by
students from primary school through university. This document explains what
happens to the homework a student enters and what operators should consider
before making the app available to children.

## What the app stores

- **No accounts, no server-side database.** The backend does not persist
  homework, explanations, or any personal data.
- **History lives in the browser.** Solved problems, follow-up chats, and
  preferences are stored in the browser's `localStorage` on the student's own
  device. Clearing the browser data or using a private window removes them.
- **Uploaded files are processed in memory** and are not written to disk or kept
  after the response is returned.

## Where homework is sent

The engine chosen for a request determines who processes the text:

| Engine  | Where the homework goes |
| ------- | ----------------------- |
| `local` | A model running on **your own machine** (Ollama). Content never leaves the device. |
| `cloud` | The configured OpenRouter endpoint and the model provider behind it. |
| `auto`  | Cloud when a key is configured, otherwise local. |

- **Local mode is fully offline.** No text, image, or metadata is transmitted.
- **Cloud mode sends the homework text** (and, for photos/scans, the image) to
  OpenRouter and its upstream model provider. Those requests are subject to that
  provider's terms and data-retention policy. Do not enable cloud mode for
  content that must not leave your infrastructure.

## Recommendations for operators serving children

If you deploy this for minors, you are the data controller and should:

- **Prefer local mode** so no student content leaves your device or network.
- **Obtain guardian consent** where required (e.g. COPPA in the US, GDPR-K in
  the EU, and equivalent local rules).
- **Avoid uploading identifiable content** — photos can capture faces, names,
  school badges, or handwriting that identifies a child.
- **Set an access code** (`API_KEY`) and rate limits before exposing the service
  publicly, so it can't be abused or used to drain a paid API key.
- **Publish your own privacy notice** describing retention, the model provider
  you use, and how to request deletion if you add any logging.

## File handling safeguards

Uploads are treated as untrusted: file size, file count, image pixel count
(decompression-bomb guard), and PDF page count are all capped, and the AI
endpoints are rate-limited. See `README.md` for the specific limits and the
environment variables that control them.

## Contact

For questions about this deployment, contact the operator who hosts it.
