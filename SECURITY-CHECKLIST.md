# Security checklist

What must be true before you submit. *How* to make each one true is your work —
that is the point of the tickets.

| # | Must be true | How the grader checks it |
|---|---|---|
| 1 | Stored passwords are argon2 hashes | Reads the seeded database and looks at the stored value |
| 2 | Wrong passwords are refused, and the message does not reveal whether the account exists | Tries a bad password |
| 3 | Every state-changing form (POST) carries a CSRF token and rejects a request without one | Replays each POST with the token removed |
| 4 | An editor cannot reach any admin-only route | Logs in as the seeded editor and requests each admin route |
| 5 | An anonymous visitor is redirected to login, never shown admin content | Requests admin routes with no session |
| 6 | A deactivated user cannot log in | Deactivates the seeded editor, then tries to log in |
| 7 | User-written Markdown cannot inject scripts | Saves a post containing `<script>` and an `onerror=` attribute, publishes, and checks both the preview and the export |
| 8 | Drafts never appear in `site/` or on the public site | Publishes with a draft present and searches the output |
| 9 | No secrets, databases, or `.env` files in git history | Greps the full history |
| 10 | Access control is enforced in code, not by hiding links | Requests admin URLs directly rather than clicking |

Rule of thumb: if the only thing stopping an editor from reaching a page is that
the link is hidden, it is not stopping anyone.
