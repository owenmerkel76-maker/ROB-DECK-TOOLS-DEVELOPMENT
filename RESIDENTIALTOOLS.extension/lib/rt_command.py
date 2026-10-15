# -*- coding: utf-8 -*-
"""Shared command workflow. Run inside pyRevit; no external extensions imported."""
import io
import json
import math
import os
import traceback
from datetime import datetime

from Autodesk.Revit import DB
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ObjectType, ObjectSnapTypes
from pyrevit import forms, revit, script

import rt_revit as api
import rt_ui
import rt_clip
import rt_simpson
import rt_presentation
from rt_layout import DEFAULTS


def floor_rectangle(floor, allow_sloped=False):
    """Read one planar straight-edge Floor, optionally projected for a level roof deck."""
    import rt_geometry
    faces = []
    for solid in api.geometry_solids(floor.get_Geometry(DB.Options())):
        faces.extend(face for face in solid.Faces
                     if isinstance(face, DB.PlanarFace) and face.FaceNormal.Z > (.01 if allow_sloped else .999999))
    if not faces:
        raise ValueError('Floor has no horizontal top face. Sloped footprints are deferred.')
    face = max(faces, key=lambda item: (item.Origin.Z, item.Area))
    if len(faces)!=1:
        raise ValueError('This mode requires one planar Floor top surface; multi-facet surfaces need separate outline/support zones.')
    loops = list(face.GetEdgesAsCurveLoops())
    if len(loops) != 1:
        raise ValueError('Floors with openings/multiple loops are not supported yet.')
    curves = list(loops[0])
    if not 3 <= len(curves) <= 100 or not all(isinstance(curve, DB.Line) for curve in curves):
        raise ValueError('Select a horizontal Floor with straight edges; curved boundaries are deferred.')
    points = [curve.GetEndPoint(0) for curve in curves]
    if not allow_sloped and max(p.Z for p in points)-min(p.Z for p in points)>1.e-5:
        raise ValueError('Floor boundary is sloped.')
    longest = max(curves,key=lambda curve: curve.Length)
    delta = longest.GetEndPoint(1)-longest.GetEndPoint(0)
    u = DB.XYZ(delta.X,delta.Y,0).Normalize()
    v = DB.XYZ(-u.Y,u.X,0)
    xs,ys = [p.DotProduct(u) for p in points],[p.DotProduct(v) for p in points]
    run,span = max(xs)-min(xs),max(ys)-min(ys)
    polygon = rt_geometry.polygon([(x-min(xs),y-min(ys)) for x,y in zip(xs,ys)])
    projected_area=face.Area*face.FaceNormal.Z
    if abs(rt_geometry.area(polygon)-projected_area)>.001:
        raise ValueError('Top face area does not match the selected Floor outline.')
    origin = u*min(xs)+v*min(ys)
    rectangular = len(polygon)==4 and abs(run*span-projected_area)<.001
    return (dict(origin=[origin.X,origin.Y],u=[u.X,u.Y],
                 source='Floor '+str(api.id_value(floor.Id)),source_floor_uid=floor.UniqueId,
                 footprint_polygon=None if rectangular else polygon,
                 roof_projection=allow_sloped,source_peak_ft=max(p.Z for p in points)),
            run,span,max(p.Z for p in points) if allow_sloped else points[0].Z)


