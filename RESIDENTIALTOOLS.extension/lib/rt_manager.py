# -*- coding: utf-8 -*-
"""Safe selection, inspection and removal for RESIDENTIALTOOLS layouts."""
import traceback
import os

from Autodesk.Revit import DB
from System.Collections.Generic import List
from pyrevit import forms, revit, script

import rt_revit as api
import rt_command
from rt_layout import validate_deletion_scope


def _label(record):
    settings = record.get('settings', {})
    counts = record.get('counts', {})
    return '{0} | {1} | boards {2}, framing {3}, clips {4}'.format(
        settings.get('name', 'Unnamed layout'), record.get('layout_id', '')[:8],
        counts.get('boards', 0)+counts.get('borders',0), counts.get('framing', 0), counts.get('clips', 0))


def _select_layout(doc):
    records = api.layout_records(doc)
    if not records:
        forms.alert('This project has no RESIDENTIALTOOLS layouts yet.', title='Deck Manager')
        return None
    labels = [_label(record) for storage, record in records]
    choice = forms.SelectFromList.show(labels, title='Deck Manager | Choose layout',
                                       multiselect=False, button_name='Manage')
    if not choice:
        return None
    return records[labels.index(choice)]


def _summary(record):
    settings, counts = record.get('settings', {}), record.get('counts', {})
    roles = [entry.get('item', {}).get('role') for entry in record.get('items', [])]
    return ('{0}\nLayout ID: {1}\n\nSaved build summary — registered elements: {2}\n'
            'Boards: {3} | Joists: {4} | Rims: {5} | Blocking: {6}\n'
            'Clips: {7} | Hangers: {8} | Hurricane straps: {9} | Corner straps: {10}\n\n'
            'Footprint extents: {11:g} ft × {12:g} ft\nSpacing: {13} in O.C.\n'
            'Managed hardware work planes: {14} (excluded from piece counts)\n'
            'Double hangers: {15} (included in total hangers)\nBeams: {16} | Posts: {17}').format(
                settings.get('name', 'Unnamed layout'), record.get('layout_id', ''),
                len(record.get('element_uids', [])), counts.get('boards', 0),
                roles.count('JOIST'), roles.count('RIM'), roles.count('BLOCK'),
                counts.get('clips', 0), counts.get('hangers', 0),
                counts.get('hurricane_straps', 0), counts.get('corner_straps', 0),
                settings.get('run_ft', 0), settings.get('span_ft', 0),
                settings.get('spacing_in', '?'), record.get('managed_hardware_planes', 0),
                counts.get('double_hangers', 0), counts.get('beams', 0), counts.get('posts', 0))


def _inspection(doc, record):
    from rt_accessories import records as accessory_records
    children=accessory_records(doc,record['layout_id'])
    elements,missing=api.registered_elements(doc,record,require_editable=False)
    roles=[api.read_stamp(element).get('role') for element in elements]
    planes=roles.count('HARDWARE_PLANE')
    accessory_roots=0
    for child_storage,child in children:
        child_elements,child_missing=api.registered_elements(doc,child,require_editable=False)
        accessory_roots+=sum(element.UniqueId in child.get('root_uids',[]) for element in child_elements)
        missing.extend(child_missing)
    details=_summary(record)
    details+='\n\nCurrent registered primary pieces: '+str(len(elements)-planes)
    details+='\nCurrent hardware work planes: '+str(planes)
    details+='\nCurrent stair/railing assemblies: '+str(accessory_roots)
    details+='\nMissing registered elements: '+str(len(missing))
    details+='\nSaved borders (including breakers): '+str(record.get('counts',{}).get('borders',0))
    details+='\nSaved breaker boards (included in borders): '+str(sum(entry.get('item',{}).get('border_kind')=='breaker'
                                                                  for entry in record.get('items',[])))
    details+='\nAccessory registries: '+str(len(children))
    if missing: details+='\nSome registered elements are missing. Rebuild or review Material List before ordering.'
    if any(child.get('parent_generation')!=record['generation'] for child_storage,child in children):
        details+='\nAccessories belong to an older deck generation; verify alignment and rerun those tools.'
    details+='\n'+'\n'.join(record.get('warnings',[]))
    return details


