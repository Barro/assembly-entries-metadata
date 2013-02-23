import argparse
import asmmetadata
import compodata
import sys

parser = argparse.ArgumentParser()
parser.add_argument('metadata_filename')
parser.add_argument("pms_root")
parser.add_argument("pms_party")
parser.add_argument('pms_login')
parser.add_argument('pms_password')
parser.add_argument('pms_compo')
parser.add_argument('--show-author', dest="show_author", default="default")
args = parser.parse_args()

metadata_file_name = args.metadata_filename
pms_login = args.pms_login
pms_password = args.pms_password
pms_compo = args.pms_compo

metadata_file = open(metadata_file_name, "rb")
metadata = asmmetadata.parse_file(metadata_file)

pms_url = compodata.pms_path_generator(args.pms_root, args.pms_party)

pms_data = compodata.download_compo_data(
    pms_url, pms_login, pms_password, pms_compo)
parsed_data = compodata.parse_compo_entries(pms_data, show_hidden_author=True)

selected_section = None
for section in metadata.sections:
    if section['pms-category'] == unicode(pms_compo):
        selected_section = section
        break

section_entries = []

for entry in parsed_data:
    existing_data = None
    for metadata_entry in selected_section['entries']:
        if entry['id'] == metadata_entry['pms-id']:
            existing_data = metadata_entry
            break
    addable_data = existing_data
    if existing_data is None:
        addable_data = {'section': selected_section}

    addable_data['pms-id'] = entry['id']
    addable_data['title'] = entry['title']
    addable_data['author'] = entry.get('author', None)
    if addable_data['author'] is None:
        del addable_data['author']
    section_entries.append(addable_data)
    # comments = entry.get('comments', None) or None
    # if comments is not None:
    #     addable_data['techniques'] = comments
    # if 'techniques' in addable_data:
    #     del addable_data['techniques']

selected_section['entries'] = section_entries

asmmetadata.print_metadata(sys.stdout, metadata)