def pick_footprint(uidoc, doc):
    choice = forms.CommandSwitchWindow.show(
        ['Pick three plan points', 'Use a horizontal Floor outline',
         'Level roof-deck outline from a sloped Floor'], message='Define residential framing/deck footprint')
    if not choice:
        return None
    if choice in ('Use a horizontal Floor outline','Level roof-deck outline from a sloped Floor'):
        prompt=('Select a single planar sloped Floor to project a level roof deck' if choice.startswith('Level roof-deck')
                else 'Select a horizontal Floor, including stepped outlines')
        reference = uidoc.Selection.PickObject(ObjectType.Element, prompt)
        floor = doc.GetElement(reference.ElementId)
        if not isinstance(floor, DB.Floor):
            raise ValueError('Selected element is not a Floor.')
        return floor_rectangle(floor,allow_sloped=choice.startswith('Level roof-deck'))
    if doc.ActiveView.ViewType not in (DB.ViewType.FloorPlan, DB.ViewType.EngineeringPlan):
        raise ValueError('Pick three points from a floor/structural plan with a work plane.')
    a = uidoc.Selection.PickPoint(ObjectSnapTypes.Endpoints, 'Point 1: first corner of rectangle edge A')
    b = uidoc.Selection.PickPoint(ObjectSnapTypes.Endpoints, 'Point 2: other end of the SAME rectangle edge A')
    c = uidoc.Selection.PickPoint(ObjectSnapTypes.Endpoints, 'Point 3: point on the opposite parallel edge')
    vector = DB.XYZ(b.X-a.X, b.Y-a.Y, 0)
    run = vector.GetLength()
    if run < 2.0:
        raise ValueError('Rectangle edge A must be at least two feet long.')
    u = vector.Normalize()
    v = DB.XYZ(-u.Y, u.X, 0)
    span = (c-a).DotProduct(v)
    if abs(span) < 2.0:
        raise ValueError('Opposite edge must be at least two feet away.')
    origin = a if span > 0 else a + v*span
    return (dict(origin=[origin.X, origin.Y], u=[u.X, u.Y], source='three picked points'),
            run, abs(span), a.Z)


def footprint_key(anchor, values, doc):
    # Ignore edge order/orientation; detect a second managed layout at the same
    # physical rectangle and elevation even when picked in the reverse direction.
    u = anchor['u']
    v = [-u[1], u[0]]
    origin = anchor['origin']
    corners = [(round(origin[0]+u[0]*x+v[0]*y, 5), round(origin[1]+u[1]*x+v[1]*y, 5))
               for x, y in (values.get('footprint_polygon') or [(0, 0), (values['run_ft'], 0),
                            (values['run_ft'], values['span_ft']), (0, values['span_ft'])])]
    level = doc.GetElement(values['level_uid'])
    z = level.Elevation + values['height_in']/12.0 if level is not None else None
    return sorted(corners), round(z, 5) if z is not None else None


