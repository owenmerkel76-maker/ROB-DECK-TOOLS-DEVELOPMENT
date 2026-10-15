# -*- coding: utf-8 -*-
"""Read-only quantities from owned current model elements; export UTF-8 CSV/JSON."""
import io
import json
import os
import traceback
from Autodesk.Revit import DB
from Autodesk.Revit.DB import Architecture as AR
from pyrevit import forms,revit,script
import rt_revit as api
import rt_accessories
import rt_command
import rt_manager
import rt_quantities
import rt_forms
from rt_layout import number
from rt_layout import owned_registered


def measure(doc,parent,record,seen,cache=None):
    rows,volumes,warnings,board_lengths=[],{},[],[]
    cache={} if cache is None else cache
    names=cache.setdefault('types',{})
    coord=api.axes(parent['anchor'],parent['settings'])
    for entry in record['items']:
        uid=entry['unique_id']; item=entry['item']; role=item['role']
        if uid in seen: raise ValueError('One element appears in multiple quantity registries: '+uid)
        seen.add(uid); element=doc.GetElement(uid)
        if element is None:
            warnings.append('Missing registered element: '+uid); continue
        if not owned_registered(record,api.read_stamp(element),uid):
            raise ValueError('Quantity ownership changed for '+uid)
        if role in ('HARDWARE_PLANE','STAIR_PART','RAILING_PART'): continue
        length=0.0
        stock_eligible=True
        if role=='POST':
            points=api.vertices(element); length=max(p.Z for p in points)-min(p.Z for p in points)
        elif role in ('JOIST','RIM','BLOCK','JOINT_SUPPORT','BORDER_SUPPORT','BORDER_BACKING','BEAM'):
            location=element.Location
            if not isinstance(location,DB.LocationCurve): raise ValueError('Framing no longer has a curve: '+uid)
            length=location.Curve.Length
        elif role in ('BOARD','BORDER'):
            points=api.vertices(element)
            u=item.get('axis_vector')
            axis=(coord[1]*u[0]+coord[2]*u[1]) if u else (coord[2] if item.get('axis')=='B' else coord[1])
            length=max(p.DotProduct(axis) for p in points)-min(p.DotProduct(axis) for p in points)
            across=DB.XYZ(-axis.Y,axis.X,0)
            extent=max(p.DotProduct(across) for p in points)-min(p.DotProduct(across) for p in points)
            if extent>item['width_in']/12+.01/12:
                stock_eligible=False
                warnings.append('Board orientation/width changed; stock estimate excludes '+uid+'. Rebuild or verify the cut length.')
            else: board_lengths.append(length)
        elif role=='RAILING':
            length=sum(curve.Length for curve in element.GetPath())
        if role in ('BOARD','BORDER'):
            type_name='Schematic composite {0:g} x {1:g} in'.format(
                item['width_in'],parent['settings']['board_thickness_in'])
            if item.get('border_kind')=='breaker': type_name='Breaker board | '+type_name
        elif role=='CLIP' and parent['settings'].get('clip_mode')=='Schematic solids':
            type_name='Generic clip | 3/16 in schematic'
        else:
            type_id=element.GetTypeId(); key=api.id_value(type_id)
            if key not in names:
                type_element=doc.GetElement(type_id)
                names[key]=rt_accessories.label(type_element) if type_element is not None else role
            type_name=names[key]
        materials=[]
        # Native accessories are assembled from subcomponents. Avoid claiming a
        # partial/double-counted assembly volume; their detail stays in schedules.
        if role not in ('STAIR','RAILING'):
            for material_id in element.GetMaterialIds(False):
                material=doc.GetElement(material_id)
                volume=element.GetMaterialVolume(material_id)
                materials.append(material.Name)
                key=material.UniqueId
                current=volumes.setdefault(key,dict(name=material.Name,volume_ft3=0))
                current['volume_ft3']+=volume
        width=item.get('width_in',item.get('section_width_in',''))
        depth=item.get('depth_in',item.get('section_depth_in',''))
        if role in ('JOIST','RIM','JOINT_SUPPORT','BORDER_SUPPORT'):
            width=parent['settings']['joist_width_in']; depth=parent['settings']['joist_depth_in']
        elif role in ('BOARD','BORDER'): depth=parent['settings']['board_thickness_in']
        rows.append(dict(layout_name=parent['settings']['name'],role=role,unique_id=uid,
                         element_id=api.id_value(element.Id),type_name=type_name,length_ft=length,
                         board_kind=item.get('border_kind'),
                         stock_eligible=stock_eligible,stock_width_in=parent['settings'].get('board_width_in',item.get('width_in','')),
                         stock_profile='Square-edge' if role=='BORDER' or item.get('edge_mode')=='square' else 'Grooved field',
                         width_in=width,depth_in=depth,
                         materials=materials))
    return rows,volumes,warnings,board_lengths