def _select_elements(doc, uidoc, record):
    elements, missing = api.registered_elements(doc, record, require_editable=False)
    elements=[e for e in elements if api.read_stamp(e).get('role')!='HARDWARE_PLANE']
    from rt_accessories import records as accessory_records
    for child_storage,child_record in accessory_records(doc,record['layout_id']):
        child_elements,child_missing=api.registered_elements(doc,child_record,require_editable=False)
        elements.extend(e for e in child_elements if e.UniqueId in child_record.get('root_uids',[]))
        missing.extend(child_missing)
    ids = List[DB.ElementId]()
    for element in elements:
        ids.Add(element.Id)
    uidoc.Selection.SetElementIds(ids)
    forms.alert('Selected {0} generated elements. Missing registered elements: {1}.'.format(
        len(elements), len(missing)), title='Deck Manager')


def _remove(doc, storage, record, log):
    elements, missing = api.registered_elements(doc, record)
    from rt_accessories import records as accessory_records
    storages=[storage]
    for child_storage,child_record in accessory_records(doc,record['layout_id']):
        child_elements,child_missing=api.registered_elements(doc,child_record)
        elements.extend(child_elements); missing.extend(child_missing); storages.append(child_storage)
    expected = set(api.id_value(element.Id) for element in elements)
    expected.update(api.id_value(item.Id) for item in storages)
    ids = List[DB.ElementId]()
    for element in elements:
        ids.Add(element.Id)
    for item in storages:
        ids.Add(item.Id)
    with api.transaction(doc, 'RESIDENTIALTOOLS | remove managed layout', log):
        deleted = set(api.id_value(eid) for eid in doc.Delete(ids))
        validate_deletion_scope(expected, deleted)
    log('Removed managed layout {0}; deleted {1} registered elements; missing {2}.'.format(
        record.get('layout_id'), len(elements), len(missing)))
    return len(elements), len(missing)


def run():
    doc, uidoc = revit.doc, revit.uidoc
    if doc is None or uidoc is None or doc.IsFamilyDocument:
        forms.alert('Open a Revit project to manage generated decks.', title='Deck Manager')
        return
    if str(doc.Application.VersionNumber) not in ('2025', '2027'):
        forms.alert('This tool targets Revit 2025 and 2027.', title='Deck Manager')
        return
    logger = script.get_logger()
    folder, log_path, log = rt_command.log_session(doc, 'Deck Manager')
    removed_committed=False
    try:
        selection = _select_layout(doc)
        if selection is None:
            log('No layout was selected; model unchanged.')
            return
        storage, record = selection
        log('Selected layout {0}.'.format(record.get('layout_id')))
        choice = forms.CommandSwitchWindow.show(
            ['Inspect counts & warnings', 'Select generated elements', 'Open layout reports', 'Remove generated layout'],
            message=_summary(record))
        if choice == 'Inspect counts & warnings':
            forms.alert(_inspection(doc,record), title='Deck Manager | Layout details')
            log('Inspected layout {0}.'.format(record.get('layout_id')))
        elif choice == 'Select generated elements':
            _select_elements(doc, uidoc, record)
            log('Selected registered elements for layout {0}.'.format(record.get('layout_id')))
        elif choice == 'Open layout reports':
            rt_command.export_result(folder,record)
            log('Exported saved layout registry snapshot; use Material List for live measured quantities.')
            os.startfile(folder)
        elif choice == 'Remove generated layout':
            if not forms.alert('Remove this managed layout, its registered stairs/railings and generated elements?\n\n'
                               'Unrelated elements are never included.', title='Confirm removal',
                               yes=True, no=True):
                return
            removed, missing = _remove(doc, storage, record, log)
            removed_committed=True
            forms.alert('Removed {0} registered elements. Missing before removal: {1}.\nLog: {2}'.format(
                removed, missing, log_path), title='Deck Manager')
    except Exception:
        detail = traceback.format_exc()
        logger.error(detail)
        log(detail)
        state=('Layout removal was committed; a later reporting step failed.' if removed_committed else
               'Deck Manager stopped without completing the requested action.')
        forms.alert(state+'\n\n' +
                    '{0}\n\nLog: {1}'.format(detail[-1100:], log_path),
                    title='Deck Manager | Error')
