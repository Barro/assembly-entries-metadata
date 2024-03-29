#!/usr/bin/env python3

import argparse
import asmmetadata
import base64
import collections
import dataclasses
import datetime
import hashlib
import html
import io
import json
import logging
import os.path
import PIL.Image  # type: ignore
import pytz
import subprocess
import sys
import tarfile
import typing
import time
import urllib
import urllib.parse

JsonDict = typing.Dict[str, typing.Optional[typing.Any]]

CURRENT_TIME = time.strftime("%Y-%m-%d %H:%M:%S")

DEFAULT_THUMBNAIL_SIZE = "160w"
EXTRA_THUMBNAIL_WIDTHS = ["%dw" % x for x in (
    160 * 1.25, 160 * 1.5, 160 * 2, 160 * 3, 160 * 4)]

DEFAULT_IMAGE_SIZE = "640w"
EXTRA_IMAGE_WIDTHS = ["%dw" % x for x in (
    640 * 1.25, 640 * 1.5, 640 * 2, 640 * 3, 640 * 4)]

parser = argparse.ArgumentParser()
parser.add_argument("datafile", type=argparse.FileType("r"))
parser.add_argument("files_root", metavar="files-root")
parser.add_argument(
    "--no-empty", dest="noempty", action="store_true",
    help="Prevent empty sections from going to import data.")
parser.add_argument(
    "--pms-vote-template",
    default="https://pms.assembly.org/asmxx/compos/%s/vote/")
parser.add_argument("--only-sections", default="")
parser.add_argument("-o", "--outfile")

args = parser.parse_args()
FILEROOT = args.files_root

create_empty_sections = not args.noempty

ExternalLinksSection = collections.namedtuple(
    "ExternalLinksSection", ["name", "links"])


class ExternalLinks:
    sections: typing.List[asmmetadata.Section]

    def __init__(self) -> None:
        self.sections = []

    def add(
            self,
            section_name: str,
            contents: str,
            href: str,
            notes: str=""
    ) -> None:
        for section in self.sections:
            if section["name"] == section_name:
                section["links"].append({
                    "href": href,
                    "contents": contents,
                    "notes": notes,
                })
                return
        self.sections.append({
            "name": section_name,
            "links": [{
                "href": href,
                "contents": contents,
                "notes": notes,
                }]
        })


def add_to_tar(tar: tarfile.TarFile, filename: str, data: bytes) -> None:
    data_str = data
    info = tarfile.TarInfo(filename)
    info.size = len(data_str)
    # 2000-01-01 00:00:00
    info.mtime = 946677600
    info.mode = 0o644
    tar.addfile(info, io.BytesIO(data_str))


def json_dumps(data: JsonDict) -> bytes:
    return json.dumps(
        data, sort_keys=True, indent=2, separators=(',', ': ')).encode("utf-8")


def select_smaller_thumbnail(fileprefix: str) -> typing.Tuple[typing.Optional[bytes], typing.Optional[str]]:
    if not os.path.isfile(fileprefix + ".jpeg"):
        return None, None
    if not os.path.isfile(fileprefix + ".png"):
        return None, None
    thumbnail_jpeg = open(fileprefix + ".jpeg", "rb").read()
    thumbnail_png = open(fileprefix + ".png", "rb").read()

    if len(thumbnail_jpeg) < len(thumbnail_png):
        return thumbnail_jpeg, 'jpeg'
    else:
        return thumbnail_png, 'png'


def generate_section_description(
        section_data: asmmetadata.Section,
        pms_path_template: str) -> str:
    description = ''
    if 'description' in section:
        description += section['description']
        if section.get('ongoing', False) is True:
            description += "<p>You can vote these entries at <a href'https://scene.assembly.org/'>scene.assembly.org</a>!</p>"
    if 'youtube-playlist' in section:
        description += """<p><a href="https://www.youtube.com/playlist?list=%s">Youtube playlist of these entries</a></p>""" % section['youtube-playlist']
    return description


def get_image_size(data: bytes) -> JsonDict:
    image = PIL.Image.open(io.BytesIO(data))
    x, y = image.size
    return {"x": x, "y": y}


