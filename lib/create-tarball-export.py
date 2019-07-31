#!/usr/bin/env python

import argparse
import asmmetadata
import base64
import collections
import datetime
import hashlib
import html
import io
import json
import os.path
import PIL.Image
import pytz
import sys
import tarfile
import time
import urllib

CURRENT_TIME = time.strftime("%Y-%m-%d %H:%M:%S")

parser = argparse.ArgumentParser()
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

ExternalLinksSection = collections.namedtuple("ExternalLinksSection", ["name", "links"])

class ExternalLinks:
    def __init__(self):
        self.sections = []

    def add(self, section_name, contents, href, notes=""):
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


def add_to_tar(tar, filename, data):
    data_str = data
    info = tarfile.TarInfo(filename)
    info.size = len(data_str)
    # 2000-01-01 00:00:00
    info.mtime = 946677600
    info.mode = 0o644
    tar.addfile(info, io.BytesIO(data_str))


def json_dumps(data):
    return json.dumps(
        data, sort_keys=True, indent=2, separators=(',', ': ')).encode("utf-8")


def display_asset(path, title, data):
    return ""
#     return """
#   <asset path="%(path)s">
#     <edition parameters="lang: workflow:public"
#          title=%(title)s
#          tags=""
#          created="2011-02-11 10:00:00"
#          modified="2011-02-11 10:00:00"><![CDATA[%(data)s
# ]]></edition>
#   </asset>
# """ % {'path': path,
#        'title': quoteattr(title),
#        'data': base64.encodestring(data),
#        }


def select_smaller_thumbnail(fileprefix):
    thumbnail_jpeg = open(fileprefix + ".jpeg", "rb").read()
    thumbnail_png = open(fileprefix + ".png", "rb").read()

    if len(thumbnail_jpeg) < len(thumbnail_png):
        return thumbnail_jpeg, 'jpeg'
    else:
        return thumbnail_png, 'png'

entry_data = asmmetadata.parse_file(sys.stdin)

def generate_section_description(section_data, pms_path_template):
    description = ''
    if 'description' in section:
        description += section['description']
        if section.get('ongoing', False) is True:
            pms_path = pms_path_template % section['pms-category']
            description += "<p>You can vote these entries at <a href='%s'>PMS</a>!</p>" % pms_path
    if 'youtube-playlist' in section:
        description += """<p><a href="https://www.youtube.com/playlist?list=%s">Youtube playlist of these entries</a></p>""" % section['youtube-playlist']

    return description


def get_image_size(data):
    image = PIL.Image.open(io.BytesIO(data))
    x, y = image.size
    return {"x": x, "y": y}


def meta_year(sections):
    section_keys = [section["key"] for section in sections]
    return "meta.json", {
        "sections": section_keys,
    }


def meta_section(section, included_entries, description=''):
    normalized_section = section['key']
    entry_keys = [
        asmmetadata.get_entry_key(entry) for entry in included_entries]

    return "%s/meta.json" % (normalized_section), {
        "name": section["name"],
        "description": section.get("description", ""),
        "is-ranked": section.get('ranked', True),
        "entries": entry_keys,
    }


def get_thumbnail_data(entry):
    thumbnail_base = asmmetadata.select_thumbnail_base(entry)
    thumbnail = None
    if thumbnail_base is not None:
        thumbnail, suffix = select_smaller_thumbnail(os.path.join(FILEROOT, thumbnail_base))
    else:
        # We don't have any displayable data.
        return None, None

    if thumbnail is None:
        del entry['section']
        sys.stderr.write("Missing thumbnail for %s!\n" % str(entry))
        sys.exit(1)

    return thumbnail, suffix


def entry_position_description_factory(pms_vote_template):
    def generator(entry, position_str):
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
            pms_path = pms_vote_template % entry['section']['pms-category']
            description += "<p>You can vote this entry at <a href='%s'>PMS</a>!</p>" % pms_path
        return description
    return generator


def calculate_checksum(data):
    m = hashlib.sha256()
    m.update(data)
    return base64.urlsafe_b64encode(m.digest())[:6].decode("utf-8")


