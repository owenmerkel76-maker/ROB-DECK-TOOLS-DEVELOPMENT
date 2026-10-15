"""Read-only local packaging checks; never launches Revit or creates a ZIP."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import sys
import warnings
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def validate_bundle_subset(source):
    """Validate the deliberately small YAML schema used by pyRevit bundles."""
    values, engine = {}, {}
    in_engine = False
    for number, raw in enumerate(source.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith('#'):
            continue
        if '\t' in raw:
            raise ValueError('Tabs are not allowed in bundle YAML (line {0})'.format(number))
        indent = len(raw) - len(raw.lstrip(' '))
        line = raw.strip()
        match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*):(?:\s+(.*))?$', line)
        if not match:
            raise ValueError('Invalid bundle YAML mapping (line {0})'.format(number))
        key, scalar = match.group(1), match.group(2)
        target = engine if indent == 2 and in_engine else values
        if (indent == 0 and key == 'engine' and scalar is None):
            if key in values:
                raise ValueError('Duplicate YAML key: ' + key)
            values[key], in_engine = {}, True
            continue
        if (indent not in (0, 2) or (indent == 2 and not in_engine) or
                (indent == 0 and in_engine and key != 'engine')):
            raise ValueError('Invalid bundle YAML indentation (line {0})'.format(number))
        if key in target:
            raise ValueError('Duplicate YAML key: ' + key)
        if scalar is None:
            raise ValueError('Unexpected nested mapping (line {0})'.format(number))
        if scalar.startswith('"'):
            try:
                value = json.loads(scalar)
            except ValueError as error:
                raise ValueError('Invalid quoted scalar at line {0}: {1}'.format(number, error))
            if not isinstance(value, str):
                raise ValueError('Expected a quoted string (line {0})'.format(number))
        elif scalar in ('true', 'false'):
            value = scalar == 'true'
        elif re.match(r'^-?[0-9]+$', scalar):
            value = int(scalar)
        else:
            raise ValueError('Unsupported bundle scalar syntax (line {0})'.format(number))
        target[key] = value
    required = {'title', 'tooltip', 'author', 'min_revit_version', 'max_revit_version'}
    if not required.issubset(set(values)) or set(values) - (required | {'engine'}):
        raise ValueError('Bundle YAML must contain the expected top-level fields')
    if engine and (set(engine) != {'clean'} or not isinstance(engine['clean'], bool)):
        raise ValueError('Bundle YAML engine mapping must contain boolean clean')
    return values


def validate_layout_subset(source):
    lines=[line for line in source.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if not lines or lines[0]!='layout:': raise ValueError('Expected a layout list')
    values=[]
    for line in lines[1:]:
        if not line.startswith('  - '): raise ValueError('Invalid layout list indentation')
        value=json.loads(line[4:])
        if not isinstance(value,str) or not value: raise ValueError('Layout entries must be quoted names')
        if value in values: raise ValueError('Duplicate layout entry: '+value)
        values.append(value)
    return dict(layout=values)


def validate(yaml_path=None, api_xml=None):
    if yaml_path:
        sys.path.insert(0, str(yaml_path))
    try:
        import yaml
    except ImportError:
        yaml = None
    from PIL import Image
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', DeprecationWarning)
        from lib2to3 import pygram, pytree
        from lib2to3.pgen2 import driver
    parser = driver.Driver(pygram.python_grammar, convert=pytree.convert)
    report = dict(errors=[], python_files=0, ironpython_static_files=0,
                  yaml_files=0, icons=0, bundles=0, preserved_files=0,
                  revit_execution='NOT RUN', api_xml=api_xml)

    UniqueLoader = None
    if yaml is not None:
        class UniqueLoader(yaml.SafeLoader):
            pass

        def mapping(loader, node, deep=False):
            result = {}
            for key_node, value_node in node.value:
                key = loader.construct_object(key_node, deep=deep)
                if key in result:
                    raise ValueError('Duplicate YAML key: ' + str(key))
                result[key] = loader.construct_object(value_node, deep=deep)
            return result

        UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    else:
        report['yaml_validation'] = 'strict pyRevit bundle schema parser (PyYAML unavailable)'
    for path in ROOT.rglob('*.py'):
        try:
            source = path.read_text(encoding='utf-8-sig')
            compile(source, str(path), 'exec')
            report['python_files'] += 1
            if path.relative_to(ROOT).parts[0] not in ('tests', 'tools'):
                parser.parse_string(source if source.endswith('\n') else source+'\n')
                for node in ast.walk(ast.parse(source)):
                    if isinstance(node, (ast.JoinedStr, ast.AnnAssign, ast.AsyncFunctionDef,
                                         ast.Await, ast.YieldFrom, ast.NamedExpr)):
                        raise ValueError('Python 3-only construct in runtime file')
                    if isinstance(node, ast.FunctionDef) and (node.args.kwonlyargs or node.args.posonlyargs):
                        raise ValueError('Python 3-only arguments in runtime file')
                report['ironpython_static_files'] += 1
        except Exception as error:
            report['errors'].append(str(path.relative_to(ROOT)) + ': ' + str(error))
    for path in ROOT.rglob('*.yaml'):
        try:
            source = path.read_text(encoding='utf-8-sig')
            if path.parent.suffix in ('.tab','.panel'):
                data=yaml.load(source,Loader=UniqueLoader) if yaml is not None else validate_layout_subset(source)
                expected={p.stem for p in path.parent.iterdir() if p.is_dir() and p.suffix in ('.panel','.pushbutton')}
                assert set(data)=={'layout'} and set(data['layout'])==expected and len(data['layout'])==len(expected),'Ribbon layout omits or duplicates a tool'
                report['yaml_files']+=1
                continue
            data = (yaml.load(source, Loader=UniqueLoader) if yaml is not None
                    else validate_bundle_subset(source))
            assert isinstance(data, dict)
            assert all(isinstance(data[k], str) and data[k] for k in ('title', 'tooltip', 'author'))
            assert data['min_revit_version'] == 2025 and data['max_revit_version'] == 2027
            report['yaml_files'] += 1
        except Exception as error:
            report['errors'].append(str(path.relative_to(ROOT)) + ': ' + str(error))
    for path in ROOT.rglob('*.pushbutton'):
        try:
            assert path.is_dir()
            assert path.parent.suffix == '.panel' and path.parent.parent.name == 'RESIDENTIALTOOLS.tab'
            assert all((path / name).is_file() for name in ('script.py', 'bundle.yaml', 'icon.png'))
            with Image.open(path / 'icon.png') as image:
                assert image.size == (32, 32) and image.format == 'PNG'
                image.verify()
            report['bundles'] += 1
            report['icons'] += 1
        except Exception as error:
            report['errors'].append(str(path.relative_to(ROOT)) + ': ' + str(error))
    try:
        assert not list(ROOT.rglob('*.extension')), 'Nested .extension directory'
        assert not list(ROOT.rglob('*.zip')), 'ZIP package present'
        tab = ROOT / 'RESIDENTIALTOOLS.tab'
        assert {p.name for p in tab.glob('*.panel')} == {
            'Framing.panel', 'Deck Design.panel', 'Deck Management.panel'}
        assert not list(ROOT.rglob('__pycache__')), 'Unexpected compiled Python artifacts'
        tree = ET.parse(ROOT / 'resources' / 'ResidentialSettings.xaml')
        ui = ast.parse((ROOT / 'lib' / 'rt_ui.py').read_text(encoding='utf-8'))
        cls = next(n for n in ui.body if isinstance(n, ast.ClassDef) and n.name == 'SettingsWindow')
        methods = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
        names = {node.attrib['{http://schemas.microsoft.com/winfx/2006/xaml}Name']
                 for node in tree.iter() if '{http://schemas.microsoft.com/winfx/2006/xaml}Name' in node.attrib}
        for node in tree.iter():
            for event in ('Click', 'SelectionChanged','TextChanged'):
                if event in node.attrib:
                    assert node.attrib[event] in methods, 'Missing WPF event handler'
        for node in ast.walk(cls):
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                    and node.value.id == 'self' and node.attr[0].isupper()
                    and node.attr not in ('Close', 'ShowDialog','Height','MinHeight','Title')):
                assert node.attr in names, 'Missing XAML control: ' + node.attr
        report['xaml'] = 'XML structure, control names and event handlers passed; native pyRevit window not executed'
        option_tree=ET.parse(ROOT/'resources'/'ToolOptions.xaml')
        option_ui=ast.parse((ROOT/'lib'/'rt_forms.py').read_text(encoding='utf-8'))
        option_cls=next(n for n in option_ui.body if isinstance(n,ast.ClassDef) and n.name=='OptionsWindow')
        option_methods={n.name for n in option_cls.body if isinstance(n,ast.FunctionDef)}
        for node in option_tree.iter():
            for event in ('Click','SelectionChanged'):
                if event in node.attrib: assert node.attrib[event] in option_methods,'Missing options event handler'
        report['options_xaml']='XML structure and event handlers passed'
        render_path=ROOT/'docs'/'UI_RENDER_REVIEW.json'
        if render_path.is_file():
            rendered=json.loads(render_path.read_text(encoding='utf-8-sig'))
            for relative,expected in rendered['source_hashes'].items():
                assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==expected,'Stale UI render review: '+relative
            report['offscreen_wpf_render']=str(rendered['screens_rendered'])+' sample screens rendered; native Revit/event binding NOT RUN'
        preserved = json.loads((ROOT / 'tools' / 'preserved_files.json').read_text(encoding='utf-8'))
        for relative, expected in preserved.items():
            actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            assert actual == expected.lower(), 'Preserved file changed: ' + relative
            report['preserved_files'] += 1
        inventory = json.loads((ROOT / 'docs' / 'SOURCE_INVENTORY.json').read_text(encoding='utf-8'))
        report['unmodified_source_files'], report['unavailable_source_files'] = 0, []
        for item in inventory['inspected_read_only']:
            path = Path(item['path'])
            if path.is_file():
                assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256'], 'Inspected source changed'
                report['unmodified_source_files'] += 1
            else:
                # The installed extension has no runtime dependency on Desktop source folders.
                report['unavailable_source_files'].append(item['path'])
        revit_adapter = (ROOT / 'lib' / 'rt_revit.py').read_text(encoding='utf-8')
        assert 'from Autodesk.Revit.DB.ExtensibleStorage import (AccessLevel, DataStorage, Entity,' in revit_adapter
        assert 'DB.DataStorage' not in revit_adapter, 'DataStorage belongs to DB.ExtensibleStorage'
        assert 'DB.AdaptiveComponentFamilyUtils.IsAdaptiveComponentFamily(family)' in revit_adapter
        assert 'AdaptiveComponentInstanceUtils.IsAdaptiveComponentFamily' not in revit_adapter
        report['extensible_storage_namespace'] = 'DataStorage imported from Autodesk.Revit.DB.ExtensibleStorage'
        report['adaptive_family_api'] = 'AdaptiveComponentFamilyUtils.IsAdaptiveComponentFamily'
    except Exception as error:
        report['errors'].append(str(error))
    if api_xml:
        try:
            members = {member.attrib['name'] for member in ET.parse(api_xml).findall('./members/member')}
            required = [
                'M:Autodesk.Revit.Creation.ItemFactoryBase.NewReferencePlane(Autodesk.Revit.DB.XYZ,Autodesk.Revit.DB.XYZ,Autodesk.Revit.DB.XYZ,Autodesk.Revit.DB.View)',
                'M:Autodesk.Revit.Creation.ItemFactoryBase.NewFamilyInstance(Autodesk.Revit.DB.Reference,Autodesk.Revit.DB.XYZ,Autodesk.Revit.DB.XYZ,Autodesk.Revit.DB.FamilySymbol)',
                'M:Autodesk.Revit.DB.ReferencePlane.GetReference',
                'M:Autodesk.Revit.DB.ReferencePlane.GetPlane',
                'M:Autodesk.Revit.DB.ReferencePlane.Flip',
                'M:Autodesk.Revit.Creation.ItemFactoryBase.NewFamilyInstance(Autodesk.Revit.DB.XYZ,Autodesk.Revit.DB.FamilySymbol,Autodesk.Revit.DB.Structure.StructuralType)',
                'M:Autodesk.Revit.DB.ExtensibleStorage.DataStorage.Create(Autodesk.Revit.DB.Document)',
                'M:Autodesk.Revit.DB.AdaptiveComponentFamilyUtils.IsAdaptiveComponentFamily(Autodesk.Revit.DB.Family)',
                'M:Autodesk.Revit.DB.Document.LoadFamily(Autodesk.Revit.DB.Document)',
                'M:Autodesk.Revit.DB.Definition.GetDataType',
                'P:Autodesk.Revit.DB.ElementId.Value',
                'M:Autodesk.Revit.DB.DirectShape.CreateElement(Autodesk.Revit.DB.Document,Autodesk.Revit.DB.ElementId)',
                'M:Autodesk.Revit.DB.Structure.StructuralFramingUtils.DisallowJoinAtEnd(Autodesk.Revit.DB.FamilyInstance,System.Int32)',
                'M:Autodesk.Revit.DB.ExtensibleStorage.ExtensibleStorageFilter.#ctor(System.Guid)',
                'M:Autodesk.Revit.DB.ExtensibleStorage.SchemaBuilder.AddSimpleField(System.String,System.Type)',
                'M:Autodesk.Revit.Creation.Document.NewFamilyInstance(Autodesk.Revit.DB.Curve,Autodesk.Revit.DB.FamilySymbol,Autodesk.Revit.DB.Level,Autodesk.Revit.DB.Structure.StructuralType)',
                'M:Autodesk.Revit.DB.GeometryCreationUtilities.CreateExtrusionGeometry(System.Collections.Generic.IList{Autodesk.Revit.DB.CurveLoop},Autodesk.Revit.DB.XYZ,System.Double,Autodesk.Revit.DB.SolidOptions)',
                'M:Autodesk.Revit.DB.BooleanOperationsUtils.ExecuteBooleanOperation(Autodesk.Revit.DB.Solid,Autodesk.Revit.DB.Solid,Autodesk.Revit.DB.BooleanOperationsType)',
                'F:Autodesk.Revit.DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM',
                'F:Autodesk.Revit.DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM',
                'F:Autodesk.Revit.DB.BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM',
                'F:Autodesk.Revit.DB.BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM',
                'F:Autodesk.Revit.DB.Structure.StructuralType.Column',
                'F:Autodesk.Revit.DB.FamilyPlacementType.TwoLevelsBased',
                'M:Autodesk.Revit.DB.StairsEditScope.Start(Autodesk.Revit.DB.ElementId,Autodesk.Revit.DB.ElementId)',
                'M:Autodesk.Revit.DB.EditScope.Commit(Autodesk.Revit.DB.IFailuresPreprocessor)',
                'M:Autodesk.Revit.DB.EditScope.Cancel',
                'P:Autodesk.Revit.DB.EditScope.IsActive',
                'M:Autodesk.Revit.DB.Architecture.StairsRun.CreateStraightRun(Autodesk.Revit.DB.Document,Autodesk.Revit.DB.ElementId,Autodesk.Revit.DB.Line,Autodesk.Revit.DB.Architecture.StairsRunJustification)',
                'P:Autodesk.Revit.DB.Architecture.Stairs.DesiredRisersNumber',
                'P:Autodesk.Revit.DB.Architecture.Stairs.ActualTreadDepth',
                'P:Autodesk.Revit.DB.Architecture.Stairs.BaseElevation',
                'P:Autodesk.Revit.DB.Architecture.StairsRun.ActualRunWidth',
                'P:Autodesk.Revit.DB.Architecture.StairsRun.BeginsWithRiser',
                'P:Autodesk.Revit.DB.Architecture.StairsRun.EndsWithRiser',
                'P:Autodesk.Revit.DB.Architecture.StairsRun.TopElevation',
                'P:Autodesk.Revit.DB.Architecture.StairsRun.ActualRisersNumber',
                'F:Autodesk.Revit.DB.BuiltInParameter.STAIRS_BASE_OFFSET',
                'F:Autodesk.Revit.DB.BuiltInParameter.STAIRS_TOP_OFFSET',
                'M:Autodesk.Revit.DB.Architecture.Railing.Create(Autodesk.Revit.DB.Document,Autodesk.Revit.DB.CurveLoop,Autodesk.Revit.DB.ElementId,Autodesk.Revit.DB.ElementId)',
                'M:Autodesk.Revit.DB.Architecture.Railing.GetPath',
                'F:Autodesk.Revit.DB.BuiltInParameter.STAIRS_RAILING_HEIGHT_OFFSET',
                'M:Autodesk.Revit.DB.Element.GetDependentElements(Autodesk.Revit.DB.ElementFilter)',
                'M:Autodesk.Revit.DB.Element.GetMaterialIds(System.Boolean)',
                'M:Autodesk.Revit.DB.Element.GetMaterialVolume(Autodesk.Revit.DB.ElementId)',
            ]
            for name in required:
                assert name in members, 'API XML member missing: ' + name
            report['api_members_checked'] = len(required)
        except Exception as error:
            report['errors'].append(str(error))
    return report


if __name__ == '__main__':
    cli = argparse.ArgumentParser()
    cli.add_argument('--yaml-lib', help='Optional directory containing PyYAML')
    cli.add_argument('--api-xml', help='Optional installed RevitAPI.xml for member checks')
    cli.add_argument('--report', help='Optional JSON report output path')
    args = cli.parse_args()
    result = validate(args.yaml_lib, args.api_xml)
    output = json.dumps(result, indent=2)
    print(output)
    if args.report:
        Path(args.report).write_text(output+'\n', encoding='utf-8')
    sys.exit(bool(result['errors']))