def meta_year_file(sections: typing.List[asmmetadata.Section]) -> typing.Tuple[str, JsonDict]:
    section_keys = [section["key"] for section in sections]
    return "meta.json", {
        "sections": section_keys,
    }


def meta_section_file(
        section: asmmetadata.Section,
        included_entries: typing.List[asmmetadata.Entry],
        description: str,
) -> typing.Tuple[str, JsonDict]:
    normalized_section = section['key']
    entry_keys = []
    for entry in included_entries:
        entry_key = asmmetadata.normalize_key(
            asmmetadata.get_entry_name(entry))
        entry_keys.append(entry_key)

    return "%s/meta.json" % (normalized_section), {
        "name": section["name"],
        "description": description,
        "is-ranked": section.get('ranked', True),
        "is-ongoing": section.get('ongoing', False),
        "entries": entry_keys,
    }


def get_thumbnail_data(
        entry: asmmetadata.Entry,
        size: str,
) -> typing.Tuple[typing.Optional[bytes], typing.Optional[str]]:
    thumbnail_base = asmmetadata.select_thumbnail_base(entry)
    thumbnail = None
    if thumbnail_base is not None:
        thumbnail, suffix = select_smaller_thumbnail(
            os.path.join(FILEROOT, thumbnail_base + "-" + size))
        if thumbnail is None:
            thumbnail, suffix = select_smaller_thumbnail(
                os.path.join(FILEROOT, thumbnail_base))
    else:
        # We don't have any displayable data.
        return None, None

    if thumbnail is None:
        del entry['section']
        sys.stderr.write("Missing thumbnail for %s!\n" % str(entry))
        sys.exit(1)

    return thumbnail, suffix


def get_image(
        filename_archive_prefix: str,
        image_base: str,
        extra_prefix: str="") -> typing.Tuple[
            typing.Optional[bytes],
            typing.Optional[JsonDict]]:
    viewfile, postfix = select_smaller_thumbnail(
        os.path.join(FILEROOT, image_base))
    if viewfile is None:
        return None, None

    base = os.path.basename(image_base)
    image_filename = os.path.basename(
        "%s%s.%s" % (filename_archive_prefix, base, postfix))
    return viewfile, {
        "filename": extra_prefix + image_filename,
        "size": get_image_size(viewfile),
        "checksum": calculate_checksum(viewfile),
        "type": "image/%s" % postfix,
    }


def get_images(
        archive_dir: str,
        filename_prefix: str,
        image_base: str,
        default_size: str,
        extra_sizes: typing.List[str],
        extra_prefix: str="") -> typing.Tuple[
            typing.List[typing.Tuple[str, bytes]],
            JsonDict]:
    files = []
    result: JsonDict = {}
    default_file, default_data = get_image(
        filename_prefix, "%s-%s" % (image_base, default_size), extra_prefix)
    if default_file is None:
        default_file, default_data = get_image(
            filename_prefix, image_base, extra_prefix)
    if default_file is None:
        raise RuntimeError("No image for base %s" % image_base)
    assert default_data is not None
    default_filename = default_data["filename"]
    assert default_filename is not None
    filename = "%s/%s" % (
        archive_dir, os.path.basename(default_filename))
    files.append((filename, default_file))
    result["default"] = default_data
    result_sources = [default_data]
    for extra_size in extra_sizes:
        filename_base = "%s-%s" % (image_base, extra_size)
        extra_file, extra_data = get_image(
            filename_prefix, filename_base, extra_prefix)
        if extra_file is None:
            continue
        assert extra_data is not None
        image_path = extra_data["filename"]
        assert image_path is not None
        filename = "%s/%s" % (
            archive_dir, os.path.basename(image_path))
        files.append((filename, extra_file))
        result_sources.append(extra_data)
    result["sources"] = result_sources
    return files, result


PositionDescriptor = typing.Callable[
    [asmmetadata.Entry, typing.Optional[str]],
    str]

def entry_position_description_factory(
        pms_vote_template: str) -> PositionDescriptor:
    def generator(
            entry: asmmetadata.Entry,
            position_str: typing.Optional[str]) -> str:
        if not entry["section"].get("ranked", True):
            return ""
        description = ""
        if entry['section'].get('ongoing', False) is False:
            if position_str is not None:
                description += u"%s" % position_str
            else:
                description += u"Not qualified to be shown on the big screen"
            description += u".</p>\n<p>\n"
        else:
            description += "<p>You can vote this entry at <a href='https://scene.assembly.org/'>scene.assembly.org</a>!</p>"
        return description
    return generator