def run():
    doc=revit.doc
    if doc is None or doc.IsFamilyDocument or str(doc.Application.VersionNumber) not in ('2025','2027'):
        forms.alert('Open a Revit 2025/2027 project.',title='Material List'); return
    folder,path,log=rt_command.log_session(doc,'Material List')
    try:
        parents=api.layout_records(doc)
        if not parents: forms.alert('Build a managed deck first.',title='Material List'); return
        labels=['All managed decks']+[rt_manager._label(record) for storage,record in parents]
        choice=forms.SelectFromList.show(labels,title='Material List | Scope',multiselect=False,button_name='Report')
        if choice is None: return
        selected=parents if choice==labels[0] else [parents[labels.index(choice)-1]]
        def validate_options(values):
            return dict(extra=number(values['extra'],'Extra board allowance (%)',0,100),
                        kerf=number(values['kerf'],'Saw kerf (inches)',0,1),
                        trim=number(values['trim'],'Total end trim (inches)',0,24))
        inputs=rt_forms.show('Material List','Installed quantities stay separate from purchasing estimates. Square-edge and grooved stock/materials are packed separately.',
            [dict(key='extra',label='Extra board-order allowance (%)',value=10),
             dict(key='kerf',label='Saw kerf between cuts (inches)',value=.125),
             dict(key='trim',label='Total end-trim allowance per stock board (inches)',value=0)],validate_options,
            lambda v:'Extra {0:g}% | Kerf {1:g} in | Total end trim {2:g} in per board.'.format(v['extra'],v['kerf'],v['trim']),'Export quantities')
        if inputs is None: return
        extra,kerf,trim=inputs['extra'],inputs['kerf'],inputs['trim']
        rows,volumes,warnings,stock,seen=[],{},[],[],set(); cache={}
        for storage,parent in selected:
            children=rt_accessories.records(doc,parent['layout_id'])
            deck_rows=[]
            for record in [parent]+[child for child_storage,child in children]:
                current,mats,notes,cuts=measure(doc,parent,record,seen,cache)
                rows.extend(current); deck_rows.extend(current); warnings.extend(notes)
                for key,value in mats.items():
                    target=volumes.setdefault(key,dict(name=value['name'],volume_ft3=0))
                    target['volume_ft3']+=value['volume_ft3']
                if record.get('parent_generation') and record['parent_generation']!=parent['generation']:
                    warnings.append('Stairs/railings were built for an earlier deck generation; verify alignment and rerun their commands.')
            estimates=rt_quantities.grouped_stock(deck_rows,parent['settings']['stock_ft'],kerf,trim,extra)
            for estimate in estimates:
                estimate['layout_name']=parent['settings']['name']
                if not estimate['estimate_complete']:
                    warnings.append('Ordering withheld for {0} / {1}: a cut exceeds usable stock after trim.'.format(parent['settings']['name'],estimate['stock_profile']))
            stock.extend(estimates)
        grouped={}
        for row in rows:
            key=(row['role'],row['type_name'],', '.join(row['materials']))
            value=grouped.setdefault(key,dict(count=0,length_ft=0))
            value['count']+=1; value['length_ft']+=row['length_ft']
        installed=[['role','type','materials','installed_count','installed_length_ft']]
        for key,value in sorted(grouped.items()): installed.append(list(key)+[value['count'],value['length_ft']])
        pieces=[['layout','role','element_id','unique_id','type','length_ft','width_in','depth_in','materials']]
        pieces.extend([r['layout_name'],r['role'],r['element_id'],r['unique_id'],r['type_name'],r['length_ft'],
                       r['width_in'],r['depth_in'],', '.join(r['materials'])] for r in rows)
        material_rows=[['material','modeled_volume_ft3']]+[[v['name'],v['volume_ft3']] for v in volumes.values()]
        order=[['layout','profile','materials','stock_width_in','thickness_in','stock_length_ft','estimated_stock_boards','extra_percent','order_with_extra','installed_cut_length_ft','complete']]
        order.extend([e['layout_name'],e['stock_profile'],', '.join(e['materials']),e['stock_width_in'],e['thickness_in'],e['board_stock_ft'],e['stock_pieces'] if e['stock_pieces'] is not None else '',extra,e['order_with_allowance'] if e['order_with_allowance'] is not None else '',e['installed_length_ft'],e['estimate_complete']] for e in stock)
        for name,table in (('installed_quantities.csv',installed),('piece_list.csv',pieces),('modeled_material_volumes.csv',material_rows),('board_order_estimate.csv',order)):
            with io.open(os.path.join(folder,name),'w',encoding='utf-8-sig') as stream: stream.write(rt_quantities.csv_text(table))
        limitations=['Stock groups separate profiles/materials and use entered kerf/end trim; no ripped-width recovery or optimized nesting. Manual rotations/oversized cuts require review.',
                     'Native stairs/railings are counted as assemblies/paths. Use Revit schedules for their tread/stringer/baluster materials.',
                     'No nails, screws, post bases/caps or footings are inferred. Reported hardware counts cover only modeled instances.',
                     'Copied/unregistered manual elements are excluded.']
        report=dict(installed_pieces=rows,materials=list(volumes.values()),board_stock=stock,warnings=warnings,limitations=limitations)
        with io.open(os.path.join(folder,'material_list.json'),'w',encoding='utf-8') as stream: stream.write(api.text_type(json.dumps(report,indent=2)))
        log('Exported read-only material list: '+str(len(rows))+' installed instances/assemblies.')
        action=forms.alert('Exported {0} installed instances/assemblies.\n\nReports: {1}\n\n{2}\n\n{3}'.format(
            len(rows),folder,'\n'.join(warnings),'\n'.join(limitations)),title='Material List | Complete',
            options=['Open reports','Close'])
        if action=='Open reports': os.startfile(folder)
    except Exception:
        detail=traceback.format_exc(); log(detail); script.get_logger().error(detail)
        forms.alert('Material report stopped. Model unchanged.\n\n'+detail[-1000:]+'\nLog: '+path,title='Material List | Error')
