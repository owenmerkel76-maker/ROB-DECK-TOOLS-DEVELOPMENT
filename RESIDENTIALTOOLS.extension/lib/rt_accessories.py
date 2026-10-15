# -*- coding: utf-8 -*-
"""Native straight stair and perimeter railing prototypes with separate ownership."""
import json
import io
import os
import math
import traceback
import uuid
from Autodesk.Revit import DB
from Autodesk.Revit.DB import Architecture as AR
from Autodesk.Revit.DB.ExtensibleStorage import DataStorage
from Autodesk.Revit.UI.Selection import ObjectSnapTypes
from Autodesk.Revit.Exceptions import OperationCanceledException
from System.Collections.Generic import List
from pyrevit import forms, revit, script
import rt_revit as api
import rt_geometry as geo
import rt_accessory_layout as geometry
import rt_code_review
import rt_forms
import rt_presentation
from rt_layout import OWNER, VERSION, validate_deletion_scope,number


def records(doc, parent_id):
    result=[]
    for storage in DB.FilteredElementCollector(doc).OfClass(DataStorage):
        record=api.read_stamp(storage)
        if record.get('owner')==OWNER and record.get('role')=='AUX_LAYOUT' and record.get('parent_id')==parent_id:
            if record.get('version')!=VERSION:
                raise ValueError('Unsupported accessory registry version.')
            result.append((storage,record))
    return result


def label(element):
    parameter=element.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
    name=element.Name if isinstance(element,DB.Level) else (
        parameter.AsString() if parameter and parameter.HasValue else element.UniqueId)
    if isinstance(element,DB.FamilySymbol): name=element.Family.Name+' | '+name
    return name + ' | '+str(api.id_value(element.Id))


def remove_registered(doc, storage, record):
    elements,missing=api.registered_elements(doc,record)
    ids=List[DB.ElementId](); expected=set()
    for element in elements+[storage]:
        ids.Add(element.Id); expected.add(api.id_value(element.Id))
    validate_deletion_scope(expected,set(api.id_value(eid) for eid in doc.Delete(ids)))


def newly_dependent(doc, roots, before):
    """Adopt only new logical children, never existing levels/types/other models."""
    found={}; queue=list(roots)
    while queue:
        element=queue.pop()
        eid=api.id_value(element.Id)
        if eid in found or eid in before or isinstance(element,DB.ElementType):
            continue
        found[eid]=element
        queue.extend(doc.GetElement(key) for key in element.GetDependentElements(None)
                     if api.id_value(key) not in before and doc.GetElement(key) is not None)
    return list(found.values())


def write_record(doc, parent, kind, roots, before, settings, log):
    layout_id,generation=str(uuid.uuid4()),str(uuid.uuid4())
    elements=newly_dependent(doc,roots,before)
    root_ids=set(api.id_value(root.Id) for root in roots)
    items=[]
    for i,element in enumerate(elements):
        role=kind if api.id_value(element.Id) in root_ids else kind+'_PART'
        item=dict(key=kind+'_'+str(i+1),role=role)
        api.write_stamp(element,dict(owner=OWNER,version=VERSION,layout_id=layout_id,generation=generation,
                                    role=role,item=item,key=item['key']))
        items.append(dict(unique_id=element.UniqueId,element_id=api.id_value(element.Id),item=item))
    storage=DataStorage.Create(doc)
    record=dict(owner=OWNER,version=VERSION,role='AUX_LAYOUT',layout_id=layout_id,generation=generation,
                parent_id=parent['layout_id'],parent_generation=parent['generation'],kind=kind,
                settings=settings,element_uids=[e.UniqueId for e in elements],items=items,
                root_uids=[e.UniqueId for e in roots])
    api.write_stamp(storage,record)
    log('Accessory registered: '+json.dumps(record))
    return record


def set_parameter(element,bip,value):
    parameter=element.get_Parameter(bip)
    if parameter is None or parameter.IsReadOnly or not parameter.Set(value):
        raise ValueError('Required native constraint is not writable: '+str(bip))


