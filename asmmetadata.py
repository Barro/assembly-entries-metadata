# -*- coding: utf-8 -*-

import cgi
import hashlib
import re
import urllib

YOUTUBE_MAX_TITLE_LENGTH = 100

def get_party_name(year, section_name):
    if year < 2007:
        return u"Assembly %d" % year
    elif 'winter' in section_name.lower():
        return u"Assembly Winter %d" % year
    else:
        return u"Assembly Summer %d" % year

def get_party_tags(year, section_name):
    tags = []
    if year < 2007:
        tags.extend(["assembly", str(year), "asm%02d" % (year % 100), "Assembly %d" % year])
    elif 'winter' in section_name.lower():
        tags.extend(["assembly", str(year), "asm%02d" % (year % 100), "asmw%02d" % (year % 100), "Assembly Winter %d" % year])
    else:
        tags.extend(["assembly", str(year), "asm%02d" % (year % 100), "asms%02d" % (year % 100), "Assembly Summer %d" % year])
    if year == 2000:
        tags.append("asm2k")
    return tags

def get_content_types(section_name):
    normalized_section_name = normalize_key(section_name)

    # Major non-computer generated recordings.
    if "seminar" in normalized_section_name:
        return set(["seminar", "summer"])
    if "assemblytv" in normalized_section_name:
        return set(["assemblytv", "summer"])
    if "winter" in normalized_section_name:
        return set(["assemblytv", "winter"])
    # Don't separate photo sections yet.
    if "photo" in normalized_section_name:
        return set(["photo", "winter", "summer"])
    # Everything else is done during the summer.
    types = ["summer"]

    # Realtime types.
    if re.search("(^| )4k", normalized_section_name):
         types.extend(["4k", "intro", "realtime", "demo-product"])
    if re.search("(^| )64k", normalized_section_name):
         types.extend(["64k", "intro", "realtime", "demo-product"])
    if re.search("(^| )40k", normalized_section_name):
         types.extend(["40k", "intro", "realtime", "demo-product"])
    if "intro" in normalized_section_name:
         types.extend(["intro", "realtime", "demo-product"])
    if "demo" in normalized_section_name:
         types.extend(["demo", "realtime", "demo-product"])

    # Different platforms.
    if "c64" in normalized_section_name:
        types.extend(["c64"])
    if "amiga" in normalized_section_name:
         types.extend(["amiga"])
    if "console" in normalized_section_name:
         types.extend(["console"])
    if "java" in normalized_section_name:
         types.extend(["java"])
    if "win95" in normalized_section_name:
         types.extend(["win95", "windows"])
    if "windows" in normalized_section_name:
         types.extend(["windows"])
    if "oldskool" in normalized_section_name:
         types.extend(["oldskool"])
    if "mobile" in normalized_section_name:
         types.extend(["mobile"])
    if "browser" in normalized_section_name:
         types.extend(["browser"])
    if "flash" in normalized_section_name:
         types.extend(["flash"])
    if "winamp" in normalized_section_name:
         types.extend(["winamp"])
    if "playstation" in normalized_section_name:
         types.extend(["playstation"])

    # Music
    if "channel" in normalized_section_name:
         types.extend(["tracker"])
    if "tiny" in normalized_section_name:
         types.extend(["tracker"])
    if "music" in normalized_section_name:
         types.extend(["music"])
    if re.match("^music$", normalized_section_name):
         types.extend(["music-any"])
    if "mp3" in normalized_section_name:
         types.extend(["mp3", "music-any"])
    if "instrumental" in normalized_section_name:
         types.extend(["instrumental"])

    # Different video types.
    if "animation" in normalized_section_name:
         types.extend(["animation", "video"])
    if re.match("^wild$", normalized_section_name):
         types.extend(["video", "platform-any"])
    if "film" in normalized_section_name:
         types.extend(["video", "platform-any"])

    # Graphics.
    if "graphics" in normalized_section_name:
         types.extend(["graphics"])
    if "raytrace" in normalized_section_name:
         types.extend(["raytrace"])
    if "ansi" in normalized_section_name:
        types.extend(["ansi"])
    if "themed" in normalized_section_name:
        types.extend(["themed"])
    if "analog" in normalized_section_name:
         types.extend(["analog", "drawn"])
    if "drawn" in normalized_section_name:
         types.extend(["drawn"])
    if "pixel graphics" in normalized_section_name:
         types.extend(["drawn"])

    # Miscellaneous.
    if "fast" in normalized_section_name:
        types.extend(["fast", "themed"])
    if "extreme" in normalized_section_name:
         types.extend(["extreme"])
    if "executable" in normalized_section_name:
         types.extend(["extreme"])
    if "wild" in normalized_section_name:
         types.extend(["wild", "platform-any"])
    if "game" in normalized_section_name:
         types.extend(["gamedev"])

    return set(types)


