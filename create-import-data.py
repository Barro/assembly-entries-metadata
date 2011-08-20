import asmmetadata
import base64
import cgi
import optparse
import os.path
import sys
import time
from xml.sax.saxutils import escape
from xml.sax.saxutils import quoteattr

CURRENT_TIME = time.strftime("%Y-%m-%d %H:%M:%S")


parser = optparse.OptionParser()
parser.add_option("--no-empty", dest="noempty", action="store_true",
                  help="Prevent empty sections from going to import data.")

(options, args) = parser.parse_args()
if len(args) != 1:
    parser.error("Need to give file root.")
fileroot = args[0]

create_empty_sections = not options.noempty

def display_asset(path, title, data):
    return """
  <asset path="%(path)s">
    <edition parameters="lang: workflow:public"
         title=%(title)s
         tags=""
         created="2011-02-11 10:00:00"
         modified="2011-02-11 10:00:00"><![CDATA[%(data)s
]]></edition>
  </asset>
""" % {'path': path, 'title': quoteattr(title), 'data': base64.encodestring(data)}

def select_smaller_thumbnail(fileprefix):
        thumbnail_jpeg = open(fileprefix + ".jpeg", "r").read()
        thumbnail_png = open(fileprefix + ".png", "r").read()

        if len(thumbnail_jpeg) < len(thumbnail_png):
            return thumbnail_jpeg, '.jpeg'
        else:
            return thumbnail_png, '.png'

entry_data = asmmetadata.parse_file(sys.stdin)

print """<?xml version="1.0" encoding="utf-8"?>
<import base="http://archive.assembly.org">
  <mediagallery path="%(year)s" purge="true">
    <edition parameters="lang: workflow:public"
         title="%(year)s"
         tags=""
         created="2011-02-11 10:00:00"
         modified="2011-02-11 10:00:00">
    </edition>
  </mediagallery>
""" % {'year': entry_data.year}

def print_section(year, section):
    normalized_section = section['key']
    sectionpath = "%s/%s" % (year, normalized_section)
    additionalinfo = ''
    description = ''
    if 'description' in section:
        description += section['description']
        # XXX Check for next year.
        # if section['ongoing'] is True:
        #     pms_path = "asm11/compos/%s/vote/" % section['pms-category']
        #     description += "<p>You can vote these entries at <a href='https://pms.asm.fi/%s'>PMS</a>!</p>" % pms_path
    if 'youtube-playlist' in section:
        description += """<p><a href="http://www.youtube.com/playlist?list=%s">Youtube playlist of these entries</a></p>""" % section['youtube-playlist']

    if description != '':
        additionalinfo = """
<mediagalleryadditionalinfo
    description=%s
>
</mediagalleryadditionalinfo>
""" % quoteattr(description)

    section_unicode = """
  <mediagallery path="%(sectionpath)s">
    <edition parameters="lang: workflow:public"
         title="%(section)s"
         tags=""
         created="2011-02-11 10:00:00"
         modified="2011-02-11 10:00:00">
        %(additionalinfo)s
    </edition>
  </mediagallery>
""" % {'year': year,
       'section': section['name'],
       'normalizedsection': normalized_section,
       'sectionpath': sectionpath,
       'additionalinfo': additionalinfo,
       }

    print section_unicode.encode("utf-8")

def get_ordinal_suffix(number):
    suffixes = {1: 'st',
               2: 'nd',
               3: 'rd'}
    suffix = suffixes.get(number % 10, 'th')
    if number in [11, 12, 13]:
        suffix = 'th'
    return suffix