def previous_settings(doc,parent,kind):
    matches=[record for storage,record in records(doc,parent['layout_id']) if record['kind']==kind]
    if len(matches)>1: raise ValueError('Multiple accessory records; replacement is ambiguous.')
    return dict(matches[0].get('settings',{})) if matches else {}


def stair_inputs(doc, parent):
    levels=sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level),key=lambda e:e.Elevation)
    types=sorted(DB.FilteredElementCollector(doc).OfClass(AR.StairsType),key=label)
    if len(levels)<2 or not types:
        raise ValueError('Load a native stair type and provide two distinct constraint levels first.')
    s=parent['settings']; deck_level=doc.GetElement(s['level_uid'])
    if deck_level is None: raise ValueError('The saved deck Level is missing; update the deck first.')
    deck_top=deck_level.Elevation+(s['height_in']+s['board_thickness_in'])/12.0
    ground=deck_top-s['board_thickness_in']/12-(s['joist_depth_in']+s.get('beam_depth_in',9.25))/12-s.get('post_height_ft',6)
    old=previous_settings(doc,parent,'STAIR')
    base=doc.GetElement(old['base_level_uid']) if old.get('base_level_uid') else levels[0]
    base=base if isinstance(base,DB.Level) else levels[0]
    top=next((level for level in levels if level.Elevation>base.Elevation),levels[-1])
    default_count=max(2,int(math.ceil((deck_top-ground)*12/7.0)))
    choices=[(label(level),level.UniqueId) for level in levels]
    fields=[dict(key='base',label='Base constraint level',kind='choice',choices=choices,value=base.UniqueId),
            dict(key='top',label='Higher constraint level (top offset aligns to deck)',kind='choice',choices=choices,
                 value=old.get('top_level_uid',top.UniqueId)),
            dict(key='type',label='Loaded native stair type',kind='choice',choices=[(label(t),t.UniqueId) for t in types],value=old.get('type_uid')),
            dict(key='width',label='Run width (feet; verify clear width after handrails)',value=old.get('width_ft',3)),
            dict(key='risers',label='Number of risers',value=old.get('risers',default_count)),
            dict(key='tread',label='Tread depth (inches)',value=old.get('tread_in',11)),
            dict(key='offset',label='Base offset above chosen level (inches)',value=old.get('base_offset_in',(ground-base.Elevation)*12))]
    def validate(values):
        base,top,stair_type=(doc.GetElement(values[key]) for key in ('base','top','type'))
        if top.Elevation<=base.Elevation: raise ValueError('Choose a top constraint level higher than the base level.')
        offset=number(values['offset'],'Base offset (inches)',-12000,12000)
        bottom=base.Elevation+offset/12
        planned=geometry.straight_stair(deck_top-bottom,values['width'],values['risers'],values['tread'])
        rt_code_review.validate_stair_dimensions(planned)
        planned.update(base_level_uid=base.UniqueId,top_level_uid=top.UniqueId,type_uid=stair_type.UniqueId,
                       bottom_ft=bottom,top_ft=deck_top,base_offset_in=offset)
        return base,top,stair_type,planned
    def summary(result):
        p=result[3]
        return '{0} risers at {1:.2f} in | {2} treads | Plan run {3:.2f} ft. Next: pick the top center and ground direction in plan.'.format(
            p['risers'],p['riser_in'],p['treads'],p['run_ft'])
    return rt_forms.show('Deck Stairs', 'Deck: '+s['name']+' | Top elevation: {0:.2f} ft. Native type controls supports and rails; verify landings, headroom and connections.'.format(deck_top),
                         fields,validate,summary,'Pick stair location')