def meta_entry(outfile, year, entry, description_generator, music_thumbnails):
    title = entry['title']
    author = entry['author']
    section_name = entry['section']['name']
    name = asmmetadata.get_entry_name(entry)

    asset = None

    normalized_name = asmmetadata.get_entry_key(entry)
    normalized_section = asmmetadata.normalize_key(section_name)
    position = entry.get('position', 0)

    extra_assets = ""

    external_links = ExternalLinks()
    locations = ""

    description = u""
    if 'warning' in entry:
        description += u"%s</p>\n<p>" % html.escape(entry['warning'])

    position_str = None
    if entry["section"].get("ranked", True):
        if position != 0:
            position_str = str(position) + asmmetadata.get_ordinal_suffix(position) + " place"

    has_media = False

    display_author = None
    if "Misc" in section_name or "Photos" in section_name:
        pass
    elif not "AssemblyTV" in section_name and not "Winter" in section_name:
        display_author = author
        if not "Seminars" in section_name:
            description += description_generator(entry, position_str)

    if 'description' in entry:
        description += u"%s</p>\n<p>" % entry['description']

    if 'platform' in entry:
        description += u"Platform: %s</p>\n<p>" % html.escape(entry['platform'])

    if 'techniques' in entry:
        description += u"Notes: %s</p>\n<p>" % html.escape(entry['techniques'])

    if display_author is not None:
        description += u"Author: %s\n" % html.escape(display_author)

    # Youtube is our primary location
    if "youtube" in entry:
        youtube_id_time = asmmetadata.get_timed_youtube_id(entry)
        has_media = True
        external_links.add(
            "View on",
            "YouTube",
            "https://www.youtube.com/watch?v=%s" % youtube_id_time)
        #locations += "<location type='youtube'>%s</location>" % youtube_id_time
        asset = {
            "type": "youtube",
            "data": {"id": youtube_id_time},
        }

    # Demoscenetv is no more
    # demoscenetv = entry.get('dtv')
    # if demoscenetv:
    #     has_media = True
        #locations += "<location type='demoscenetv'>%s</location>" % (escape(demoscenetv))

    # XXX some photos are missing
    if 'galleriafi' in entry:
        return

    if entry.get('image-file') or entry.get('galleriafi'):
        image_file = entry.get('image-file')
        if image_file is None:
            image_file = "%s/%s.jpeg" % (normalized_section, normalized_name)
        if asmmetadata.is_image(image_file):
            has_media = True
            baseprefix, _ = image_file.split(".")
            viewfile, postfix = select_smaller_thumbnail(
                os.path.join(FILEROOT, 'thumbnails/large/%s' % baseprefix))

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
            #locations += "<location type='image'>%s|%s</location>" % (image_filename, escape(name))

            extra_assets += display_asset(
                "%d/%s/%s/%s" % (year, normalized_section, normalized_name, image_filename), name, viewfile)

    webfile = entry.get('webfile')
    if webfile:
        if asmmetadata.is_image(webfile):
            has_media = True
            baseprefix, _ = webfile.split(".")
            viewfile, postfix = select_smaller_thumbnail(os.path.join(FILEROOT, 'thumbnails/large/%s' % baseprefix))

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
            "http://www.pouet.net/prod.php?which=%s" % pouet)
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
                    "https://files.scene.org/view/%s" % part,
                    "(scene.org)")

                # locations += "<location type='sceneorg'>%s|%s (%d/%d)</location>" % (
                #     escape(part), download_type, i, len(parts))
                i += 1
        else:
            external_links.add(
                "Download",
                "%s" % download_type,
                "https://files.scene.org/view/%s" % sceneorg,
                "(scene.org)")
            #locations += "<location type='sceneorg'>%s|%s</location>" % (escape(sceneorg), download_type)

    sceneorgvideo = entry.get('sceneorgvideo')
    mediavideo = entry.get('media')
    if sceneorgvideo:
        external_links.add(
            "Download",
            "HQ video",
            "https://files.scene.org/view/%s" % sceneorgvideo,
            "(scene.org)")
        #locations += "<location type='sceneorg'>%s|HQ video</location>" % (escape(sceneorgvideo))
    elif mediavideo:
        external_links.add(
            "Download",
            "HQ video",
            "https://media.assembly.org/%s" % mediavideo,
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
        return

    has_thumbnail = False
    if entry.get('use-parent-thumbnail', False) is True:
        has_thumbnail = True
        thumbnails = music_thumbnails
    else:
        thumbnail_data = get_thumbnail_data(entry)
        if thumbnail_data is not None:
            has_thumbnail = True
            thumbnail_bytes, thumbnail_suffix = thumbnail_data
            thumbnail_basename = "%s-thumbnail-default.%s" % (
                normalized_name, thumbnail_suffix)
            thumbnails = {
                "default": {
                    "filename": thumbnail_basename,
                    "size": get_image_size(thumbnail_bytes),
                    "checksum": calculate_checksum(thumbnail_bytes),
                    "type": "image/%s" % thumbnail_suffix,
                }
            }
            thumbnail_filename = "%s/%s/%s" % (
                normalized_section,
                normalized_name,
                thumbnail_basename)
            add_to_tar(outfile, thumbnail_filename, thumbnail_bytes)

    if not has_thumbnail:
        return

    ranking = 'ranking="%d"' % position
    if position == 0:
        ranking = ''

    description_non_unicode = description

    tags = set()
    entry_tags = entry.get('tags')
    if entry_tags:
        tags.update(entry_tags.split(" "))

#     if entry.get('use-parent-thumbnail', False) is False:
#         thumbnail_asset = """
#   <asset path="%(year)s/%(normalizedsection)s/%(normalizedname)s/thumbnail">
#     <edition parameters="lang: workflow:public"
#          title=%(title)s
#          tags="hide-search"
#          created="%(current-time)s"
#          modified="%(current-time)s"><![CDATA[%(data)s
# ]]></edition>
#   </asset>
# """ % {'year': year,
#        'normalizedsection': normalized_section,
#        'normalizedname': normalized_name,
#        'data': base64.encodestring(thumbnail_data),
#        'title': quoteattr(title),
#        'current-time': CURRENT_TIME,
#        }
#     else:
#         thumbnail_asset = ''

#     asset_data = """
#   <externalasset path="%(year)s/%(normalizedsection)s/%(normalizedname)s">
#     <edition parameters="lang: workflow:public"
#          title=%(title)s
#          tags=%(tags)s
#          created="%(current-time)s"
#          modified="%(current-time)s">
#       <mediagalleryadditionalinfo
#           author=%(author)s
#           description=%(description)s
#           %(ranking)s></mediagalleryadditionalinfo>
#       %(locations)s
#     </edition>
#   </externalasset>
# %(thumbnail)s
# """ % {'year': year,
#        'normalizedsection': normalized_section,
#        'normalizedname': normalized_name,
#        'title': quoteattr(title),
#        'author': quoteattr(author),
#        'ranking': ranking,
#        'thumbnail': thumbnail_asset,
#        'locations': locations,
#        'description': quoteattr(description_non_unicode),
#        'current-time': CURRENT_TIME,
#        'tags': quoteattr(" ".join(tags)),
#        }
#     asset_data_str = asset_data.encode("utf-8")
    return "%s/%s/meta.json" % (normalized_section, normalized_name), {
        "title": title,
        "author": author,
        "asset": asset,
        "thumbnails": thumbnails,
        "description": description,
        "external-links": external_links.sections,
    }
    # print asset_data_str
    # extra_assets_str = extra_assets.encode("utf-8")
    # print extra_assets_str


outfile = tarfile.TarFile.open(args.outfile, "w:gz")

music_thumbnail_data, music_thumbnail_suffix = select_smaller_thumbnail(
    os.path.join(FILEROOT, 'thumbnails', 'music-thumbnail'))
music_thumbnail_basename = "music-background.%s" % music_thumbnail_suffix
music_thumbnails = {
    "default": {
        "filename": "../../%s" % music_thumbnail_basename,
        "type": "image/%s" % music_thumbnail_suffix,
        "checksum": calculate_checksum(music_thumbnail_data),
        "size": get_image_size(music_thumbnail_data),
    }
}
add_to_tar(outfile, music_thumbnail_basename, music_thumbnail_data)

now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)

included_sections = []

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
    # Music files have all the same thumbnail.
    if 'music' in section['name'].lower():
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
            music_thumbnails)
        if not entry_out:
            continue
        included_entries.append(entry)
        entry_filename, entry_metadata = entry_out
        add_to_tar(outfile, entry_filename, json_dumps(entry_metadata))

    filename, data = meta_section(
        section, included_entries, section_description)
    add_to_tar(outfile, filename, json_dumps(data))

year_filename, year_metadata = meta_year(included_sections)
add_to_tar(outfile, year_filename, json_dumps(year_metadata))