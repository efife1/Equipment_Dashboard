# Future work — planned enhancements

Not urgent, not blocking fabrication or deployment. Revisit during the
next build session. See `docs/OPEN_ITEMS.md` for hardware items that
*do* need to be resolved before fabrication — this file is for
software/dashboard features to add later.

## Dashboard card rearranging

Let the user drag-and-drop cards on the dashboard to arrange them in
whatever order they want (rather than the fixed/registry order they
show up in today).

**Planned approach:**
- Drag-and-drop reordering on the dashboard grid; position tracked in
  frontend state while dragging (no live-save on every move).
- Explicit **"Save Layout" button** to commit the current arrangement —
  avoids accidental saves from a stray drag, and pairs naturally with a
  "Reset to default" option.
- On page load: check for a saved layout and apply it; fall back to
  default (registry) order if none exists.

**Storage location — still to decide, depends on usage pattern:**
- **Client-side (localStorage):** simplest to build. Persists across
  new tabs/windows and browser restarts on the *same* browser/device.
  Resets only on cleared browser data, incognito mode, or a different
  browser/device. Good fit if the dashboard is mainly viewed from one
  shared screen (e.g. a wall-mounted monitor).
- **Server-side (`registry.py` or a new small JSON store):** layout
  follows the dashboard regardless of which browser/device views it.
  Better fit if multiple people check the dashboard from their own
  laptops/phones and expect a consistent arrangement. More backend work
  (new endpoint + storage), but consistent with the existing
  atomic-JSON-write pattern already used in `registry.py`.

Decision on client vs. server storage to be made at build time based on
how the dashboard is actually being used/viewed by then.