def create_stair(doc,uidoc,parent,log):
    inputs=stair_inputs(doc,parent)
    if inputs is None: return None
    base,top,stair_type,s=inputs
    if doc.ActiveView.ViewType not in (DB.ViewType.FloorPlan,DB.ViewType.EngineeringPlan):
        raise ValueError('Pick the stair direction in a plan view with a work plane.')
    landing=uidoc.Selection.PickPoint(ObjectSnapTypes.Endpoints,'Stair top center at deck edge')
    toward=uidoc.Selection.PickPoint(ObjectSnapTypes.Endpoints,'Pick a point toward the ground landing')
    direction=DB.XYZ(toward.X-landing.X,toward.Y-landing.Y,0)
    if direction.GetLength()<.5: raise ValueError('Pick a distinct ground direction point.')
    direction=direction.Normalize()
    end=DB.XYZ(landing.X,landing.Y,s['bottom_ft']); start=end+direction*s['run_ft']
    s.update(top_xy=[landing.X,landing.Y],down_direction=[direction.X,direction.Y])
    scope=DB.StairsEditScope(doc,'RESIDENTIALTOOLS | straight deck stair')
    try:
        stairs_id=scope.Start(base.Id,top.Id)
        with api.transaction(doc,'Deck stair run',log):
            stair=doc.GetElement(stairs_id)
            replacement=stair.ChangeTypeId(stair_type.Id)
            if not replacement.Equals(DB.ElementId.InvalidElementId):
                stair=doc.GetElement(replacement); stairs_id=stair.Id
            set_parameter(stair,DB.BuiltInParameter.STAIRS_BASE_OFFSET,s['bottom_ft']-base.Elevation)
            set_parameter(stair,DB.BuiltInParameter.STAIRS_TOP_OFFSET,s['top_ft']-top.Elevation)
            stair.DesiredRisersNumber=s['risers']; stair.ActualTreadDepth=s['tread_in']/12
            run=AR.StairsRun.CreateStraightRun(doc,stairs_id,DB.Line.CreateBound(start,end),AR.StairsRunJustification.Center)
            run.ActualRunWidth=s['width_ft']; run.BeginsWithRiser=True; run.EndsWithRiser=True
            run.TopElevation=s['height_ft']  # Native run elevations are relative to stairs base.
            doc.Regenerate()
            if run.ActualRisersNumber!=s['risers'] or abs(stair.BaseElevation+run.TopElevation-s['top_ft'])>.001/12:
                raise ValueError('Native run does not match the requested risers/deck top; review its type/end-riser settings. Stair creation rolled back.')
        scope.Commit(api.FailureLogger(log))
        stair=doc.GetElement(stairs_id)
        if stair is None: raise ValueError('Native stair edit scope did not retain the new stair.')
        return [stair],s
    finally:
        if scope.IsActive: scope.Cancel()
        scope.Dispose()


def create_railings(doc,parent,log):
    s=parent['settings']; f=geo.frame(s); poly=f['polygon']
    types=sorted(DB.FilteredElementCollector(doc).OfClass(AR.RailingType),key=label)
    if not types: raise ValueError('Load a native railing type first.')
    old=previous_settings(doc,parent,'RAILING'); edges=rt_presentation.edge_labels(poly)
    opening=old.get('opening',[0,0,3])
    fields=[dict(key='type',label='Loaded native railing type',kind='choice',choices=[(label(t),t.UniqueId) for t in types],value=old.get('type_uid')),
            dict(key='edges',label='Perimeter edges to model (coordinates are in deck preview feet)',kind='checklist',
                 choices=list(zip(edges,range(len(poly)))),value=old.get('selected_edges',list(range(len(poly))))),
            dict(key='opening',label='Stair / gate opening edge',kind='choice',choices=[('No opening',-1)]+list(zip(edges,range(len(poly)))),value=int(opening[0])-1),
            dict(key='center',label='Opening center from edge start (feet)',value=opening[1]),
            dict(key='width',label='Opening width (feet)',value=opening[2])]
    def validate(values):
        edge=values['opening']; center=float(values['center']) if edge>=0 else 0; width=float(values['width']) if edge>=0 else 0
        paths=geometry.railing_paths(poly,values['edges'],edge,center,width)
        return dict(type_uid=values['type'],paths=paths,selected_edges=values['edges'],opening=[edge+1,center,width])
    result=rt_forms.show('Deck Railings','Deck: '+s['name']+' | Native type controls guard height and balusters. Leave access clear and verify the chosen type.',
                         fields,validate,lambda r:'{0} connected path(s), {1:.2f} ft total. Opening is excluded.'.format(len(r['paths']),sum(geometry.path_length(p) for p in r['paths'])),'Create / replace railings')
    if result is None: return None
    paths=result['paths']; railing_type=doc.GetElement(result['type_uid'])
    level=doc.GetElement(s['level_uid']); coord=api.axes(parent['anchor'],s)
    roots=[]
    with api.transaction(doc,'Deck perimeter railings',log):
        for points in paths:
            curve=DB.CurveLoop()
            world=[api.world_point(coord,x,y,0) for x,y in points]
            for a,b in zip(world,world[1:]): curve.Append(DB.Line.CreateBound(a,b))
            root=AR.Railing.Create(doc,curve,railing_type.Id,level.Id)
            if root is None: raise ValueError('Native railing could not be created.')
            set_parameter(root,DB.BuiltInParameter.STAIRS_RAILING_HEIGHT_OFFSET,
                          (s['height_in']+s['board_thickness_in'])/12)
            roots.append(root)
        doc.Regenerate()
    return roots,dict(type_uid=railing_type.UniqueId,paths=paths,opening=result['opening'],selected_edges=result['selected_edges'],
                      length_ft=sum(geometry.path_length(p) for p in paths),
                      level_uid=level.UniqueId,deck_top_offset_in=s['height_in']+s['board_thickness_in'])


