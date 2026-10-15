# -*- coding: utf-8 -*-
"""Structural framing prototype; must be exercised inside Revit.

Reference-plane discovery, template-form removal and extrusion end locks are
adapted from the locally inspected FRAMETOOLS v0.2.2 Create Joist RFAs script.
The catalog, separate flange/web materials and automated tests are new.
"""
import os
import math
from contextlib import contextmanager

from Autodesk.Revit.DB import (
    Blend, BuiltInCategory, BuiltInParameter, Color, CurveArray, CurveArrArray,
    ElementId, Extrusion, FailureProcessingResult, FailureSeverity,
    FilteredElementCollector, GeometryInstance, GroupTypeId, IFailuresPreprocessor,
    Level, Line, Material, Options, Plane, PlanarFace, ReferencePlane, Revolution,
    SaveAsOptions, SketchPlane, Solid, SpecTypeId, Sweep, SweptBlend, Transaction,
    TransactionStatus, UnitSystem, ViewPlan, XYZ,
)
from Autodesk.Revit.DB.Structure import StructuralFramingUtils, StructuralType
from lumber_catalog import area_inches, rectangles

INCH = 1.0 / 12.0
TOLERANCE = 1.0e-4  # feet


def id_value(element_id):
    """Revit 2025/2027 expose 64-bit Value; never truncate to IntegerValue."""
    return int(element_id.Value)


class FailureLogger(IFailuresPreprocessor):
    def __init__(self, log):
        self.log = log

    def PreprocessFailures(self, accessor):
        has_error = False
        for failure in accessor.GetFailureMessages():
            ids = [id_value(eid) for eid in failure.GetFailingElementIds()]
            self.log('Revit failure: {0}; elements={1}'.format(
                failure.GetDescriptionText(), ids))
            if failure.GetSeverity() == FailureSeverity.Warning:
                # Recorded warnings need not open modal dialogs in temporary docs.
                accessor.DeleteWarning(failure)
            else:
                has_error = True
        return (FailureProcessingResult.ProceedWithRollBack if has_error
                else FailureProcessingResult.Continue)


@contextmanager
def transaction(doc, name, log):
    tx = Transaction(doc, name)
    handler = FailureLogger(log)
    try:
        if tx.Start() != TransactionStatus.Started:
            raise RuntimeError('Transaction did not start: ' + name)
        options = tx.GetFailureHandlingOptions()
        options.SetFailuresPreprocessor(handler)
        options.SetClearAfterRollback(True)
        tx.SetFailureHandlingOptions(options)
        yield
        if tx.Commit() != TransactionStatus.Committed:
            raise RuntimeError('Revit rolled back transaction: ' + name)
    finally:
        if tx.GetStatus() == TransactionStatus.Started:
            tx.RollBack()
        tx.Dispose()


def length_planes(doc):
    planes = dict(((p.Name or '').strip().lower(), p)
                  for p in FilteredElementCollector(doc).OfClass(ReferencePlane))
    for left, right in (('member left', 'member right'),
                        ('left member', 'right member'), ('left', 'right')):
        a, b = planes.get(left), planes.get(right)
        if a is None or b is None:
            continue
        delta = b.GetPlane().Origin - a.GetPlane().Origin
        if abs(delta.Z) > TOLERANCE or delta.GetLength() < 1.0:
            continue
        axis = delta.Normalize()
        if (abs(a.GetPlane().Normal.DotProduct(axis)) < .999 or
                abs(b.GetPlane().Normal.DotProduct(axis)) < .999):
            continue
        return a, b, axis, delta.GetLength()
    raise ValueError('Template needs horizontal Member Left/Member Right (or '
                     'Left/Right) beam planes. Localized templates are not yet supported.')


def plan_view(doc):
    views = [v for v in FilteredElementCollector(doc).OfClass(ViewPlan)
             if not v.IsTemplate and v.ViewType.ToString() == 'FloorPlan']
    if not views:
        raise ValueError('Template has no Ref. Level floor plan.')
    views.sort(key=lambda v: (0 if 'ref.' in v.Name.lower() else 1, v.Name))
    return views[0]


