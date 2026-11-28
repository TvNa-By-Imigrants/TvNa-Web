#!/usr/bin/env python3
"""Stage 5d: add photos to a new place (after stage 5c), remove a wrong one, or change the order.
A place needs 1 to 5 photos to be published; photo 1 is the main one. Each photo is checked (20 MB at most,
at least 600 px on each side, not the same picture twice), made a 1200 px JPG without EXIF (no GPS), put on
Cloudinary as tvna/places/<place_id>-<code>, and saved in data/places/<place_id>.json with its source and credit.
Sources: "Google Maps", "Shop's own page", "Own photo", or "Other: <where>". credit = who took or posted it.

Usage:
    python stage5d_add_photo.py tvna_p_0001 front.jpg "https://lh3.googleusercontent.com/..." --source "Google Maps" --credit "Dara S."
    python stage5d_add_photo.py tvna_p_0001 --remove 2
    python stage5d_add_photo.py tvna_p_0001 --move 3 --to 1
"""
import argparse
import sys
from pathlib import Path

from tvna_common import PLACES_DIR
from tvna_review import MAX_PHOTOS, PhotoError, add_photo, move_photo, peek_photo, photos_of, read_place, remove_photo, text


def show_photos(place_id: str, folder: Path) -> int:
    """Print the place's photos in order, so nobody has to run --move or --remove again to check."""
    photos = photos_of(read_place(place_id, folder)[2])
    print(text("photo.count", place_id=place_id, count=len(photos), max=MAX_PHOTOS))
    for number, photo in enumerate(photos, 1):
        photo = photo if isinstance(photo, dict) else {"url": photo}
        print(text("photo.list_line", number=number, credit=photo.get("credit"), source=photo.get("source"),
                   url=photo.get("url")))
    return len(photos)


def asked_yes(question: str) -> bool:
    try:
        return input(question).strip().lower() == "yes"
    except EOFError:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("place_id", help="e.g. tvna_p_0001 (stage 5c and stage5d_check_photos.py list them)")
    ap.add_argument("images", nargs="*", help="photo files or image links")
    ap.add_argument("--source", help='"Google Maps", "Shop\'s own page", "Own photo" or "Other: <where>"')
    ap.add_argument("--credit", help="who took or posted the photo")
    ap.add_argument("--remove", type=int, metavar="N", help="remove photo N")
    ap.add_argument("--yes", action="store_true", help="with --remove: don't ask first")
    ap.add_argument("--move", type=int, metavar="N", help="move photo N ...")
    ap.add_argument("--to", type=int, metavar="M", help="... to position M (1 = the main photo)")
    ap.add_argument("--places-dir", type=Path, default=PLACES_DIR)
    args = ap.parse_args()
    actions = [bool(args.images), args.remove is not None, args.move is not None]
    if sum(actions) != 1 or (args.move is not None) != (args.to is not None):
        ap.error("give photos to add, or --remove N, or --move N --to M (one at a time)")

    try:
        if args.remove is not None:
            photo = peek_photo(args.place_id, args.remove, args.places_dir)
            ask = text("photo.remove_ask", number=args.remove, place_id=args.place_id, url=photo.get("url"),
                       credit=photo.get("credit"))
            if not args.yes and not asked_yes(ask):
                print(text("photo.remove_kept"))
                return
            removed = remove_photo(args.place_id, args.remove, args.places_dir)
            print(text("photo.removed", place_id=args.place_id, number=args.remove, url=removed.get("url")))
        elif args.move is not None:
            move_photo(args.place_id, args.move, args.to, args.places_dir)
            print(text("photo.moved", place_id=args.place_id, number=args.move, to=args.to))
        else:
            read_place(args.place_id, args.places_dir)  # a wrong id stops here, before any download
    except PhotoError as e:
        sys.exit(text("cli.error", reason=e))

    failed = 0
    for image in args.images:
        try:
            add_photo(args.place_id, image, args.source, args.credit, args.places_dir)
            count = len(photos_of(read_place(args.place_id, args.places_dir)[2]))
            print(text("photo.added", place_id=args.place_id, number=count, source=args.source.strip(),
                       credit=args.credit.strip()))
        except PhotoError as e:
            failed += 1
            print(text("cli.failed", place_id=args.place_id, image=image, reason=e))
    if len(args.images) > 1:
        print(text("cli.summary", added=len(args.images) - failed, failed=failed))
    try:
        count = show_photos(args.place_id, args.places_dir)
    except PhotoError as e:
        sys.exit(text("cli.error", reason=e))
    print(text("cli.next_more", need=1) if count == 0 else text("cli.next_check"))
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
