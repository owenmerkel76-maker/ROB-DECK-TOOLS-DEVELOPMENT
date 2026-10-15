# -*- coding: utf-8 -*-
"""Revit 2025/2027 adapter: geometry, ownership, atomic coordinated rebuild."""
import json
import math
import uuid
from contextlib import contextmanager

from System import Guid, String
from System.Collections.Generic import List
from Autodesk.Revit import DB
from Autodesk.Revit.DB.ExtensibleStorage import (AccessLevel, DataStorage, Entity,
                                                 ExtensibleStorageFilter, Schema, SchemaBuilder)
from Autodesk.Revit.DB.Structure import StructuralFramingUtils, StructuralType

import rt_board_profile
import rt_clip
import rt_simpson_catalog
import rt_geometry
from rt_layout import OWNER, VERSION, owned_registered, validate_deletion_scope

SCHEMA_GUID = Guid('4c61be62-398d-4fef-87a5-506ba95d2ec3')
LENGTH_TOL = .001 / 12.0
try:
    text_type = unicode
except NameError:
    text_type = str


def id_value(eid):
    return int(eid.Value)


def schema():
    result = Schema.Lookup(SCHEMA_GUID)
    if result is not None:
        field = result.GetField('Payload')
        if (result.SchemaName != 'ResidentialToolsRectV1' or field is None or
                field.ValueType.FullName != 'System.String'):
            raise RuntimeError('Residential ownership schema conflicts with another schema.')
        return result
    builder = SchemaBuilder(SCHEMA_GUID)
    builder.SetSchemaName('ResidentialToolsRectV1')
    builder.SetVendorId('RSDT')
    builder.SetReadAccessLevel(AccessLevel.Public)
    builder.SetWriteAccessLevel(AccessLevel.Public)
    builder.AddSimpleField('Payload', String)
    return builder.Finish()


def read_stamp(element):
    entity = element.GetEntity(schema())
    if not entity.IsValid():
        return {}
    payload = entity.Get[String](schema().GetField('Payload'))
    try:
        result = json.loads(payload)
    except (ValueError, TypeError):
        raise ValueError('Corrupt Residential metadata on element ' + str(id_value(element.Id)))
    if not isinstance(result, dict):
        raise ValueError('Residential element metadata must be a JSON object.')
    return result


def write_stamp(element, payload):
    entity = Entity(schema())
    entity.Set[String](schema().GetField('Payload'),
                       text_type(json.dumps(payload, ensure_ascii=False)))
    element.SetEntity(entity)


def layout_records(doc):
    records = []
    seen = set()
    for element in DB.FilteredElementCollector(doc).OfClass(DataStorage):
        stamp = read_stamp(element)
        if stamp.get('owner') == OWNER and stamp.get('role') == 'LAYOUT':
            if stamp.get('version') != VERSION:
                raise ValueError('Layout version is not supported by this baseline.')
            if stamp.get('layout_id') in seen:
                raise ValueError('Duplicate layout registry detected. Refusing ambiguous rebuild.')
            seen.add(stamp.get('layout_id'))
            records.append((element, stamp))
    return records


class FailureLogger(DB.IFailuresPreprocessor):
    def __init__(self, log):
        self.log = log

    def PreprocessFailures(self, accessor):
        error = False
        for failure in accessor.GetFailureMessages():
            self.log('REVIT {0}: {1}; element ids={2}'.format(
                failure.GetSeverity(), failure.GetDescriptionText(),
                [id_value(e) for e in failure.GetFailingElementIds()]))
            if failure.GetSeverity() == DB.FailureSeverity.Warning:
                accessor.DeleteWarning(failure)
            else:
                error = True
        return (DB.FailureProcessingResult.ProceedWithRollBack if error
                else DB.FailureProcessingResult.Continue)


@contextmanager
def transaction(doc, title, log):
    tx = DB.Transaction(doc, title)
    handler = FailureLogger(log)
    try:
        if tx.Start() != DB.TransactionStatus.Started:
            raise RuntimeError('Transaction could not start.')
        options = tx.GetFailureHandlingOptions()
        options.SetFailuresPreprocessor(handler)
        options.SetClearAfterRollback(True)
        tx.SetFailureHandlingOptions(options)
        yield
        if tx.Commit() != DB.TransactionStatus.Committed:
            raise RuntimeError('Revit rejected the build; transaction rolled back.')
    finally:
        if tx.GetStatus() == DB.TransactionStatus.Started:
            tx.RollBack()
        tx.Dispose()


def types(doc, category):
    return list(DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol).OfCategory(category))


def symbol_name(symbol):
    parameter = symbol.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
    family=symbol.Family.Name
    name=parameter.AsString() if parameter and parameter.HasValue else symbol.UniqueId
    return family if family==name else family+' | '+name


def clip_types(doc):
    categories = (DB.BuiltInCategory.OST_GenericModel,)
    return [symbol for symbol in types(doc, categories[0])
            if not point_family_reason(symbol.Family, categories)]


def hardware_categories():
    # Loadable connector RFAs such as Simpson LUS use Structural Connections.
    # OfClass(FamilySymbol) excludes system StructuralConnectionHandler objects.
    return (DB.BuiltInCategory.OST_GenericModel, DB.BuiltInCategory.OST_StructConnections)