def remove_sample_forms(doc):
    ids = []
    for kind in (Extrusion, Sweep, Blend, SweptBlend, Revolution):
        ids.extend(e.Id for e in FilteredElementCollector(doc).OfClass(kind))
    for eid in ids:
        if doc.GetElement(eid) is not None:
            doc.Delete(eid)


def solids(geometry):
    for item in geometry:
        if isinstance(item, Solid) and item.Volume > 1.0e-9:
            yield item
        elif isinstance(item, GeometryInstance):
            for solid in solids(item.GetInstanceGeometry()):
                yield solid


def end_reference(doc, extrusion, plane, axis):
    doc.Regenerate()
    options = Options()
    options.ComputeReferences = True
    target = plane.GetPlane().Origin.DotProduct(axis)
    for solid in solids(extrusion.get_Geometry(options)):
        for face in solid.Faces:
            if (isinstance(face, PlanarFace) and face.Reference is not None and
                    abs(face.FaceNormal.DotProduct(axis)) > .999 and
                    abs(face.Origin.DotProduct(axis) - target) < TOLERANCE):
                return face.Reference
    raise ValueError('Cannot find extrusion end face on ' + plane.Name)


def create_extrusion(doc, rect, left, axis, span, view, right):
    transverse = XYZ(-axis.Y, axis.X, 0)
    origin = left.GetPlane().Origin
    sketch = SketchPlane.Create(doc, Plane.CreateByNormalAndOrigin(axis, origin))
    y0, z0, y1, z1, material_index = rect
    points = [origin + transverse * (y * INCH) + XYZ.BasisZ * (z * INCH)
              for y, z in ((y0, z0), (y1, z0), (y1, z1), (y0, z1))]
    curves = CurveArray()
    for i in range(4):
        curves.Append(Line.CreateBound(points[i], points[(i + 1) % 4]))
    loops = CurveArrArray()
    loops.Append(curves)
    extrusion = doc.FamilyCreate.NewExtrusion(True, loops, sketch, span)
    for plane in (left, right):
        reference = end_reference(doc, extrusion, plane, axis)
        alignment = doc.FamilyCreate.NewAlignment(view, plane.GetReference(), reference)
        if alignment is None or not alignment.IsLocked:
            raise ValueError('Revit did not lock extrusion to ' + plane.Name)
    return extrusion


def add_metadata(doc, section):
    manager = doc.FamilyManager
    if manager.CurrentType is None:
        manager.NewType(section['type_name'])
    else:
        manager.RenameCurrentType(section['type_name'])
    # Exactly one section/type per output RFA. Preserve template reference skeleton.
    extras = [t for t in manager.Types if t.Name != section['type_name']]
    for family_type in extras:
        manager.CurrentType = family_type
        manager.DeleteCurrentType()
    manager.CurrentType = next(t for t in manager.Types if t.Name == section['type_name'])
    for name, value in (('LL_Category', section['category']),
                        ('LL_Material_Identifier', section['material_id']),
                        ('LL_Profile', section['profile']),
                        ('LL_Design_Status', 'Prototype; species/grade/capacity unspecified')):
        parameter = manager.AddParameter(name, GroupTypeId.IdentityData,
                                         SpecTypeId.String.Text, False)
        manager.Set(parameter, value)
    for name, key in (('Width', 'width'), ('Depth', 'depth'),
                      ('Flange_Thickness', 'flange_thickness'),
                      ('Web_Thickness', 'web_thickness')):
        if key in section:
            parameter = manager.AddParameter('LL_AsGenerated_' + name,
                                             GroupTypeId.Dimensions, SpecTypeId.Length, False)
            # Reporting parameters document fixed section sizes, never imply flex.
            manager.SetFormula(parameter, '{0} in'.format(section[key]))
    material_parameters = []
    for i, name in enumerate(section['materials']):
        material = Material.Create(doc, name)
        doc.GetElement(material).Color = Color(*section['color'])
        description = doc.GetElement(material).get_Parameter(BuiltInParameter.ALL_MODEL_DESCRIPTION)
        if description is not None and not description.IsReadOnly:
            description.Set('Prototype visual identity; no physical or structural asset assigned.')
        parameter = manager.AddParameter('LL_Material_' + str(i + 1),
                                         GroupTypeId.Materials, SpecTypeId.Reference.Material, False)
        manager.Set(parameter, material)
        material_parameters.append(parameter)
    return material_parameters