def log_session(doc, mode):
    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    folder = os.path.join(base, 'RESIDENTIALTOOLS', 'Reports',
                          datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    os.makedirs(folder)
    log_path = os.path.join(folder, 'run.log')
    def log(message):
        try:
            with io.open(log_path, 'a', encoding='utf-8') as stream:
                stream.write(u'{0} {1}\n'.format(datetime.now().isoformat(), message))
        except (IOError,OSError):
            script.get_logger().warning('File log unavailable; %s',message)
    log('Mode={0}; Revit={1}; document={2}'.format(mode, doc.Application.VersionNumber, doc.Title))
    log('Extension release={0}; source={1}'.format(rt_presentation.release_version(),os.path.dirname(os.path.dirname(__file__))))
    return folder, log_path, log


def export_result(folder, record):
    with io.open(os.path.join(folder, 'layout_report.json'), 'w', encoding='utf-8') as stream:
        stream.write(api.text_type(json.dumps(record, ensure_ascii=False, indent=2)))
    # Simple installed-piece counts/dimensions, not a purchase/stock packing estimate.
    with io.open(os.path.join(folder, 'installed_pieces.csv'), 'w', encoding='utf-8') as stream:
        stream.write(u'key,role,element_id,unique_id,length_ft,width_in\n')
        for item in record['items']:
            shape = item['item']
            if shape['role'] == 'HARDWARE_PLANE':
                continue  # Managed construction reference, not an installed piece.
            length = shape.get('length_ft', '')
            if 'a' in shape:
                length = math.sqrt(sum((shape['b'][i]-shape['a'][i])**2 for i in (0, 1)))
            elif shape['role'] == 'POST':
                length = shape['height_ft']
            stream.write(u'{0},{1},{2},{3},{4},{5}\n'.format(
                shape['key'], shape['role'], item['element_id'], item['unique_id'],
                length, shape.get('width_in', '')))


def create_clip_rfa(app, folder, log):
    template = forms.pick_file(file_ext='rft', title='Select unhosted Generic Model.rft for schematic clip')
    if not template:
        return
    destination = forms.pick_folder(title='Select destination for generic schematic clip RFA')
    if not destination:
        return
    path = os.path.join(destination, rt_clip.FAMILY_NAME + '_R' + str(app.VersionNumber)
                        + '_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.rfa')
    api.generate_clip_family(app, template, path, log)
    log('Schematic clip RFA saved: ' + path)
    forms.alert('Generic schematic clip RFA saved:\n{0}\n\n'
                'Load it with Insert > Load Family, then choose Loaded family in the '
                'clip settings. Test its origin, orientation and gap fit in Revit. '
                'This is reused schematic geometry, not manufacturer CAD.'.format(path),
                title='RESIDENTIALTOOLS | Schematic clip')


def choose_layout(doc, uidoc, mode):
    records = api.layout_records(doc)
    if not records: return (None,None)
    selected_ids = []
    for eid in uidoc.Selection.GetElementIds():
        element = doc.GetElement(eid)
        if element is not None:
            layout_id = api.read_stamp(element).get('layout_id')
            if layout_id:
                selected_ids.append(layout_id)
    selected_ids = set(selected_ids)
    if len(selected_ids) == 1:
        for storage, record in records:
            if record['layout_id'] in selected_ids:
                return storage, record
    if mode == 'Deck Clip Builder' and not records:
        forms.alert('Create a coordinated rectangular layout with Deck Builder or '
                    'Joist Builder first, then enable boards, framing and clips in '
                    'the shared settings.', title='RESIDENTIALTOOLS')
        return None
    labels = ['New deck / framing layout...'] + [
        '{0} | {1}'.format(record['settings']['name'], record['layout_id'][:8]) for storage, record in records]
    choice = forms.SelectFromList.show(labels, title='RESIDENTIALTOOLS | Choose managed layout',
                                       multiselect=False, button_name='Open settings')
    if not choice:
        return None
    index = labels.index(choice)
    return records[index-1] if index else (None, None)


def run(mode):
    doc, uidoc = revit.doc, revit.uidoc
    if doc is None or uidoc is None or doc.IsFamilyDocument:
        forms.alert('Open a Revit project and a floor/structural plan first.', title='RESIDENTIALTOOLS')
        return
    if str(doc.Application.VersionNumber) not in ('2025', '2027'):
        forms.alert('This baseline targets Revit 2025 and 2027.', title='RESIDENTIALTOOLS')
        return
    folder, log_path, log = None, None, None
    committed=None
    try:
        folder, log_path, log = log_session(doc, mode)
        selection = choose_layout(doc, uidoc, mode)
        if selection is None:
            return
        storage, record = selection
        if record:
            values, anchor = dict(record['settings']), dict(record['anchor'])
        else:
            footprint = pick_footprint(uidoc, doc)
            if footprint is None:
                return
            anchor, run_ft, span_ft, z = footprint
            levels = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level), key=lambda level: level.Elevation)
            if not levels:
                raise ValueError('Project needs at least one Level.')
            level = doc.ActiveView.GenLevel or levels[0]
            values = dict(DEFAULTS, run_ft=run_ft, span_ft=span_ft,
                          height_in=(z-level.Elevation)*12.0, level_uid=level.UniqueId,
                          footprint_polygon=anchor.get('footprint_polygon'))
            if anchor.get('roof_projection'):
                values['height_in']+=values['joist_depth_in']+values['roof_clearance_in']
            if mode == 'Joist Builder':
                values.update(boards_enabled=False, clips_enabled=False)
            for old_storage, old_record in api.layout_records(doc):
                same_floor = (anchor.get('source_floor_uid') is not None and
                              anchor.get('source_floor_uid') == old_record['anchor'].get('source_floor_uid'))
                if same_floor or footprint_key(anchor, values, doc) == footprint_key(
                        old_record['anchor'], old_record['settings'], doc):
                    storage, record = old_storage, old_record
                    values, anchor = dict(record['settings']), dict(record['anchor'])
                    log('Reused existing layout at selected footprint instead of creating a duplicate.')
                    break
        if mode in ('Deck Builder', 'Deck Designer'):
            values['boards_enabled'] = True
        if mode in ('Joist Builder', 'Deck Designer'):
            values['framing_enabled'] = True
        if mode == 'Deck Clip Builder':
            values['clips_enabled'] = True
        settings_mode = mode
        initial_tab=None
        while True:
            ui_values = dict(values)
            if record:
                ui_values['layout_id'] = record['layout_id']
            result = rt_ui.show(doc, anchor, ui_values, settings_mode,initial_tab=initial_tab)
            if result is None:
                log('Canceled; model unchanged.')
                return
            values=result['settings']
            initial_tab=result.get('tab_index')
            if result['action'] == 'clip_family':
                create_clip_rfa(doc.Application, folder, log)
                continue
            if result['action'] == 'simpson_library':
                values = rt_simpson.run(doc, values, log)
                initial_tab=2
                continue
            if result['action'] == 'repick':
                footprint = pick_footprint(uidoc, doc)
                if footprint is not None:
                    anchor, values['run_ft'], values['span_ft'], z = footprint
                    values['footprint_polygon'] = anchor.get('footprint_polygon')
                    level = doc.GetElement(values['level_uid'])
                    if level is not None:
                        values['height_in'] = (z-level.Elevation)*12.0
                        if anchor.get('roof_projection'):
                            values['height_in']+=float(values['joist_depth_in'])+float(values['roof_clearance_in'])
                continue
            # Catch duplicate footprints after editing dimensions or repicking.
            for old_storage, old_record in api.layout_records(doc):
                if record and old_record['layout_id'] == record['layout_id']:
                    continue
                if footprint_key(anchor, values, doc) == footprint_key(
                        old_record['anchor'], old_record['settings'], doc):
                    raise ValueError('Another managed layout already occupies this footprint. '
                                     'Open that existing layout instead of creating duplicates.')
            committed = api.rebuild(doc, storage, record, anchor, result['planned'], log)
            export_warning = ''
            try:
                export_result(folder, committed)
            except Exception:
                log('Build COMMITTED but external report export failed:\n' + traceback.format_exc())
                export_warning = '\nExternal export failed; settings/counts remain stored in the model.'
            warnings = '\n'.join(committed['warnings'])
            forms.alert('Layout built: {0}\n\nPlaced counts: {1}\n\n{2}\n\n'
                        'Report folder: {3}{4}'.format(values['name'], rt_presentation.count_text(committed['counts'],
                            sum(entry.get('item',{}).get('border_kind')=='breaker' for entry in committed['items'])),
                                                      warnings, folder, export_warning),
                        title='RESIDENTIALTOOLS | Coordinated baseline')
            return
    except OperationCanceledException:
        if log:
            log('Selection canceled; model unchanged.')
    except Exception:
        detail = traceback.format_exc()
        script.get_logger().error(detail)
        if log:
            try:
                log(detail)
            except Exception:
                pass
        state=('Layout was committed. A later reporting/display step failed.' if committed is not None else
               'Residential build stopped. Any in-progress rebuild was rolled back.')
        forms.alert(state+'\n\n'+
                    '{0}\n\nLog: {1}'.format(detail[-1400:], log_path or 'pyRevit output'),
                    title='RESIDENTIALTOOLS | Build error')