def hardware_types(doc):
    categories = hardware_categories()
    return [symbol for category in categories for symbol in types(doc, category)
            if not hardware_family_reason(symbol.Family)]


def hardware_family_reason(family):
    """Accept unhosted points and non-face-hosted work-plane connectors."""
    if family.FamilyPlacementType != DB.FamilyPlacementType.WorkPlaneBased:
        return point_family_reason(family, hardware_categories())
    category = family.FamilyCategory
    if category is None or not any(category.Id.Equals(DB.ElementId(value))
                                  for value in hardware_categories()):
        return 'This work-plane family category is not supported for hardware.'
    if DB.AdaptiveComponentFamilyUtils.IsAdaptiveComponentFamily(family):
        return 'Adaptive families require a separate placement workflow.'
    host = family.get_Parameter(DB.BuiltInParameter.FAMILY_HOSTING_BEHAVIOR)
    if host is not None and host.AsInteger() != 0:
        return ('Family host behavior is {0}; face/wall/floor-hosted hardware '
                'requires a separate placement workflow.').format(host.AsInteger())
    return ''


def family_diagnostics(family):
    category = family.FamilyCategory
    host = family.get_Parameter(DB.BuiltInParameter.FAMILY_HOSTING_BEHAVIOR)
    plane = family.get_Parameter(DB.BuiltInParameter.FAMILY_WORK_PLANE_BASED)
    return dict(name=family.Name, category=category.Name if category else None,
                category_id=id_value(category.Id) if category else None,
                placement=text_type(family.FamilyPlacementType),
                host_behavior=host.AsInteger() if host is not None else None,
                work_plane_based=plane.AsInteger() if plane is not None else None,
                adaptive=bool(DB.AdaptiveComponentFamilyUtils.IsAdaptiveComponentFamily(family)))


def point_family_reason(family, categories):
    category = family.FamilyCategory
    if category is None or not any(category.Id.Equals(DB.ElementId(value)) for value in categories):
        return 'Category {0} is not supported by this picker.'.format(category.Name if category else '(none)')
    if family.FamilyPlacementType != DB.FamilyPlacementType.OneLevelBased:
        return 'Family placement is {0}; unhosted point placement is required.'.format(family.FamilyPlacementType)
    if DB.AdaptiveComponentFamilyUtils.IsAdaptiveComponentFamily(family):
        return 'Adaptive families require a separate placement workflow.'
    for key, label in ((DB.BuiltInParameter.FAMILY_HOSTING_BEHAVIOR, 'host behavior'),
                       (DB.BuiltInParameter.FAMILY_WORK_PLANE_BASED, 'work-plane requirement')):
        parameter = family.get_Parameter(key)
        if parameter is not None and parameter.AsInteger() != 0:
            return 'Family {0} is {1}; unhosted point placement is required.'.format(label, parameter.AsInteger())
    return ''


def type_dimensions(symbol):
    result = {}
    for key, suffix in (('joist_width_in', 'Width'), ('joist_depth_in', 'Depth')):
        for prefix in ('LL_AsGenerated_', 'FT_AsGenerated_'):
            parameter = symbol.LookupParameter(prefix + suffix)
            if parameter is not None and parameter.HasValue:
                result[key] = parameter.AsDouble() * 12.0
                break
    # Common Revit section parameters provide dimensions for ordinary loaded
    # families without assigning treatment/material identity from their names.
    for key, names in (('joist_width_in', ('b', 'Width', 'Section Width')),
                       ('joist_depth_in', ('h', 'Depth', 'Height', 'Section Depth'))):
        if key in result:
            continue
        for name in names:
            parameter = symbol.LookupParameter(name)
            if (parameter is not None and parameter.HasValue and
                    parameter.StorageType == DB.StorageType.Double and
                    parameter.Definition.GetDataType().Equals(DB.SpecTypeId.Length) and
                    parameter.AsDouble() > 0):
                result[key] = parameter.AsDouble() * 12.0
                break
    return result


def type_category(symbol):
    parameter = symbol.LookupParameter('LL_Category')
    if parameter is not None and parameter.HasValue:
        return parameter.AsString()
    name = symbol.Family.Name.upper()
    if name.startswith('FT_PT_'):
        return 'pressure_treated'
    if name.startswith('FT_KD_'):
        return 'untreated_dimensional'
    return 'unknown'


def post_dimensions(symbol):
    """Read column section dimensions without treating overall Height as depth."""
    result={}
    for key,names in (('joist_width_in',('b','Width','Section Width')),
                       ('joist_depth_in',('d','h','Depth','Section Depth'))):
        for name in names:
            parameter=symbol.LookupParameter(name)
            if (parameter is not None and parameter.HasValue and parameter.StorageType==DB.StorageType.Double and
                    parameter.Definition.GetDataType().Equals(DB.SpecTypeId.Length) and parameter.AsDouble()>0):
                result[key]=parameter.AsDouble()*12.0
                break
    return result