def get_long_section_name(section_name):
    if "winter" in section_name.lower():
        return u"AssemblyTV"
    elif "assemblytv" in section_name.lower():
        return u"AssemblyTV"
    elif "seminars" in section_name.lower():
        return u"Seminars"
    else:
        return u"%s competition" % section_name

def normalize_key(value):
    normalized = value.strip().lower()
    normalized = normalized.replace(u"ä", u"a")
    normalized = normalized.replace(u"ö", u"o")
    normalized = normalized.replace(u"å", u"a")
    normalized = re.sub("[^a-z0-9]", "-", normalized)
    normalized = re.sub("-{2,}", "-", normalized)
    normalized = normalized.strip("-")
    return normalized

class EntryYear(object):
    year = None
    sections = []
    entries = []


def parse_entry_line(line):
    try:
        data_dict = dict((str(x.split(":", 1)[0]), x.split(":", 1)[1]) for x in line.split("|"))
    except:
        print line
        raise

    position = int(data_dict.get('position', u'0'))
    if position != 0:
        data_dict['position'] = position
    elif 'position' in data_dict:
        del data_dict['position']
    return data_dict

def parse_file(file_handle):
    result = EntryYear()

    year = None
    section = None
    normalized_section = None

    for line in file_handle:
        line = unicode(line.strip(), "utf-8")
        if line == "":
            continue
        if line[0] == "#":
            continue
        if line[0] == ":":
            data_type, value = line.split(" ", 1)
            if data_type == ":year":
                assert result.year is None
                year = int(value)
                result.year = year
            elif data_type == ":section":
                # Sections must have year.
                assert year is not None
                section_name = value
                normalized_section = normalize_key(section_name)
                assert not normalized_section in [section['key'] for section in result.sections]
                section = {
                    'key': normalized_section,
                    'name': section_name,
                    'year': year,
                    'entries': [],
                    }
                result.sections.append(section)
            elif data_type == ":description":
                # Descriptions can only be under section.
                assert section is not None
                # Only one description per section is allowed.
                assert 'description' not in section
                clean_value = value.strip()
                if len(clean_value):
                    section['description'] = clean_value
            elif data_type == ":youtube-playlist":
                assert section is not None
                assert 'youtube-playlist' not in section
                clean_value = value.strip()
                section['youtube-playlist'] = clean_value
            elif data_type == ":pms-category":
                # Categories can only be under section.
                assert section is not None
                # Only one category per section is allowed.
                assert 'pms-category' not in section
                clean_value = value.strip()
                if len(clean_value):
                    section['pms-category'] = clean_value
            elif data_type == ":ongoing":
                clean_value = value.strip()
                if clean_value.lower() == "true":
                    section['ongoing'] = True
            elif data_type == ":public":
                clean_value = value.strip()
                if clean_value.lower() == "false":
                    section['public'] = False
            else:
                raise RuntimeError, "Unknown type %s." % data_type
            continue

        assert year is not None
        assert section is not None

        data_dict = parse_entry_line(line)

        assert 'section' not in data_dict
        data_dict['section'] = section

        result.entries.append(data_dict)
        section['entries'].append(data_dict)

    return result


def print_metadata(outfile, year_entry_data):
    outfile.write(":year %d\n" % year_entry_data.year)
    for section in year_entry_data.sections:
        outfile.write("\n:section %s\n" % section['name'])
        if 'youtube-playlist' in section:
            outfile.write(":youtube-playlist %s\n" % section['youtube-playlist'].encode("utf-8"))
        if 'pms-category' in section:
            outfile.write(":pms-category %s\n" % section['pms-category'])
        if 'description' in section:
            outfile.write(":description %s\n" % section['description'].encode("utf-8"))
        if 'ongoing' in section:
            ongoing_text = "false"
            if section['ongoing'] is True:
                ongoing_text = "true"
            outfile.write(":ongoing %s\n" % ongoing_text)
        if 'public' in section:
            public_text = "true"
            if section['public'] is False:
                public_text = "false"
            outfile.write(":public %s\n" % public_text)

        outfile.write("\n")

        for entry in section['entries']:
            del entry['section']
            parts = sorted(u"%s:%s" % (key, value) for key, value in entry.items())
            outline = u"|".join(parts)
            outfile.write("%s\n" % outline.encode("utf-8"))

        outfile.write("\n")

def sort_entries(entries):
    return sorted(
        entries,
        lambda x, y: cmp(x.get('position', 999), y.get('position', 999)))

def select_thumbnail_base(entry):
    if 'youtube' in entry:
        return 'youtube-thumbnails/%s' % entry['youtube']
    if 'dtv' in entry:
        demoscenetv_thumb = cgi.parse_qs(entry['dtv'])['image'][0].split("/")[-1].split(".")[0]
        return 'dtv-thumbnails/%s' % demoscenetv_thumb
    if 'webfile' in entry or 'image-file' in entry:
        filename = entry.get('webfile', None) or entry.get('image-file')
        baseprefix, _ = filename.split(".")
        if filename.endswith(".png") or filename.endswith(".jpeg") or filename.endswith(".gif"):
            return 'thumbnails/small/%s' % baseprefix
    return None