def print_entry(year, entry):
    title = entry['title']
    author = entry['author']
    section_name = entry['section']['name']
    if "AssemblyTV" in section_name or "Seminars" in section_name or "Winter" in section_name:
        name = title
    else:
        name = "%s by %s" % (title, author)

    normalized_name = asmmetadata.normalize_key(name)
    normalized_section = asmmetadata.normalize_key(section_name)
    position = entry.get('position', 0)

    extra_assets = ""

    locations = ""

    thumbnail = None

    description = u""
    if 'warning' in entry:
        description = u"%s</p>\n<p>" % entry['warning']

    position_str = None

    if position != 0:
        position_str = str(position) + get_ordinal_suffix(position) + " place"

    if not "AssemblyTV" in section_name and not "Winter" in section_name:
        if not "Seminars" in section_name:
            if entry['section'].get('ongoing', False) is False:
                if position_str is not None:
                    description += u"%s" % position_str
                else:
                    description += u"Not qualified to be shown on the big screen"
                description += u".</p>\n<p>\n"
            # XXX Check for next year.
            # else:
            #     pms_path = "asm11/compos/%s/vote/" % entry['section']['pms-category']
            #     description += "<p>You can vote this entry at <a href='https://pms.asm.fi/%s'>PMS</a>!</p>" % pms_path

        if 'techniques' in entry:
            description += u"Notes: %s</p>\n<p>" % entry['techniques']

        if 'description' in entry:
            description += u"%s</p>\n<p>" % entry['description']

        description += u"Author: %s\n" % cgi.escape(author)

    if 'dtv' in entry:
        demoscenetv = entry['dtv']

    # Youtube is primary location
    if 'youtube' in entry:
        youtube = entry['youtube']
        locations += "<location type='youtube'>%s</location>" % youtube

    # Youtube is primary location
    if 'dtv' in entry:
        demoscenetv = entry['dtv']
        locations += "<location type='demoscenetv'>%s</location>" % (escape(demoscenetv))

    if 'image-file' in entry and 'webfile' not in entry:
        image_file = entry['image-file']
        if image_file.endswith(".png") or image_file.endswith(".jpeg") or image_file.endswith(".gif"):
            baseprefix, _ = image_file.split(".")
            viewfile, postfix = select_smaller_thumbnail(os.path.join(fileroot, 'thumbnails/large/%s' % baseprefix))

            normal_prefix = asmmetadata.normalize_key(baseprefix)
            image_filename = normal_prefix + postfix
            locations += "<location type='image'>%s|%s</location>" % (image_filename, escape(name))

            extra_assets += display_asset(
                "%d/%s/%s/%s" % (year, normalized_section, normalized_name, image_filename), name, viewfile)

    if 'webfile' in entry:
        webfile = entry['webfile']
        if webfile.endswith(".png") or webfile.endswith(".jpeg") or webfile.endswith(".gif"):
            baseprefix, _ = webfile.split(".")
            viewfile, postfix = select_smaller_thumbnail(os.path.join(fileroot, 'thumbnails/large/%s' % baseprefix))

            normal_prefix = asmmetadata.normalize_key(baseprefix)
            image_filename = normal_prefix + postfix
            locations += "<location type='download'>http://media.assembly.org/compo-media/assembly%d/%s|Full resolution</location>" % (year, webfile)
            locations += "<location type='image'>%s|%s</location>" % (image_filename, escape(name))

            extra_assets += display_asset(
                "%d/%s/%s/%s" % (year, normalized_section, normalized_name, image_filename), name, viewfile)
        elif webfile.endswith(".mp3"):
            locations += "<location type='download'>http://media.assembly.org/compo-media/assembly%d/%s|MP3</location>" % (year, webfile)

    if 'pouet' in entry:
        pouet = entry['pouet']
        locations += "<location type='pouet'>%s</location>" % (pouet)

    if 'download' in entry:
        download = entry['download']
        download_type = "Original"
        if "game" in section_name.lower():
            download_type = "Playable game"
        locations += "<location type='download'>%s|%s</location>" % (escape(download), download_type)

    if 'sceneorg' in entry:
        sceneorg = entry['sceneorg']
        download_type = "Original"
        if "game" in section_name.lower():
            download_type = "Playable game"
        if "," in sceneorg:
            parts = sceneorg.split(",")
            i = 1
            for part in parts:
                locations += "<location type='sceneorg'>%s|%s (%d/%d)</location>" % (
                    escape(part), download_type, i, len(parts))
                i += 1
        else:
            locations += "<location type='sceneorg'>%s|%s</location>" % (escape(sceneorg), download_type)

    if 'sceneorgvideo' in entry:
        sceneorgvideo = entry['sceneorgvideo']
        locations += "<location type='sceneorg'>%s|HQ video</location>" % (escape(sceneorgvideo))
    elif 'media' in entry:
        mediavideo = entry['media']
        locations += "<location type='download'>http://media.assembly.org%s|HQ video</location>" % (mediavideo)

    thumbnail_base = asmmetadata.select_thumbnail_base(entry)
    thumbnail = None
    if thumbnail_base is not None:
        thumbnail, _ = select_smaller_thumbnail(os.path.join(fileroot, thumbnail_base))

    if thumbnail is None:
        sys.stderr.write("Missing thumbnail for %s!\n" % str(entry))
        sys.exit(1)
        return

    ranking = 'ranking="%d"' % position
    if position == 0:
        ranking = ''

    description_non_unicode = description

    asset_data = """
  <externalasset path="%(year)s/%(normalizedsection)s/%(normalizedname)s">
    <edition parameters="lang: workflow:public"
         title=%(title)s
         tags="hide-navigation"
         created="%(current-time)s"
         modified="%(current-time)s">
      <mediagalleryadditionalinfo
          author=%(author)s
          description=%(description)s
          %(ranking)s></mediagalleryadditionalinfo>
      %(locations)s
    </edition>
  </externalasset>
  <asset path="%(year)s/%(normalizedsection)s/%(normalizedname)s/thumbnail">
    <edition parameters="lang: workflow:public"
         title=%(title)s
         tags="hide-navigation"
         created="%(current-time)s"
         modified="%(current-time)s"><![CDATA[%(thumbnail)s
]]></edition>
  </asset>
""" % {'year': year,
       'normalizedsection': normalized_section,
       'normalizedname': normalized_name,
       'title': quoteattr(title),
       'author': quoteattr(author),
       'ranking': ranking,
       'thumbnail': base64.encodestring(thumbnail),
       'locations': locations,
       'description': quoteattr(description_non_unicode),
       'current-time': CURRENT_TIME,
       }
    asset_data_str = asset_data.encode("utf-8")
    print asset_data_str
    extra_assets_str = extra_assets.encode("utf-8")
    print extra_assets_str


for section in entry_data.sections:
    if section.get('public', True) is False:
        continue
    if len(section['entries']) == 0 and not create_empty_sections:
        continue
    print_section(entry_data.year, section)

    for entry in asmmetadata.sort_entries(section['entries']):
        print_entry(entry_data.year, entry)

print """</import>"""