def validate_type(doc, settings):
    if not settings['framing_enabled']:
        return None
    uid = settings.get('joist_symbol_uid')
    symbol = doc.GetElement(uid) if uid else None
    if not isinstance(symbol, DB.FamilySymbol) or not symbol.Category.Id.Equals(
            DB.ElementId(DB.BuiltInCategory.OST_StructuralFraming)):
        raise ValueError('Select a loaded Structural Framing type. Generate/test the '
                         'Lumber Library RFAs and load them into this project first.')
    expected = {'Exterior pressure-treated': 'pressure_treated',
                'Interior untreated': 'untreated_dimensional'}.get(settings['exposure'])
    if expected is not None and type_category(symbol) != expected:
        raise ValueError('Selected framing type is {0}; the chosen exposure requires {1}. '
                         'For a loaded family without verified LL/FT treatment metadata, '
                         'choose User-verified engineered/custom and verify its material and section.'
                         .format(type_category(symbol), expected))
    dimensions = type_dimensions(symbol)
    for key, value in dimensions.items():
        if abs(settings[key] - value) > .001:
            raise ValueError('Entered {0} does not match selected type metadata ({1:g} in).'.format(key, value))
    return symbol


def validate_block_type(doc, settings, default_symbol):
    """Resolve a separately selected framing symbol for generated blocking."""
    uid = settings.get('block_symbol_uid')
    symbol = doc.GetElement(uid) if uid else default_symbol
    if not isinstance(symbol, DB.FamilySymbol) or not symbol.Category.Id.Equals(
            DB.ElementId(DB.BuiltInCategory.OST_StructuralFraming)):
        raise ValueError('Select a loaded Structural Framing type for solid blocking.')
    expected = {'Exterior pressure-treated': 'pressure_treated',
                'Interior untreated': 'untreated_dimensional'}.get(settings['exposure'])
    if expected is not None and type_category(symbol) != expected:
        raise ValueError('Selected blocking family category does not match framing exposure. '
                         'Choose a matching LL/FT family, or use user-verified custom framing.')
    dimensions = type_dimensions(symbol)
    for key, dimension_key in (('block_width_in', 'joist_width_in'),
                               ('block_depth_in', 'joist_depth_in')):
        if dimension_key in dimensions:
            if abs(settings[key] - dimensions[dimension_key]) > .001:
                raise ValueError('Entered {0} does not match selected blocking type metadata ({1:g} in).'
                                 .format(key, dimensions[dimension_key]))
    return symbol


def validate_clip_type(doc, settings):
    if not settings['clips_enabled'] or settings['clip_mode'] != 'Loaded family':
        return None
    uid = settings.get('clip_symbol_uid')
    symbol = doc.GetElement(uid) if uid else None
    eligible = set(item.UniqueId for item in clip_types(doc))
    if symbol is None or symbol.UniqueId not in eligible:
        raise ValueError('Choose an unhosted, non-adaptive, point-based Generic Model clip type.')
    schematic = symbol.Family.Name.startswith((rt_clip.FAMILY_NAME, 'DT_CAMO_EDGECLIP_3-16_SCHEMATIC'))
    if schematic and abs(settings['gap_in'] - .1875) > 1.e-7:
        raise ValueError('Selected reused schematic clip family requires a 3/16 inch side gap.')
    return symbol


def validate_hardware_type(doc, unique_id, label):
    if not unique_id:
        return None
    symbol = doc.GetElement(unique_id)
    eligible = set(item.UniqueId for item in hardware_types(doc))
    if symbol is None or symbol.UniqueId not in eligible:
        raise ValueError('Choose a loaded unhosted point-based Generic Model or loadable '
                         'Structural Connections type, or a non-face-hosted work-plane '
                         'type for {0}. Face/wall/floor-hosted, adaptive and line-based '
                         'families require a different placement workflow.'.format(label))
    return symbol


def validate_support_types(doc, settings):
    if not settings.get('supports_enabled'):
        return None, None
    symbols = []
    for key, category, width_key, depth_key, label in (
            ('beam_symbol_uid', DB.BuiltInCategory.OST_StructuralFraming,
             'beam_width_in', 'beam_depth_in', 'beam'),
            ('post_symbol_uid', DB.BuiltInCategory.OST_StructuralColumns,
             'post_width_in', 'post_depth_in', 'post')):
        uid = settings.get(key)
        symbol = doc.GetElement(uid) if uid else None
        if not isinstance(symbol, DB.FamilySymbol) or not symbol.Category.Id.Equals(DB.ElementId(category)):
            raise ValueError('Select a loaded {0} family in its structural category.'.format(label))
        expected = {'Exterior pressure-treated': 'pressure_treated',
                    'Interior untreated': 'untreated_dimensional'}.get(settings['exposure'])
        known = type_category(symbol)
        if expected and known in ('pressure_treated', 'untreated_dimensional') and known != expected:
            raise ValueError('Selected {0} treatment metadata conflicts with framing exposure.'.format(label))
        dimensions = post_dimensions(symbol) if label=='post' else type_dimensions(symbol)
        for target, source in ((width_key, 'joist_width_in'), (depth_key, 'joist_depth_in')):
            if source in dimensions and abs(settings[target]-dimensions[source]) > .001:
                raise ValueError('Entered {0} does not match the selected {1} section.'.format(target, label))
        if label == 'post' and (symbol.Family.FamilyPlacementType != DB.FamilyPlacementType.TwoLevelsBased or
                DB.AdaptiveComponentFamilyUtils.IsAdaptiveComponentFamily(symbol.Family)):
            raise ValueError('Posts require a non-adaptive, two-level Structural Column family.')
        symbols.append(symbol)
    return tuple(symbols)