def create_merged_image_base(start, entries):
    merged_name = "|".join(
        map(normalize_key,
            map(lambda entry: "%s-by-%s" % (entry['title'], entry['author']),
                entries)))
    filenames_digest = hashlib.md5(merged_name).hexdigest()
    return "merged-%s-%02d-%02d-%s" % (
        entries[0]['section']['key'],
        start,
        start + len(entries) - 1,
        filenames_digest,
        )


def get_ordinal_suffix(number):
    suffixes = {1: 'st',
               2: 'nd',
               3: 'rd'}
    suffix = suffixes.get(number % 10, 'th')
    if number in [11, 12, 13]:
        suffix = 'th'
    return suffix


def get_youtube_info_data(entry):
    title = entry['title']
    author = entry['author']
    section_name = entry['section']['name']
    if "AssemblyTV" in section_name or "Seminars" in section_name or "Winter" in section_name or "Misc" in section_name:
        name = title
    else:
        name = "%s by %s" % (title, author)

    position = entry.get('position', 0)

    description = u""
    if 'warning' in entry:
        description += u"%s\n\n" % entry['warning']

    position_str = None

    if position != 0:
        position_str = str(position) + get_ordinal_suffix(position) + " place"

    party_name = get_party_name(
        entry['section']['year'], entry['section']['name'])

    display_author = None
    if "Misc" in section_name:
        pass
    elif not "AssemblyTV" in section_name and not "Winter" in section_name:
        display_author = author
        if not "Seminars" in section_name:
            description += "%s %s competition entry, " % (party_name, section_name)
            if entry['section'].get('ongoing', False) is False:
                if position_str is not None:
                    description += u"%s" % position_str
                else:
                    description += u"not qualified to be shown on the big screen"
                description += u".\n\n"
        else:
            description += u"%s seminar presentation.\n\n" % party_name
    elif "AssemblyTV" in section_name or "Winter" in section_name:
        description += u"%s AssemblyTV program.\n\n" % party_name

    if 'description' in entry:
        description += u"%s\n\n" % entry['description']

    if 'platform' in entry:
        description += u"Platform: %s\n" % entry['platform']

    if 'techniques' in entry:
        description += u"Notes: %s\n" % entry['techniques']

    description += u"Title: %s\n" % title
    if display_author is not None:
        description += u"Author: %s\n" % display_author

    description += "\n"

    pouet = entry.get('pouet', None)
    if pouet is not None:
        description += u"Pouet.net: http://pouet.net/prod.php?which=%s\n" % urllib.quote_plus(pouet.strip())

    if 'download' in entry:
        download = entry['download']
        download_type = "Download original:"
        if "game" in section_name.lower():
            download_type = "Download playable game:"
        description += "%s: %s\n" % (download_type, download)

    if 'sceneorg' in entry:
        sceneorg = entry['sceneorg']
        download_type = "original"
        if "game" in section_name.lower():
            download_type = "playable game"
        if "," in sceneorg:
            parts = sceneorg.split(",")
            i = 1
            for part in parts:
                description += "Download %s part %d/%d: http://www.scene.org/file.php?file=%s\n" % (
                    download_type, i, len(parts), urllib.quote_plus(part))
                i += 1
        else:
            description += "Download %s: http://www.scene.org/file.php?file=%s\n" % (
                download_type, urllib.quote_plus(sceneorg))

    if 'sceneorgvideo' in entry:
        sceneorgvideo = entry['sceneorgvideo']
        description += "Download high quality video: http://www.scene.org/file.php?file=%s\n" % urllib.quote_plus(sceneorgvideo)
    elif 'media' in entry:
        mediavideo = entry['media']
        description += "Download high quality video: http://media.assembly.org%s\n" % mediavideo

    tags = set(get_party_tags(
            entry['section']['year'], entry['section']['name']))

    if 'tags' in entry:
        tags.update(entry['tags'].split(" "))

    if "AssemblyTV" in entry['section']['name'] or "Winter" in entry['section']['name']:
        tags.add("AssemblyTV")
    if "Seminars" in entry['section']['name']:
        tags.add("seminar")

    description_non_unicode = description.encode("utf-8")

    name = name.replace("<", "-")
    name = name.replace(">", "-")

    category = "Entertainment"
    if "Seminars" in entry['section']['name']:
        category = "Tech"

    return {
        'title': name[:YOUTUBE_MAX_TITLE_LENGTH].encode("utf-8"),
        'description': description_non_unicode,
        'tags': list(tags),
        'category': category,
        }
