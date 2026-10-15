# -*- coding: utf-8 -*-
"""Download verified vendor RFA URLs, inspect placement compatibility, load types."""
import hashlib
import io
import json
import os
import traceback
from datetime import datetime

from System import Array, Byte
from System.IO import FileAccess, FileMode, FileStream
from System.Net import WebRequest
from Autodesk.Revit import DB
from pyrevit import forms, script

import rt_revit as api
import rt_simpson_catalog as catalog

MAX_BYTES = 40 * 1024 * 1024


def cache_path(doc, entry):
    root = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    folder = os.path.join(root, 'RESIDENTIALTOOLS', 'BIM', 'Simpson',
                          'R' + str(doc.Application.VersionNumber))
    if not os.path.isdir(folder):
        os.makedirs(folder)
    return os.path.join(folder, catalog.filename(entry))


def checksum(path):
    result = hashlib.sha256()
    with io.open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            result.update(block)
    return result.hexdigest()


def cached_valid(path, entry):
    if not os.path.isfile(path) or not os.path.isfile(path + '.json'):
        return False
    try:
        with io.open(path + '.json', 'r', encoding='utf-8') as stream:
            source = json.load(stream)
        with io.open(path, 'rb') as stream:
            catalog.validate_rfa_header(stream.read(8))
        return source['url'] == entry['url'] and source['sha256'] == checksum(path)
    except (IOError, ValueError, KeyError):
        return False


def download(entry, path, log):
    catalog.filename(entry)
    request = WebRequest.Create(entry['url'])
    request.Timeout = 20000
    request.ReadWriteTimeout = 20000
    request.UserAgent = 'RESIDENTIALTOOLS-pyRevit/1.0'
    partial = path + '.part'
    response, incoming, outgoing = None, None, None
    try:
        response = request.GetResponse()
        if response.ContentLength > MAX_BYTES:
            raise ValueError('RFA download exceeds the 40 MB prototype limit.')
        incoming = response.GetResponseStream()
        outgoing = FileStream(partial, FileMode.Create, FileAccess.Write)
        buffer = Array.CreateInstance(Byte, 65536)
        total = 0
        while True:
            count = incoming.Read(buffer, 0, buffer.Length)
            if count == 0:
                break
            total += count
            if total > MAX_BYTES:
                raise ValueError('RFA download exceeds the 40 MB prototype limit.')
            outgoing.Write(buffer, 0, count)
        outgoing.Dispose()
        outgoing = None
        with io.open(partial, 'rb') as stream:
            catalog.validate_rfa_header(stream.read(8))
        if os.path.isfile(path):
            os.remove(path)
        os.rename(partial, path)
        source = dict(model=entry['model'], url=entry['url'], sha256=checksum(path),
                      downloaded_utc=datetime.utcnow().isoformat() + 'Z',
                      license_url=catalog.LICENSE_URL)
        with io.open(path + '.json', 'w', encoding='utf-8') as stream:
            stream.write(api.text_type(json.dumps(source, indent=2)))
        log('Simpson download: {0}; bytes={1}; sha256={2}'.format(entry['url'], total, source['sha256']))
        return source
    finally:
        for item in (outgoing, incoming, response):
            if item is not None:
                item.Dispose()
        if os.path.isfile(partial):
            os.remove(partial)


def license_confirmed():
    while True:
        choice = forms.alert('Simpson states that downloading represents agreement to its '
                             'License Agreement and Terms. Review the terms before downloading.\n\n' +
                             catalog.LICENSE_URL, title='Simpson Strong-Tie | Download terms',
                             options=['Review license terms', 'I agree; download this RFA', 'Cancel'])
        if choice == 'Review license terms':
            os.startfile(catalog.LICENSE_URL)
        else:
            return choice == 'I agree; download this RFA'


def load_compatible(doc, path, log):
    family_doc = doc.Application.OpenDocumentFile(path)
    try:
        if not family_doc.IsFamilyDocument:
            raise ValueError('Downloaded file is not a Revit family.')
        family = family_doc.OwnerFamily
        diagnostic = api.family_diagnostics(family)
        log('Simpson family inspection: ' + json.dumps(diagnostic, ensure_ascii=False))
        reason = api.hardware_family_reason(family)
        if reason:
            raise ValueError('Manufacturer family {0}: category={1}; placement={2}. {3}\n'
                             'The RFA remains cached for manual review: {4}'.format(
                                 diagnostic['name'], diagnostic['category'], diagnostic['placement'], reason, path))
        # OwnerFamily.Name can be empty in an opened vendor family document.
        family_name = family.Name or os.path.splitext(os.path.basename(path))[0]
        existing = next((item for item in DB.FilteredElementCollector(doc).OfClass(DB.Family)
                         if item.Name == family_name), None)
        if existing is not None:
            loaded = existing
            log('Reused existing loaded family without overwriting: ' + family_name)
        else:
            # Family-document overload runs its own load transaction. The target
            # project must not have an open transaction here.
            loaded = family_doc.LoadFamily(doc)
            if loaded is None:
                raise ValueError('Revit did not load the manufacturer family.')
            log('Loaded manufacturer family: ' + loaded.Name)
        eligible = set(symbol.UniqueId for symbol in api.hardware_types(doc))
        symbols = [doc.GetElement(eid) for eid in loaded.GetFamilySymbolIds()]
        return (sorted([symbol for symbol in symbols if symbol.UniqueId in eligible], key=api.symbol_name),
                existing is not None)
    finally:
        family_doc.Close(False)