def axes(anchor, settings):
    base_u = DB.XYZ(anchor['u'][0], anchor['u'][1], 0)
    base_v = DB.XYZ(-base_u.Y, base_u.X, 0)
    origin = DB.XYZ(anchor['origin'][0], anchor['origin'][1], 0)
    frame = rt_geometry.frame(settings)
    origin = origin + base_u*frame['shift'][0] + base_v*frame['shift'][1]
    u = base_u*math.cos(frame['angle']) + base_v*math.sin(frame['angle'])
    v = DB.XYZ(-u.Y, u.X, 0)
    return origin, u, v


def world_point(coord, x, y, z):
    origin, u, v = coord
    return origin + u * x + v * y + DB.XYZ.BasisZ * z


def loop(points):
    result = DB.CurveLoop()
    for i, point in enumerate(points):
        result.Append(DB.Line.CreateBound(point, points[(i+1) % len(points)]))
    loops = List[DB.CurveLoop]()
    loops.Add(result)
    return loops


def extrusion(points, direction, length, material):
    return DB.GeometryCreationUtilities.CreateExtrusionGeometry(
        loop(points), direction, length, DB.SolidOptions(material, DB.ElementId.InvalidElementId))


def material(doc, name, color):
    for item in DB.FilteredElementCollector(doc).OfClass(DB.Material):
        if item.Name == name:
            return item.Id
    eid = DB.Material.Create(doc, name)
    doc.GetElement(eid).Color = DB.Color(*color)
    return eid


def set_text(element, bip, value):
    parameter = element.get_Parameter(bip)
    if parameter is None or parameter.IsReadOnly:
        raise ValueError('Generated element lacks writable schedule metadata.')
    if not parameter.Set(text_type(value)):
        raise ValueError('Could not set schedule metadata.')


def tag(element, item, layout_id, generation, name):
    write_stamp(element, dict(owner=OWNER, version=VERSION, layout_id=layout_id,
                              generation=generation, role=item['role'], key=item['key'], item=item))
    set_text(element, DB.BuiltInParameter.ALL_MODEL_MARK, layout_id[:8] + '_' + item['key'])
    set_text(element, DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS,
             'RESIDENTIALTOOLS | {0} | {1} | {2}'.format(name, item['role'], item['key']))


def shape(doc, geometries, name, layout_id, item):
    result = DB.DirectShape.CreateElement(doc, DB.ElementId(DB.BuiltInCategory.OST_GenericModel))
    result.ApplicationId = OWNER
    result.ApplicationDataId = layout_id + ':' + item['key']
    result.Name = name
    geometry = List[DB.GeometryObject]()
    for solid in geometries:
        geometry.Add(solid)
    result.SetShape(geometry)
    return result


def create_board(doc, board, coord, underside, settings, mat, layout_id):
    if board['role'] == 'BORDER':
        points = [world_point(coord, x, y, underside) for x, y in board['polygon']]
        solid = extrusion(points, DB.XYZ.BasisZ, settings['board_thickness_in']/12.0, mat)
    else:
        outline = rt_board_profile.make_outline(board['width_in'], board['edge_mode'],
                                                thickness_in=settings['board_thickness_in'])
        center = (board['low'] + board['high'])/2.0
        points = [world_point(coord, board['start'], center+y/12.0, underside+z/12.0)
                  for y, z in outline]
        solid = extrusion(points, coord[1], board['length_ft'], mat)
        if board.get('polygon'):
            trim = extrusion([world_point(coord,x,y,underside) for x,y in board['polygon']],
                             DB.XYZ.BasisZ,settings['board_thickness_in']/12.0,mat)
            solid = DB.BooleanOperationsUtils.ExecuteBooleanOperation(solid,trim,DB.BooleanOperationsType.Intersect)
    return shape(doc, [solid], 'RT Composite ' + board['key'], layout_id, board)


def geometry_solids(geometry):
    for item in geometry:
        if isinstance(item, DB.Solid) and item.Volume > 1.e-9:
            yield item
        elif isinstance(item, DB.GeometryInstance):
            for solid in geometry_solids(item.GetInstanceGeometry()):
                yield solid


def vertices(element):
    result = []
    geometry = element.get_Geometry(DB.Options())
    if geometry is not None:
        for solid in geometry_solids(geometry):
            for face in solid.Faces:
                result.extend(face.Triangulate().Vertices)
    if not result:
        raise ValueError('Structural family produced no measurable 3D solids: ' + element.UniqueId)
    return result