def calculate_checksum(data: bytes) -> str:
    m = hashlib.sha256()
    m.update(data)
    return base64.urlsafe_b64encode(m.digest())[:8].decode("utf-8")


def meta_entry(
        outfile: tarfile.TarFile,
        year: int,
        entry: asmmetadata.Entry,
        description_generator: PositionDescriptor,
        music_thumbnails: typing.Optional[typing.Any]
) -> typing.Optional[typing.Tuple[str, JsonDict]]:
    title = entry['title']
    author = entry.get('author', "author-will-be-revealed-later")
    section_name = entry['section']['name']
    name = asmmetadata.get_entry_name(entry)

    asset = None

    normalized_name = asmmetadata.normalize_key(
        asmmetadata.get_entry_name(entry))
    normalized_section = asmmetadata.normalize_key(section_name)

    external_links = ExternalLinks()
    locations = ""

    description = u""
    if 'warning' in entry:
        description += u"%s</p>\n<p>" % html.escape(entry['warning'])

    placement = None
    placement_str = None
    if entry["section"].get("ranked", True):
        placement = entry.get('position', -1)
        if placement != -1:
            placement_str = str(placement) + asmmetadata.get_ordinal_suffix(placement) + " place"

    has_media = False

    display_author = None
    if "Misc" in section_name or "Photos" in section_name:
        pass
    elif not "AssemblyTV" in section_name and not "Winter" in section_name:
        display_author = author
        if not "Seminars" in section_name:
            description += description_generator(entry, placement_str)

    if 'description' in entry:
        description += f"{entry['description']}</p>\n<p>"

    if 'platform' in entry:
        description += "Platform: %s</p>\n<p>" % html.escape(entry['platform'])

    if 'techniques' in entry:
        description += "Notes: %s</p>\n<p>" % html.escape(entry['techniques'])

    if display_author is not None:
        description += (
            f"Author: <a " +
            "href=\"../../search?q=%s\" " % urllib.parse.quote_plus(display_author) +
            f"title=\"Do an approximate search on author's name from all entries\"" +
            ">%s</a>\n" % html.escape(display_author)
        )

    # Twitch embed does not work
    # if "twitch" in entry:
    #     twitch_id_time = asmmetadata.get_timed_twitch_id(entry)
    #     has_media = True
    #     external_links.add(
    #         "View on",
    #         "Twitch",
    #         "https://twitch.tv/videos/%s" % twitch_id_time)
    #     asset = {
    #         "type": "twitch",
    #         "data": {"id": twitch_id_time},
    #     }
    # Youtube is our primary location
    if "youtube" in entry:
        youtube_id_time = asmmetadata.get_timed_youtube_id(entry)
        has_media = True
        external_links.add(
            "View on",
            "YouTube",
            "https://www.youtube.com/watch?v=%s" % youtube_id_time)
        asset = {
            "type": "youtube",
            "data": {"id": youtube_id_time},
        }
    if entry.get('image-file') or entry.get('galleriafi'):
        image_file = entry.get('image-file')
        galleriafi_path = entry.get("galleriafi")
        if galleriafi_path:
            image_file = "%s/%s" % (
                normalized_section,
                asmmetadata.get_galleriafi_filename(galleriafi_path))
        if image_file is None:
            image_file = "%s/%s.jpeg" % (normalized_section, normalized_name)
        if asmmetadata.is_image(image_file):
            has_media = True
            _, baseprefix_r = image_file[::-1].split(".", 1)
            baseprefix = baseprefix_r[::-1]
            image_base = 'thumbnails/large/%s' % baseprefix
            archive_dir = "%s/%s" % (normalized_section, normalized_name)
            files, images_data = get_images(
                archive_dir,
                "asset-",
                image_base,
                DEFAULT_IMAGE_SIZE,
                EXTRA_IMAGE_WIDTHS)
            for filename, data in files:
                add_to_tar(outfile, filename, data)
            asset = {
                "type": "image",
                "data": images_data,
            }
            #locations += "<location type='image'>%s|%s</location>" % (image_filename, escape(name))

    webfile = entry.get('webfile')
    if webfile:
        if asmmetadata.is_image(webfile):
            has_media = True
            _, baseprefix_r = webfile[::-1].split(".", 1)
            baseprefix = baseprefix_r[::-1]
            viewfile, postfix = select_smaller_thumbnail(
                os.path.join(FILEROOT, 'thumbnails/large/%s' % baseprefix))
            if viewfile is None:
                logging.error(
                    "Image file %s did not have an expected thumbnail",
                    baseprefix)
                raise RuntimeError("No thumbnail for image file")
            viewfile_basename = "%s.%s" % (normalized_name, postfix)
            viewfile_filename = "%s/%s/%s" % (
                normalized_section, normalized_name, viewfile_basename)
            add_to_tar(outfile, viewfile_filename, viewfile)
            normal_prefix = asmmetadata.normalize_key(baseprefix)
            image_filename = "%s.%s" % (normal_prefix, postfix)
            asset = {
                "type": "image",
                "data": {
                    "default": {
                        "filename": viewfile_basename,
                        "size": get_image_size(viewfile),
                        "checksum": calculate_checksum(viewfile),
                        "type": "image/%s" % postfix,
                    }
                }
            }

            external_links.add(
                "Download",
                "Full resolution",
                "https://media.assembly.org/compo-media/assembly%d/%s" % (year, webfile),
                "(media.assembly.org)"
            )
            # locations += "<location type='download'>|Full resolution</location>" % ()
            # locations += "<location type='image'>%s|%s</location>" % (image_filename, escape(name))

        elif webfile.endswith(".mp3"):
            external_links.add(
                "Download",
                "MP3",
                "https://media.assembly.org/compo-media/assembly%d/%s" % (year, webfile),
                "(media.assembly.org")
            #locations += "<location type='download'>http://media.assembly.org/compo-media/assembly%d/%s|MP3</location>" % (year, webfile)

    pouet = entry.get('pouet')
    if pouet:
        external_links.add(
            "View on",
            "pouet.net",
            "https://www.pouet.net/prod.php?which=%s" % pouet)
        #locations += "<location type='pouet'>%s</location>" % (pouet)

    download = entry.get('download')
    if download:
        download_type = "Original"
        if "game" in section_name.lower():
            download_type = "Playable game"
        external_links.add(
            "Download",
            download_type,
            download,
            "(%s)" % urllib.parse.urlparse(download).netloc)
        #locations += "<location type='download'>%s|%s</location>" % (escape(download), download_type)

    sceneorg = entry.get('sceneorg')
    if sceneorg:
        download_type = "Original"
        if "game" in section_name.lower():
            download_type = "Playable game"
        if ";" in sceneorg:
            parts = sceneorg.split(";")
            i = 1
            for part in parts:
                external_links.add(
                    "Download",
                    "%s (%d/%d)" % (download_type, i, len(parts)),
                    "https://files.scene.org/view%s" % part,
                    "(files.scene.org)")

                # locations += "<location type='sceneorg'>%s|%s (%d/%d)</location>" % (
                #     escape(part), download_type, i, len(parts))
                i += 1
        else:
            external_links.add(
                "Download",
                "%s" % download_type,
                "https://files.scene.org/view%s" % sceneorg,
                "(files.scene.org)")
            #locations += "<location type='sceneorg'>%s|%s</location>" % (escape(sceneorg), download_type)

    sceneorgvideo = entry.get('sceneorgvideo')
    mediavideo = entry.get('media')
    if sceneorgvideo:
        external_links.add(
            "Download",
            "HQ video",
            "https://files.scene.org/view%s" % sceneorgvideo,
            "(files.scene.org)")
        #locations += "<location type='sceneorg'>%s|HQ video</location>" % (escape(sceneorgvideo))
    elif mediavideo:
        external_links.add(
            "Download",
            "HQ video",
            "https://media.assembly.org%s" % mediavideo,
            "(media.assembly.org)")
        #locations += "<location type='download'>http://media.assembly.org%s|HQ video</location>" % (mediavideo)

    galleriafi = entry.get("galleriafi")
    if galleriafi:
        external_links.add(
            "Download",
            "Original image",
            "https://assembly.galleria.fi%s" % galleriafi,
            "(assembly.galleria.fi)")
        #locations += "<location type='download'>http://assembly.galleria.fi%s|Original image</location>" % (galleriafi)

    if not has_media:
        return None

    has_thumbnail = False
    if entry.get('use-parent-thumbnail', False) is True:
        has_thumbnail = True
        thumbnails = music_thumbnails
    else:
        thumbnail_base = asmmetadata.select_thumbnail_base(entry)
        assert thumbnail_base is not None, entry
        archive_dir = "%s/%s" % (
            normalized_section, normalized_name)
        try:
            files, thumbnails = get_images(
                archive_dir,
                "thumb-",
                thumbnail_base,
                DEFAULT_THUMBNAIL_SIZE,
                EXTRA_THUMBNAIL_WIDTHS)
            for thumbnail_tar_filename, thumbnail_tar_data in files:
                add_to_tar(outfile, thumbnail_tar_filename, thumbnail_tar_data)
            has_thumbnail = True
        except Exception as e:
            logging.warning(
                "No thumbnail for %s: %s", thumbnail_base, e)

    if not has_thumbnail:
        return None

    tags = set()
    entry_tags = entry.get('tags')
    if entry_tags:
        tags.update(entry_tags.split(" "))

    metadata = {
        "year": year,
        "section": section_name,
        "title": title,
        "author": author,
        "asset": asset,
        "thumbnails": thumbnails,
        "description": description,
        "external-links": external_links.sections,
    }
    if placement is not None:
        metadata["placement"] = placement
    return "%s/%s/meta.json" % (normalized_section, normalized_name), metadata


