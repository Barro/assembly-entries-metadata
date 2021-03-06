#!/usr/bin/env python3

import argparse
import asmmetadata
import http.cookiejar
import json
import os
import re
import sys
import urllib.request


def fetch_data(cookie_jar):
    jar = http.cookiejar.MozillaCookieJar(cookie_jar)
    jar.load()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    request_entry = opener.open("https://scene.assembly.org/api/v1/entry/?format=json")
    entries = json.loads(request_entry.read())
    request_playlist = opener.open("https://scene.assembly.org/api/v1/playlist/?format=json")
    playlists = json.loads(request_playlist.read())
    return entries, playlists


def update_section_partyman_data(section, partyman_competitions):
    slug = section.get("partyman-slug")
    competition_meta = None
    entries = None
    for partyman_competition in partyman_competitions:
        if partyman_competition["competition"]["slug"] == slug:
            competition_meta = partyman_competition["competition"]
            entries = partyman_competition["entries"]
            break
    if entries is None:
        raise RuntimeError("Missing partyman data for slug %r" % slug)

    section_entries = []
    for partyman_entry in entries:
        entry_entry = partyman_entry["entry"]
        existing_data = None
        for metadata_entry in section['entries']:
            try:
                uuid = int(metadata_entry.get('partyman-id'))
            except:
                uuid = metadata_entry.get('partyman-id')
            if (partyman_entry['pk'] == uuid or entry_entry["uuid"] == uuid):
                existing_data = metadata_entry
                break
        addable_data = existing_data
        if existing_data is None:
            addable_data = {'section': section}
        addable_data['partyman-id'] = entry_entry['uuid']
        title = entry_entry['title']
        title = title.replace("|", "-")
        addable_data['title'] = title
        author = entry_entry.get("by")
        if not author:
            author = "author-will-be-revealed-after-compo"
        author = author.replace("|", "-")
        addable_data['author'] = author
        slide_info = entry_entry.get("slide_info")
        if slide_info:
             slide_info = slide_info.strip()
             slide_info = slide_info.replace("&", "&amp;")
             slide_info = slide_info.replace("<", "&lt;")
             slide_info = slide_info.replace("\r", "")
             slide_info = re.sub("\n+", "\n", slide_info)
             slide_info = slide_info.replace("\n", "<br/>")
             slide_info = slide_info.replace("|", "-")
             addable_data["techniques"] = slide_info
        elif "techniques" in addable_data:
            del addable_data["techniques"]
        # preview_youtube_url = partyman_entry.get("preview", "")
        # youtube_id = None
        # if preview_youtube_url:
        #     youtube_id = asmyoutube.get_video_id_try_url(preview_youtube_url)
        # if youtube_id:
        #     addable_data["youtube"] = youtube_id
        section_entries.append(addable_data)
    section["entries"] = section_entries
    return section


def fetch_update_data(metadata_file, cookie_jar):
    entries, playlists = fetch_data(cookie_jar)
    metadata = asmmetadata.parse_file(metadata_file)

    metadata_partyman_slugs = []
    for section in metadata.sections:
        slug = section.get("partyman-slug")
        if slug is None:
            continue
        update_section_partyman_data(section, playlists)

    with open(metadata_file.name, "w") as fp:
        asmmetadata.print_metadata(fp, metadata)


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('metadata_file', type=argparse.FileType("r"))
    parser.add_argument('cookie_jar')
    args = parser.parse_args(argv[1:])
    fetch_update_data(args.metadata_file, args.cookie_jar)

    return os.EX_OK

if __name__ == "__main__":
    sys.exit(main(sys.argv))