def create_member(doc, member, coord, underside, settings, symbol, level):
    a = world_point(coord, member['a'][0], member['a'][1], underside)
    b = world_point(coord, member['b'][0], member['b'][1], underside)
    result = doc.Create.NewFamilyInstance(DB.Line.CreateBound(a, b), symbol, level, StructuralType.Beam)
    if result is None:
        raise ValueError('Revit could not create structural framing instance.')
    StructuralFramingUtils.DisallowJoinAtEnd(result, 0)
    StructuralFramingUtils.DisallowJoinAtEnd(result, 1)
    doc.Regenerate()
    points = vertices(result)
    # Use measured solid top, handling both the centered LL section and FT's
    # top-origin sections without guessing numeric justification enum values.
    delta = underside - max(p.Z for p in points)
    if abs(delta) > LENGTH_TOL:
        DB.ElementTransformUtils.MoveElement(doc, result.Id, DB.XYZ(0, 0, delta))
        doc.Regenerate()
        points = vertices(result)
    along = (b-a).Normalize()
    across = DB.XYZ(-along.Y, along.X, 0)
    expected_width = member.get('section_width_in', settings['joist_width_in']) / 12.0
    expected_depth = member.get('section_depth_in', settings['joist_depth_in']) / 12.0
    checks = [(max(p.DotProduct(along) for p in points)-min(p.DotProduct(along) for p in points), a.DistanceTo(b), 'length'),
              (max(p.DotProduct(across) for p in points)-min(p.DotProduct(across) for p in points), expected_width, 'width'),
              (max(p.Z for p in points)-min(p.Z for p in points), expected_depth, 'depth'),
              (max(p.Z for p in points), underside, 'top'),
              ((max(p.DotProduct(across) for p in points)+min(p.DotProduct(across) for p in points))/2.0,
               a.DotProduct(across), 'lateral center'),
              (min(p.DotProduct(along) for p in points), min(a.DotProduct(along), b.DotProduct(along)), 'start'),
              (max(p.DotProduct(along) for p in points), max(a.DotProduct(along), b.DotProduct(along)), 'end')]
    for measured, expected, label in checks:
        if abs(measured-expected) > LENGTH_TOL:
            raise ValueError('Family geometry {0} mismatch on {1}: expected {2:g} ft, got {3:g}. '
                             'Check family flex/offsets; entire rebuild will roll back.'.format(
                                 label, member['key'], expected, measured))
    return result


def create_post(doc, item, coord, underside, symbol, level):
    top = underside + item['top_offset_in']/12.0
    bottom = top - item['height_ft']
    point = world_point(coord, item['x'], item['y'], bottom)
    result = doc.Create.NewFamilyInstance(point, symbol, level, StructuralType.Column)
    if result is None:
        raise ValueError('Revit could not create post ' + item['key'])
    # Both constraints reference the chosen project level, with explicit offsets.
    # Lower the base first, then set the top offset and level. Avoid an interim
    # top below the base when both constraints reference the same level.
    for bip, value in ((DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM, level.Id),
                       (DB.BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM, bottom-level.Elevation),
                       (DB.BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM, top-level.Elevation),
                       (DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM, level.Id)):
        parameter = result.get_Parameter(bip)
        if parameter is None or parameter.IsReadOnly or not parameter.Set(value):
            raise ValueError('Post family lacks writable base/top constraints: ' + item['key'])
    angle = math.atan2(coord[1].Y, coord[1].X)+math.radians(item.get('rotation_deg',0))
    if abs(angle) > 1.e-9:
        DB.ElementTransformUtils.RotateElement(doc, result.Id,
            DB.Line.CreateBound(point, point+DB.XYZ.BasisZ), angle)
    doc.Regenerate()
    points = vertices(result)
    checks = [(min(p.Z for p in points), bottom, 'base'), (max(p.Z for p in points), top, 'top')]
    local=math.radians(item.get('rotation_deg',0))
    post_u=coord[1]*math.cos(local)+coord[2]*math.sin(local)
    post_v=coord[2]*math.cos(local)-coord[1]*math.sin(local)
    for axis, dimension, label in ((post_u, item['width_in']/12.0, 'width'),
                                    (post_v, item['depth_in']/12.0, 'depth')):
        low, high = min(p.DotProduct(axis) for p in points), max(p.DotProduct(axis) for p in points)
        checks.extend([(high-low, dimension, label), ((high+low)/2.0, point.DotProduct(axis), label+' center')])
    for measured, expected, label in checks:
        if abs(measured-expected) > LENGTH_TOL:
            raise ValueError('Post {0} geometry {1} mismatch; expected {2:g} ft, got {3:g}. '
                             'Check column family flex/origin; rebuild will roll back.'
                             .format(item['key'], label, expected, measured))
    return result


def schematic_clip_solids(coord, clip, underside, materials):
    result = []
    for outline, z, height, kind in rt_clip.parts():
        points = [world_point(coord, clip['x']+x/12.0, clip['y']+y/12.0, underside+z/12.0)
                  for x, y in outline]
        result.append(extrusion(points, DB.XYZ.BasisZ, height/12.0, materials[kind]))
    return result


def create_clip(doc, clip, coord, underside, level, symbol, materials, layout_id):
    if symbol is None:
        return shape(doc, schematic_clip_solids(coord, clip, underside, materials),
                     'RT Generic CAMO-style schematic clip', layout_id, clip)
    point = world_point(coord, clip['x'], clip['y'], underside)
    result = doc.Create.NewFamilyInstance(point, symbol, level, StructuralType.NonStructural)
    if result is None:
        raise ValueError('Clip family instance could not be created.')
    angle = math.atan2(coord[1].Y, coord[1].X)
    if abs(angle) > 1.e-9:
        DB.ElementTransformUtils.RotateElement(doc, result.Id,
            DB.Line.CreateBound(point, point+DB.XYZ.BasisZ), angle)
    return result