tmp_outfile = args.outfile + ".tmp"
outfile = tarfile.TarFile.open(tmp_outfile, "w")
section_thumbnails = {}

now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)

included_sections = []
entry_data = asmmetadata.parse_file(args.datafile)

for section in entry_data.sections:
    if section.get('public', True) is False:
        continue
    if section.get('public-after', now) > now:
        continue
    if len(section['entries']) == 0 and not create_empty_sections:
        continue
    if len(args.only_sections) and section['key'] not in args.only_sections.split(","):
        continue
    included_sections.append(section)

    section_description = generate_section_description(
        section, args.pms_vote_template)

    sorted_entries = asmmetadata.sort_entries(section['entries'])
    section_thumbnail = section.get("section-thumbnail")

    section_thumbnails_meta = None
    if section_thumbnail:
        if section_thumbnail not in section_thumbnails:
            section_thumbnail_files, section_thumbnails_meta = get_images(
                ".",
                "",
                "thumbnails/%s" % section_thumbnail,
                DEFAULT_THUMBNAIL_SIZE,
                EXTRA_THUMBNAIL_WIDTHS,
                "../../")
            for thumbnail_tar_filename, data in section_thumbnail_files:
                add_to_tar(outfile, thumbnail_tar_filename, data)
            section_thumbnails[section_thumbnail] = section_thumbnails_meta
        section_thumbnails_meta = section_thumbnails[section_thumbnail]
        for entry in sorted_entries:
            entry['use-parent-thumbnail'] = True
    entry_position_descriptor = entry_position_description_factory(
        args.pms_vote_template)
    included_entries = []
    for entry in sorted_entries:
        entry_out = meta_entry(
            outfile,
            entry_data.year,
            entry,
            entry_position_descriptor,
            section_thumbnails_meta)
        if not entry_out:
            continue
        included_entries.append(entry)
        entry_filename, entry_metadata = entry_out
        add_to_tar(outfile, entry_filename, json_dumps(entry_metadata))

    entry_filename, entry_data_dict = meta_section_file(
        section,
        included_entries,
        section_description)
    tarfile_data = json_dumps(entry_data_dict)
    add_to_tar(outfile, entry_filename, tarfile_data)

year_filename, year_metadata = meta_year_file(included_sections)
add_to_tar(outfile, year_filename, json_dumps(year_metadata))
outfile.close()
with open(args.outfile, "wb") as out_tarball:
    subprocess.check_call(
        ["pigz", "--rsyncable", "--no-time", "--stdout", tmp_outfile],
        stdout=out_tarball)
os.remove(tmp_outfile)