def measure(elements, axis):
    transverse = XYZ(-axis.Y, axis.X, 0)
    points, volume, material_ids = [], 0.0, set()
    options = Options()
    for element in elements:
        geometry = element.get_Geometry(options)
        if geometry is None:
            raise ValueError('Element {0} has no geometry.'.format(id_value(element.Id)))
        for solid in solids(geometry):
            volume += solid.Volume
            for face in solid.Faces:
                material_ids.add(id_value(face.MaterialElementId))
                points.extend(face.Triangulate().Vertices)
    if not points:
        raise ValueError('No measurable solid geometry.')
    coordinates = [[p.DotProduct(a) for p in points] for a in (axis, transverse, XYZ.BasisZ)]
    return dict(length=max(coordinates[0]) - min(coordinates[0]),
                axis_min=min(coordinates[0]), axis_max=max(coordinates[0]),
                width=max(coordinates[1]) - min(coordinates[1]),
                depth=max(coordinates[2]) - min(coordinates[2]), volume=volume,
                material_ids=sorted(material_ids))


def check_measurement(doc, measurement, section, length, endpoints):
    expected = dict(length=length, width=section['width'] * INCH,
                    depth=section['depth'] * INCH,
                    volume=area_inches(section) * INCH * INCH * length)
    for key, value in expected.items():
        if abs(measurement[key] - value) > max(TOLERANCE, abs(value) * 1.0e-5):
            raise ValueError('{0}: expected {1}, measured {2}'.format(
                key, value, measurement[key]))
    for key, target in zip(('axis_min', 'axis_max'), sorted(endpoints)):
        if abs(measurement[key] - target) > TOLERANCE:
            raise ValueError('Solid end does not coincide with beam end: ' + key)
    names = set()
    # Retrieve actual material ids from faces rather than converting 64-bit ids.
    for material in FilteredElementCollector(doc).OfClass(Material):
        if id_value(material.Id) in measurement['material_ids']:
            names.add(material.Name)
    if names != set(section['materials']):
        raise ValueError('Solid materials mismatch: ' + repr(sorted(names)))
    measurement['material_names'] = sorted(names)


def test_family(doc, forms, section, axis, log):
    manager = doc.FamilyManager
    parameter = manager.get_Parameter('Length')
    if parameter is None:
        parameter = manager.get_Parameter(BuiltInParameter.INSTANCE_LENGTH_PARAM)
    if parameter is None or not parameter.IsInstance:
        raise ValueError('Template has no native instance Length parameter.')
    results = []
    for length in (8.0, 14.0, 8.0):
        with transaction(doc, 'LL family length flex', log):
            manager.Set(parameter, length)
            doc.Regenerate()
            measurement = measure(forms, axis)
            left, right, unused_axis, unused_span = length_planes(doc)
            endpoints = [p.GetPlane().Origin.DotProduct(axis) for p in (left, right)]
            check_measurement(doc, measurement, section, length, endpoints)
        measurement['test'] = 'family_length_flex'
        results.append(measurement)
        log('Family flex passed: ' + repr(measurement))
    return results