def create_hardware_plane(doc, coord, underside, layout_id, generation, plane_key='hardware'):
    """Create one owned horizontal host; keep it out of connector quantities."""
    origin = world_point(coord, 0, 0, underside)
    result = doc.Create.NewReferencePlane(origin + coord[1], origin, coord[2], doc.ActiveView)
    if result is None:
        raise ValueError('Revit could not create the hardware work plane.')
    result.Name = 'RT Hardware ' + layout_id[:8] + ' ' + generation[:8] + ' ' + plane_key
    doc.Regenerate()
    if result.GetPlane().Normal.DotProduct(DB.XYZ.BasisZ) < 0:
        result.Flip()
        doc.Regenerate()
    if result.GetPlane().Normal.DotProduct(DB.XYZ.BasisZ) < .999999:
        raise ValueError('Hardware work plane must face upward horizontally.')
    if result.GetReference() is None:
        raise ValueError('Hardware work plane has no usable reference.')
    return result


def create_hardware(doc, item, coord, underside, level, symbol, hardware_plane=None):
    """Place a native point or work-plane connector at its planned joint point."""
    point = world_point(coord, item['x'], item['y'], underside + item.get('z_offset_in', 0)/12.0)
    if symbol.Family.FamilyPlacementType == DB.FamilyPlacementType.WorkPlaneBased:
        if hardware_plane is None:
            raise ValueError('Work-plane hardware requires a managed reference plane: ' + item['key'])
        plane = hardware_plane.GetPlane()
        if abs((point - plane.Origin).DotProduct(plane.Normal)) > LENGTH_TOL:
            raise ValueError('Hardware insertion point is outside its managed plane: ' + item['key'])
        local_angle=math.radians(item.get('rotation_deg',0))+(math.pi if item.get('end')==1 else 0)
        direction=(coord[1]*math.cos(local_angle)+coord[2]*math.sin(local_angle)
                   if item.get('rotation_deg') else coord[1].Negate() if item.get('end')==1 else coord[1])
        # Reference direction sets rotation in the host plane. Do not rotate the
        # hosted instance afterwards or use the level/XYZ overload for this RFA.
        result = doc.Create.NewFamilyInstance(hardware_plane.GetReference(), point, direction, symbol)
        if result is None:
            raise ValueError('Work-plane hardware could not be created: ' + item['key'])
        return result
    if symbol.Category.Id.Equals(DB.ElementId(DB.BuiltInCategory.OST_StructConnections)):
        result = doc.Create.NewFamilyInstance(point, symbol, StructuralType.NonStructural)
    else:
        result = doc.Create.NewFamilyInstance(point, symbol, level, StructuralType.NonStructural)
    if result is None:
        raise ValueError('Hardware family instance could not be created: ' + item['key'])
    # Family local X follows the selected board axis; endpoint-based hardware is
    # turned toward the interior at the far end. Confirm this convention per RFA.
    angle = math.atan2(coord[1].Y, coord[1].X)+math.radians(item.get('rotation_deg',0))
    if item.get('end') == 1:
        angle += math.pi
    if abs(angle) > 1.e-9:
        DB.ElementTransformUtils.RotateElement(doc, result.Id,
            DB.Line.CreateBound(point, point+DB.XYZ.BasisZ), angle)
    return result


def registered_elements(doc, record, require_editable=True):
    result, missing = [], []
    if record is None:
        return result, missing
    for uid in record['element_uids']:
        element = doc.GetElement(uid)
        if element is None:
            missing.append(uid)
            continue
        if not owned_registered(record, read_stamp(element), uid):
            raise ValueError('Ownership changed for registered element. Rebuild refuses to delete it: ' + uid)
        if require_editable and (element.Pinned or not element.GroupId.Equals(DB.ElementId.InvalidElementId)):
            raise ValueError('Generated element is pinned or grouped. Unpin/ungroup before rebuilding: ' + uid)
        result.append(element)
    return result, missing


