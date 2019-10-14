#!/bin/sh
# Updates the .po file for all languages from POTFILES.in,
# or just some specific ones.

set -e

update_pofiles () {
    for pofile in "$@"; do
        lang=$(basename "$pofile" .po)
        intltool-update -g mypaint --dist "$lang"
    done
}

if [ -n "$1" ]; then
    echo >&2 "Updating just \"$*\"..."
    update_pofiles "$@"
else
    echo >&2 "Updating *.po..."
    update_pofiles ./*.po
fi