def run(kind):
    doc,uidoc=revit.doc,revit.uidoc
    if doc is None or doc.IsFamilyDocument or str(doc.Application.VersionNumber) not in ('2025','2027'):
        forms.alert('Open a Revit 2025/2027 project.',title='Deck accessories'); return
    import rt_manager
    import rt_command
    folder,path,log=rt_command.log_session(doc,'Deck '+kind)
    group=None
    committed=False
    try:
        selected=rt_manager._select_layout(doc)
        if selected is None: return
        storage,parent=selected
        matches=[entry for entry in records(doc,parent['layout_id']) if entry[1]['kind']==kind]
        if len(matches)>1: raise ValueError('Duplicate accessory registries; refusing ambiguous replacement.')
        before=set(api.id_value(eid) for eid in DB.FilteredElementCollector(doc).ToElementIds())
        group=DB.TransactionGroup(doc,'RESIDENTIALTOOLS | '+kind)
        if group.Start()!=DB.TransactionStatus.Started: raise ValueError('Accessory transaction group could not start.')
        result=create_stair(doc,uidoc,parent,log) if kind=='STAIR' else create_railings(doc,parent,log)
        if result is None: return
        roots,values=result
        with api.transaction(doc,'Register deck accessory replacement',log):
            for old_storage,old_record in matches: remove_registered(doc,old_storage,old_record)
            record=write_record(doc,parent,kind,roots,before,values,log)
        if group.Assimilate()!=DB.TransactionStatus.Committed:
            raise ValueError('Accessory group did not commit.')
        committed=True
        try:
            with io.open(os.path.join(folder,'accessory_report.json'),'w',encoding='utf-8') as stream:
                stream.write(api.text_type(json.dumps(record,indent=2)))
        except Exception:
            log('Accessory committed; external report failed:\n'+traceback.format_exc())
        forms.alert('{0} native {1} assembly/path(s) created. Verify geometry, family/type, '
                    'height and connections in Revit.\nRerun this command to replace this deck accessory.\nLog: {2}'
                    .format(len(roots),kind.lower(),path),title='Deck accessories | Prototype')
    except OperationCanceledException:
        log('Canceled accessory command; group rolled back.')
    except Exception:
        detail=traceback.format_exc(); log(detail); script.get_logger().error(detail)
        state='Accessory was committed; a later report/display step failed.' if committed else 'Accessory stopped. Any in-progress transaction group is rolled back.'
        forms.alert(state+'\n\n'+detail[-1000:]+'\nLog: '+path,
                    title='Deck accessories | Error')
    finally:
        if group is not None:
            if group.GetStatus()==DB.TransactionStatus.Started: group.RollBack()
            group.Dispose()