def run(doc, values, log):
    result = dict(values)
    try:
        uid = values.get('joist_symbol_uid', '')
        symbol = doc.GetElement(uid) if uid else None
        category = api.type_category(symbol) if symbol is not None else 'unknown'
        role_choice = forms.CommandSwitchWindow.show(
            ['Size-matched joist hanger', 'Double-joist hanger (two touching plies)',
             'Hurricane tie', 'Corner angle', 'Browse Drawing Finder'],
            message='Selected joist: {0}\nEntered size: {1} x {2} in.\n'
                    'Model lookup does not select structural capacity, fasteners or coating.'
                    .format(api.symbol_name(symbol) if symbol else '(choose a joist for size-matched hangers)',values['joist_width_in'],values['joist_depth_in']))
        if not role_choice:
            return result
        if role_choice == 'Browse Drawing Finder':
            os.startfile(catalog.finder_url())
            return result
        role = {'Size-matched joist hanger': 'hanger',
                'Double-joist hanger (two touching plies)': 'double_hanger', 'Hurricane tie': 'hurricane',
                'Corner angle': 'corner'}[role_choice]
        if role in ('hanger','double_hanger'):
            if symbol is None: raise ValueError('Select a loaded joist family for a size-matched hanger.')
            width,depth=catalog.dimensions(values['joist_width_in'],values['joist_depth_in'])
        else: width,depth=0.0,0.0
        if role == 'double_hanger':
            width *= 2
        verified = False
        if role in ('hanger', 'double_hanger') and category == 'unknown':
            profile = forms.CommandSwitchWindow.show(
                ['Verified solid-sawn rectangular wood', 'Engineered wood / steel / other'],
                message='This family has no verified section identity. Which material/profile is it?')
            if profile is None:
                return result
            verified = profile == 'Verified solid-sawn rectangular wood'
        entries = catalog.candidates(role, width, depth, category, verified)
        if not entries:
            forms.alert('There is no verified size match in this starter index. '
                        'I-joists, LVL and steel need product-specific hanger selection. '
                        'Use Simpson Drawing Finder and load the reviewed RFA manually.',
                        title='Simpson BIM library', options=['OK'])
            os.startfile(catalog.finder_url())
            return result
        labels = [entry['model'] + ' | Simpson 3D RFA' for entry in entries]
        choice = forms.SelectFromList.show(labels, title='Simpson | Choose model to review',
                                           multiselect=False, button_name='Get RFA')
        if not choice:
            return result
        entry = entries[labels.index(choice)]
        path = cache_path(doc, entry)
        use_cache = False
        if cached_valid(path, entry):
            action = forms.CommandSwitchWindow.show(['Use cached RFA', 'Download latest', 'Cancel'],
                                                    message=entry['model'])
            if action is None or action == 'Cancel':
                return result
            use_cache = action == 'Use cached RFA'
        if not use_cache:
            if not license_confirmed():
                return result
            download(entry, path, log)
        symbols, reused_existing = load_compatible(doc, path, log)
        if not symbols:
            raise ValueError('No eligible point or work-plane hardware type was found in the loaded family.')
        type_labels = [api.symbol_name(item) for item in symbols]
        selected_label = forms.SelectFromList.show(type_labels, title='Simpson | Loaded family type',
                                                   multiselect=False, button_name='Choose type')
        if selected_label is None:
            return result
        selected = symbols[type_labels.index(selected_label)]
        needs_rims=role in ('hanger','double_hanger','corner')
        if not values['framing_enabled'] or (needs_rims and not values['rims']):
            forms.alert('Family loaded. Enable framing and, for end hangers/corner brackets, rim joists before placement.',
                        title='Simpson BIM library')
            return result
        action = forms.alert('Family available: {0}\n{1}\n\nCheck its origin, orientation, section fit, '
                             'coating and fasteners in Revit. Placement still uses the prototype '
                             'joist-end/corner insertion points.\n\n'
                             'Hardware will be placed only on Build / rebuild layout.'.format(
                                 api.symbol_name(selected),
                                 'Existing project family reused without overwrite.' if reused_existing
                                 else 'Manufacturer RFA loaded into the project.'),
                             title='Simpson | Loaded hardware',
                             options=['Select for prototype placement', 'Load only'])
        if action != 'Select for prototype placement':
            return result
        result[catalog.ROLE_KEYS[role]] = selected.UniqueId
        sources = dict(values.get('simpson_sources', {}))
        sources[role] = dict(model=entry['model'], url=entry['url'], unique_id=selected.UniqueId,
                             source_rfa_sha256=checksum(path), loaded_family_reused=reused_existing,
                             joist_symbol_uid=symbol.UniqueId if symbol else None,
                             width_in=width, depth_in=depth,
                             ply_count=2 if role == 'double_hanger' else 1,
                             verified_solid_sawn=verified,
                             selection_is_structural_design=False)
        result['simpson_sources'] = sources
        log('Selected Simpson {0}: {1}; joist={2}; {3:g}x{4:g} in; placement unverified.'
            .format(role, entry['model'], symbol.UniqueId if symbol else None, width, depth))
    except Exception as error:
        detail = traceback.format_exc()
        log('Simpson library error:\n' + detail)
        script.get_logger().error(detail)
        forms.alert('Simpson hardware was not selected. No deck rebuild was performed. '
                    'Downloaded RFAs remain cached.\n\n' + api.text_type(error),
                    title='Simpson BIM library | Error')
    return result