def rebuild(doc, data_storage, record, anchor, planned, log):
    schema()
    s = planned['settings']
    level = doc.GetElement(s['level_uid']) if s.get('level_uid') else None
    if not isinstance(level, DB.Level):
        raise ValueError('Select a valid project Level.')
    if anchor.get('roof_projection'):
        if s.get('supports_enabled'):
            raise ValueError('Projected roof-deck mode builds level boards/framing. Roof stanchions and bases are not implemented; disable freestanding beams/posts and use reviewed roof supports.')
        framing_bottom=level.Elevation+s['height_in']/12.0-(s['joist_depth_in']/12.0 if s['framing_enabled'] else 0)
        if framing_bottom<anchor['source_peak_ft']+s['roof_clearance_in']/12.0-LENGTH_TOL:
            raise ValueError('Increase deck elevation to maintain the chosen framing clearance above the sloped Floor peak.')
    joist_symbol = validate_type(doc, s)
    beam_symbol, post_symbol = validate_support_types(doc, s)
    rt_simpson_catalog.validate_selections(s, type_category(joist_symbol) if joist_symbol else None)
    block_symbol = (validate_block_type(doc, s, joist_symbol)
                    if any(item['role'] in ('BLOCK','BORDER_BACKING') for item in planned['members']) else None)
    clip_symbol = validate_clip_type(doc, s)
    hardware_symbols = {
        'HANGER': validate_hardware_type(doc, s.get('hanger_symbol_uid'), 'joist hangers'),
        'DOUBLE_HANGER': validate_hardware_type(doc, s.get('double_hanger_symbol_uid'), 'double joist hangers'),
        'HURRICANE_STRAP': validate_hardware_type(doc, s.get('hurricane_symbol_uid'), 'hurricane straps'),
        'CORNER_STRAP': validate_hardware_type(doc, s.get('corner_strap_symbol_uid'), 'corner straps')}
    old, missing = registered_elements(doc, record)
    layout_id = record['layout_id'] if record else str(uuid.uuid4())
    unregistered = []
    known_uids = set(record['element_uids']) if record else set()
    for element in DB.FilteredElementCollector(doc).WherePasses(ExtensibleStorageFilter(SCHEMA_GUID)):
        stamp = read_stamp(element)
        if (stamp.get('owner') == OWNER and stamp.get('layout_id') == layout_id and
                stamp.get('role') != 'LAYOUT' and element.UniqueId not in known_uids):
            unregistered.append(element.UniqueId)
    generation = str(uuid.uuid4())
    coord = axes(anchor, s)
    underside = level.Elevation + s['height_in']/12.0
    generated, item_records = [], []
    with transaction(doc, 'RESIDENTIALTOOLS | coordinated rebuild ' + s['name'], log):
        if joist_symbol is not None:
            joist_symbol.Activate()
        if block_symbol is not None:
            block_symbol.Activate()
        if clip_symbol is not None:
            clip_symbol.Activate()
        for symbol in (beam_symbol, post_symbol):
            if symbol is not None:
                symbol.Activate()
        for symbol in hardware_symbols.values():
            if symbol is not None:
                symbol.Activate()
        doc.Regenerate()
        board_mat = material(doc, 'RT_Composite_Schematic', (121, 91, 65))
        clip_mats = dict(nylon=material(doc, 'RT_Clip_Nylon_Schematic', (32, 35, 41)),
                         steel=material(doc, 'RT_Clip_Steel_Schematic', (164, 172, 177)))
        for item in planned['boards']:
            element = create_board(doc, item, coord, underside, s, board_mat, layout_id)
            tag(element, item, layout_id, generation, s['name'])
            generated.append(element)
            item_records.append(dict(unique_id=element.UniqueId, element_id=id_value(element.Id), item=item))
        for item in planned['members']:
            member_symbol = block_symbol if item['role'] in ('BLOCK','BORDER_BACKING') else joist_symbol
            element = create_member(doc, item, coord, underside, s, member_symbol, level)
            tag(element, item, layout_id, generation, s['name'])
            generated.append(element)
            item_records.append(dict(unique_id=element.UniqueId, element_id=id_value(element.Id), item=item))
        for item in planned['clips']:
            element = create_clip(doc, item, coord, underside, level, clip_symbol, clip_mats, layout_id)
            tag(element, item, layout_id, generation, s['name'])
            generated.append(element)
            item_records.append(dict(unique_id=element.UniqueId, element_id=id_value(element.Id), item=item))
        for item in planned.get('beams', []):
            element = create_member(doc, item, coord, underside+item['z_offset_in']/12.0, s, beam_symbol, level)
            tag(element, item, layout_id, generation, s['name'])
            generated.append(element)
            item_records.append(dict(unique_id=element.UniqueId, element_id=id_value(element.Id), item=item))
        for item in planned.get('posts', []):
            element = create_post(doc, item, coord, underside, post_symbol, level)
            tag(element, item, layout_id, generation, s['name'])
            generated.append(element)
            item_records.append(dict(unique_id=element.UniqueId, element_id=id_value(element.Id), item=item))
        hardware_planes = {}
        for item in planned['hardware']:
            symbol = hardware_symbols[item['role']]
            if symbol is None:
                raise ValueError('No loaded family selected for planned hardware role ' + item['role'])
            hardware_plane = None
            if symbol.Family.FamilyPlacementType == DB.FamilyPlacementType.WorkPlaneBased:
                elevation = underside + item.get('z_offset_in', 0)/12.0
                plane_key = round(elevation, 8)
                if plane_key not in hardware_planes:
                    name_key = 'plane-{0}'.format(len(hardware_planes)+1)
                    hardware_plane = create_hardware_plane(doc, coord, elevation, layout_id, generation, name_key)
                    plane_item = dict(role='HARDWARE_PLANE', key=name_key,
                                      elevation_ft=elevation, normal=[0, 0, 1])
                    # Reference planes have no writable Mark/Comments fields.
                    write_stamp(hardware_plane, dict(owner=OWNER, version=VERSION, layout_id=layout_id,
                                generation=generation, role=plane_item['role'], key=plane_item['key'], item=plane_item))
                    generated.append(hardware_plane)
                    item_records.append(dict(unique_id=hardware_plane.UniqueId,
                                              element_id=id_value(hardware_plane.Id), item=plane_item))
                    hardware_planes[plane_key] = hardware_plane
                    log('Hardware host plane: id={0}; elevation_ft={1}; normal=+Z; '
                        'placement/fit require Revit review.'.format(id_value(hardware_plane.Id), elevation))
                hardware_plane = hardware_planes[plane_key]
            try:
                element = create_hardware(doc, item, coord, underside, level, symbol, hardware_plane)
            except Exception:
                log('Hardware placement failed: item={0}; family={1}; diagnostics={2}'.format(
                    json.dumps(item), symbol_name(symbol), json.dumps(family_diagnostics(symbol.Family))))
                raise
            tag(element, item, layout_id, generation, s['name'])
            generated.append(element)
            item_records.append(dict(unique_id=element.UniqueId, element_id=id_value(element.Id), item=item))
        # Creating and checking new geometry BEFORE deleting the previous layout
        # means every failure leaves the previous layout intact via rollback.
        old_ids = List[DB.ElementId]()
        old_values = set()
        for element in old:
            old_ids.Add(element.Id)
            old_values.add(id_value(element.Id))
        if old:
            deleted = set(id_value(eid) for eid in doc.Delete(old_ids))
            validate_deletion_scope(old_values, deleted)
        if data_storage is None:
            data_storage = DataStorage.Create(doc)
        result = dict(owner=OWNER, version=VERSION, role='LAYOUT', layout_id=layout_id,
                      generation=generation, settings=s, anchor=anchor,
                      element_uids=[element.UniqueId for element in generated],
                      items=item_records, counts=planned['counts'], warnings=list(planned['warnings']),
                      skipped_hanger_connections=planned.get('skipped_hanger_connections', []),
                      managed_hardware_planes=len(hardware_planes),
                      missing_previous_elements=missing,
                      preserved_unregistered_tagged_copies=unregistered,
                      joist_type=symbol_name(joist_symbol) if joist_symbol else None,
                      blocking_type=symbol_name(block_symbol) if block_symbol else None,
                      beam_type=symbol_name(beam_symbol) if beam_symbol else None,
                      post_type=symbol_name(post_symbol) if post_symbol else None,
                      clip_type=symbol_name(clip_symbol) if clip_symbol else 'Generic CAMO-style schematic solids',
                      hardware_types=dict((role, symbol_name(symbol) if symbol else None)
                                          for role, symbol in hardware_symbols.items()))
        import rt_code_review
        result['code_review']=rt_code_review.review(planned)
        if unregistered:
            result['warnings'].append('{0} unregistered tagged copies were preserved and '
                                      'excluded from managed layout counts.'.format(len(unregistered)))
        write_stamp(data_storage, result)
        doc.Regenerate()
        for element in generated:
            if doc.GetElement(element.Id) is None:
                raise ValueError('Generated element disappeared before commit.')
    log('COMMITTED layout {0}; counts={1}; removed={2}; missing={3}'.format(
        layout_id, result['counts'], len(old), len(missing)))
    return result