def test_project(app, family_doc, section, log):
    doc = app.NewProjectDocument(UnitSystem.Imperial)
    if doc is None:
        raise ValueError('Cannot create temporary project for beam tests.')
    try:
        family = family_doc.LoadFamily(doc)  # No open project transaction here.
        if family is None:
            raise ValueError('Generated family did not load into temporary project.')
        symbol_ids = list(family.GetFamilySymbolIds())
        if len(symbol_ids) != 1:
            raise ValueError('Expected exactly one family type.')
        symbol = doc.GetElement(symbol_ids[0])
        if symbol.LookupParameter('LL_Material_Identifier').AsString() != section['material_id']:
            raise ValueError('Loaded type material identifier does not match catalog.')
        results = []
        with transaction(doc, 'LL place and resize test beams', log):
            level = Level.Create(doc, 0.0)
            symbol.Activate()
            doc.Regenerate()
            for row, angle in enumerate((0.0, math.pi / 6.0)):
                axis = XYZ(math.cos(angle), math.sin(angle), 0)
                origin = XYZ(0, row * 20.0, 0)
                beam = doc.Create.NewFamilyInstance(
                    Line.CreateBound(origin, origin + axis * 8.0),
                    symbol, level, StructuralType.Beam)
                StructuralFramingUtils.DisallowJoinAtEnd(beam, 0)
                StructuralFramingUtils.DisallowJoinAtEnd(beam, 1)
                for length in (8.0, 14.0, 8.0):
                    # Change the SAME instance, not just independent family defaults.
                    beam.Location.Curve = Line.CreateBound(origin, origin + axis * length)
                    doc.Regenerate()
                    measurement = measure([beam], axis)
                    endpoints = (origin.DotProduct(axis),
                                 (origin + axis * length).DotProduct(axis))
                    check_measurement(doc, measurement, section, length, endpoints)
                    measurement.update(test='project_place_and_resize',
                                       angle_degrees=angle * 180.0 / math.pi,
                                       element_id=id_value(beam.Id))
                    results.append(measurement)
                    log('Project beam test passed: ' + repr(measurement))
        return results
    finally:
        if not doc.Close(False):
            raise RuntimeError('Temporary test project did not close.')


def generate_and_test(app, template, folder, section, log):
    doc = app.NewFamilyDocument(template)
    if doc is None:
        raise ValueError('Cannot open selected family template.')
    try:
        category = doc.OwnerFamily.FamilyCategory
        if category is None or not category.Id.Equals(ElementId(BuiltInCategory.OST_StructuralFraming)):
            raise ValueError('Selected RFT is not Structural Framing - Beams and Braces.')
        log('Generating ' + section['key'])
        with transaction(doc, 'LL generate ' + section['key'], log):
            left, right, axis, span = length_planes(doc)
            view = plan_view(doc)
            remove_sample_forms(doc)
            materials = add_metadata(doc, section)
            forms = []
            for rect in rectangles(section):
                form = create_extrusion(doc, rect, left, axis, span, view, right)
                parameter = form.get_Parameter(BuiltInParameter.MATERIAL_ID_PARAM)
                material = materials[rect[4]]
                if parameter is None or not doc.FamilyManager.CanElementParameterBeAssociated(parameter, material):
                    raise ValueError('Cannot associate extrusion material parameter.')
                doc.FamilyManager.AssociateElementParameterToFamilyParameter(parameter, material)
                if doc.FamilyManager.GetAssociatedFamilyParameter(parameter) is None:
                    raise ValueError('Extrusion material association failed.')
                forms.append(form)
            doc.Regenerate()
        tests = test_family(doc, forms, section, axis, log)
        tests.extend(test_project(app, doc, section, log))
        # No RFA is saved if any generation, family flex or project test fails.
        path = os.path.join(folder, section['family'] + '_R' + str(app.VersionNumber) + '.rfa')
        options = SaveAsOptions()
        options.OverwriteExistingFile = False
        doc.SaveAs(path, options)
        log('Saved after automated Revit checks: ' + path)
        return dict(rfa=path, checks=tests, section=section)
    finally:
        if not doc.Close(False):
            raise RuntimeError('Temporary family document did not close.')
