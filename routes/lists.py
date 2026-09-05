"""Managing vocabulary lists from the browser.

Lets a parent add this week's spelling words by pasting them or uploading a
text file, instead of needing shell access to the server.
"""
from flask import (
    Blueprint, current_app, flash, redirect, render_template, request, url_for,
)

import wordlists

bp = Blueprint("lists", __name__, url_prefix="/lists")

# Uploaded text is parsed, never executed or rendered raw, so the extension
# check is a helpful nudge rather than a security control.
ALLOWED_EXTENSIONS = (".txt", ".text", ".csv")


def _uploaded_text(storage):
    """Decode an uploaded file, or raise ListError with a readable message."""
    filename = (storage.filename or "").lower()
    if not filename.endswith(ALLOWED_EXTENSIONS):
        raise wordlists.ListError("Please upload a plain text (.txt) file.")

    raw = storage.read(current_app.config["MAX_CONTENT_LENGTH"] + 1)
    if len(raw) > current_app.config["MAX_CONTENT_LENGTH"]:
        raise wordlists.ListError("That file is too big for a word list.")

    # A list pasted out of Word or exported from a spreadsheet can carry odd
    # bytes; replace them rather than refusing the whole file.
    return raw.decode("utf-8", errors="replace")


@bp.get("")
def manage():
    return render_template("lists.html", word_lists=wordlists.available_lists())


@bp.post("")
def save():
    name = request.form.get("name", "")
    text = request.form.get("words", "")

    upload = request.files.get("file")
    try:
        if upload and upload.filename:
            text = _uploaded_text(upload)
            # An unnamed upload falls back to its own filename for the title.
            if not name.strip():
                name = upload.filename.rsplit(".", 1)[0]

        result = wordlists.save_list(name, text)
    except wordlists.ListError as exc:
        flash(str(exc), "error")
        return redirect(url_for("lists.manage"))

    message = "{} {} with {} word{}.".format(
        "Replaced" if result["replaced"] else "Saved",
        result["name"],
        result["count"],
        "" if result["count"] == 1 else "s",
    )
    if result["skipped"]:
        message += " Skipped {} entr{} that weren't 3-12 letter words.".format(
            result["skipped"], "y" if result["skipped"] == 1 else "ies"
        )

    flash(message, "success")
    return redirect(url_for("lists.manage"))


@bp.post("/<slug>/delete")
def delete(slug):
    if wordlists.delete_list(slug):
        flash("Deleted that list. Past scores keep its name.", "success")
    else:
        flash("That list no longer exists.", "error")
    return redirect(url_for("lists.manage"))