def generate_clip_family(app, template, path, log):
    doc = app.NewFamilyDocument(template)
    if doc is None:
        raise ValueError('Could not open Generic Model template.')
    try:
        category = doc.OwnerFamily.FamilyCategory
        if category is None or not category.Id.Equals(DB.ElementId(DB.BuiltInCategory.OST_GenericModel)):
            raise ValueError('Clip RFA requires a Generic Model template.')
        if doc.OwnerFamily.FamilyPlacementType != DB.FamilyPlacementType.OneLevelBased:
            raise ValueError('Use an unhosted Generic Model.rft, not a face/work-plane/line template.')
        with transaction(doc, 'RT schematic clip family', log):
            manager = doc.FamilyManager
            if manager.CurrentType is None:
                manager.NewType('3-16 Gap - Schematic')
            else:
                manager.RenameCurrentType('3-16 Gap - Schematic')
            mats = dict(nylon=material(doc, 'RT_Clip_Nylon_Schematic', (32, 35, 41)),
                        steel=material(doc, 'RT_Clip_Steel_Schematic', (164, 172, 177)))
            for outline, z, height, kind in rt_clip.parts():
                points = [DB.XYZ(x/12.0, y/12.0, z/12.0) for x, y in outline]
                profile = DB.CurveArray()
                for i, point in enumerate(points):
                    profile.Append(DB.Line.CreateBound(point, points[(i+1) % len(points)]))
                profiles = DB.CurveArrArray()
                profiles.Append(profile)
                sketch = DB.SketchPlane.Create(doc, DB.Plane.CreateByNormalAndOrigin(DB.XYZ.BasisZ, points[0]))
                form = doc.FamilyCreate.NewExtrusion(True, profiles, sketch, height/12.0)
                form.get_Parameter(DB.BuiltInParameter.MATERIAL_ID_PARAM).Set(mats[kind])
            param = manager.AddParameter('RT_Model_Status', DB.GroupTypeId.IdentityData, DB.SpecTypeId.String.Text, False)
            manager.Set(param, 'Generic schematic; not CAMO CAD; not manufacturer approved')
            doc.Regenerate()
        options = DB.SaveAsOptions()
        options.OverwriteExistingFile = False
        doc.SaveAs(path, options)
    finally:
        if not doc.Close(False):
            raise RuntimeError('Schematic clip family document did not close.')
